import typing
from typing import Iterable, Optional, Tuple, Union

import httpcore
import httpx

from httpx_caching import _policy as protocol
from httpx_caching._cache import DictCache
from httpx_caching._heuristics import BaseHeuristic
from httpx_caching._models import Response
from httpx_caching._policy import CachingPolicy, Source
from httpx_caching._types import RawHeaders, RawURL
from httpx_caching._utils import ByteStreamWrapper, request_to_raw


class SyncCachingTransport(httpcore.SyncHTTPTransport):
    invalidating_methods = {"PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        transport: httpcore.SyncHTTPTransport,
        cache: DictCache = None,
        cache_etags: bool = True,
        heuristic: BaseHeuristic = None,
        cacheable_methods: Iterable[str] = ("GET",),
        cacheable_status_codes: Iterable[int] = (
            200,
            203,
            300,
            301,
            308,
        ),
    ):
        self.transport = transport

        self.cache = DictCache() if cache is None else cache
        self.heuristic = heuristic
        self.cacheable_methods = cacheable_methods
        self.cacheable_status_codes = cacheable_status_codes
        self.cache_etags = cache_etags

    def request(
        self,
        method: bytes,
        url: RawURL,
        headers: RawHeaders = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, RawHeaders, httpcore.SyncByteStream, dict]:

        request = httpx.Request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
        )

        caching_protocol = CachingPolicy(
            request=request,
            cache_etags=self.cache_etags,
            heuristic=self.heuristic,
            cacheable_methods=self.cacheable_methods,
            cacheable_status_codes=self.cacheable_status_codes,
        )

        response, source = caching_protocol.run(self.io_handler)

        response.ext["from_cache"] = source == Source.CACHE
        return response.to_raw()

    @typing.no_type_check
    def io_handler(
        self, action: protocol.IOAction
    ) -> Union[Tuple[Optional[Response], Optional[dict]], Optional[Response]]:
        """
        Takes an IOAction produced by the caching protocol and enacts it.

        If asked to get a Response from the cache or remote server, it returns
        that Response.
        """
        if isinstance(action, protocol.CacheGet):
            return self.cache.get(action.key)

        elif isinstance(action, protocol.CacheDelete):
            self.cache.delete(action.key)
            return None

        elif isinstance(action, protocol.CacheSet):
            stream = action.response.stream
            # TODO: we can probably just get rid of deferred?
            if action.deferred and not isinstance(stream, httpcore.PlainByteStream):
                return self.wrap_response_stream(
                    action.key, action.response, action.vary_header_values
                )
            else:
                stream = action.response.stream
                assert isinstance(stream, httpcore.PlainByteStream)
                response_body = stream._content
                self.cache.set(
                    action.key,
                    action.response,
                    action.vary_header_values,
                    response_body,
                )
            return None

        elif isinstance(action, protocol.MakeRequest):
            args = request_to_raw(action.request)
            raw_response = self.transport.request(*args)  # type: ignore
            return Response.from_raw(raw_response)

        elif isinstance(action, protocol.CloseResponseStream):
            for _chunk in action.response.stream:  # type: ignore
                pass
            action.response.stream.close()  # type: ignore
            return None
        else:
            raise ValueError(action)

    def wrap_response_stream(
        self, key: str, response: Response, vary_header_values: dict
    ) -> Response:
        wrapped_stream = ByteStreamWrapper(response.stream)
        response.stream = wrapped_stream

        def callback(response_body: bytes):
            print("saving to cache:", key)
            self.cache.set(key, response, vary_header_values, response_body)

        response.stream.callback = callback
        return response

    def close(self) -> None:
        self.cache.close()
        self.transport.close()  # type: ignore
