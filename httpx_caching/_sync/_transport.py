from typing import Iterable, Optional, Tuple

import httpx
from httpx import SyncByteStream
from multimethod import multimethod

from httpx_caching import SyncDictCache, _policy as protocol
from httpx_caching._heuristics import BaseHeuristic
from httpx_caching._models import Response
from httpx_caching._policy import CachingPolicy, Source
from httpx_caching._types import RawHeaders, RawURL
from httpx_caching._utils import ByteStreamWrapper, request_to_raw


class SyncCachingTransport(httpx.BaseTransport):
    invalidating_methods = {"PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        transport: httpx.BaseTransport,
        cache: SyncDictCache = None,
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

        self.cache = SyncDictCache() if cache is None else cache
        self.heuristic = heuristic
        self.cacheable_methods = cacheable_methods
        self.cacheable_status_codes = cacheable_status_codes
        self.cache_etags = cache_etags

    def handle_request(
        self,
        method: bytes,
        url: RawURL,
        headers: RawHeaders,
        stream: SyncByteStream,
        extensions: dict,
    ) -> Tuple[int, RawHeaders, SyncByteStream, dict]:

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

        response.extensions["from_cache"] = source == Source.CACHE
        return response.to_raw()

    @multimethod
    def io_handler(self, action):
        raise NotImplementedError(f"Cannot handle {action}")

    @io_handler.register
    def _io_cache_get(
        self, action: protocol.CacheGet
    ) -> Tuple[Optional[Response], Optional[dict]]:
        return self.cache.get(action.key)

    @io_handler.register
    def _io_cache_delete(self, action: protocol.CacheDelete) -> None:
        self.cache.delete(action.key)
        return None

    @io_handler.register
    def _io_cache_set(self, action: protocol.CacheSet) -> Optional[Response]:
        if action.deferred:
            # This is a response with a body, so we need to wait for it to be read before we can cache it
            return self.wrap_response_stream(
                action.key, action.response, action.vary_header_values
            )
        else:
            stream = action.response.stream
            # TODO: Are we needlessly recaching the body here? Is this just a header change?
            self.cache.set(
                action.key,
                action.response,
                action.vary_header_values,
                b"".join(stream),  # type: ignore
            )
        return None

    @io_handler.register
    def _io_make_request(self, action: protocol.MakeRequest) -> Response:
        args = request_to_raw(action.request)
        raw_response = self.transport.handle_request(*args)  # type: ignore
        return Response.from_raw(raw_response)

    @io_handler.register
    def _io_close_response_stream(self, action: protocol.CloseResponseStream) -> None:
        for _chunk in action.response.stream:  # type: ignore
            pass
        action.response.stream.close()
        return None

    def wrap_response_stream(
        self, key: str, response: Response, vary_header_values: dict
    ) -> Response:
        response_stream: SyncByteStream = response.stream  # type: ignore
        wrapped_stream = ByteStreamWrapper(response_stream)
        response.stream = wrapped_stream

        def callback(response_body: bytes):
            print("saving to cache:", key)
            self.cache.set(key, response, vary_header_values, response_body)

        response.stream.callback = callback
        return response

    def close(self) -> None:
        self.cache.close()
        self.transport.close()  # type: ignore
