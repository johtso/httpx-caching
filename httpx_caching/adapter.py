# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import functools
from typing import Optional, Tuple

import httpcore
import httpx
from httpx import URL, Headers, codes

from ._types import RawHeaders, RawURL
from .cache import DictCache
from .controller import PERMANENT_REDIRECT_STATUSES, CacheController
from .models import Response
from .utils import SyncByteStreamWrapper


class HTTPCacheTransport:
    """
    Base caching Transport
    """

    invalidating_methods = {"PUT", "PATCH", "DELETE"}

    def __init__(
        self,
        cache=None,
        cache_etags=True,
        controller_class=None,
        serializer=None,
        heuristic=None,
        cacheable_methods=None,
        transport=None,
    ):
        self.cache = DictCache() if cache is None else cache
        self.heuristic = heuristic
        self.cacheable_methods = cacheable_methods or ("GET",)

        controller_factory = controller_class or CacheController
        self.controller = controller_factory(
            self.cache, cache_etags=cache_etags, serializer=serializer
        )
        if not transport:
            raise ValueError("You must provide a Transport.")
        self.transport = transport

    def is_cacheable_method(self, method: str):
        return method in self.cacheable_methods

    def is_invalidating_method(self, method: str):
        return method in self.invalidating_methods

    def pre_request(
        self,
        request_method: str,
        request_url: URL,
        request_headers: Headers,
    ) -> Tuple[Optional[Response], Headers]:
        """
        Returns a potentially valid cached Response.
        """

        # TODO: CacheControl allowed passing cacheable_methods as part of the request?
        cached_response = None
        new_request_headers = request_headers.copy()

        if self.is_cacheable_method(request_method):
            cached_response = self.controller.cached_request(
                request_url, request_headers
            )

        # check for etags and add headers if appropriate
        # TODO: This seems to hit the cache a second time, that shouldn't be necessary.
        new_request_headers.update(
            self.controller.conditional_headers(request_url, request_headers)
        )

        return cached_response, new_request_headers

    def post_request(
        self,
        request_url: URL,
        request_method: str,
        request_headers: Headers,
        response: Response,
        from_cache: bool,
    ) -> Tuple[Response, bool]:

        cached_response = None
        # TODO: is cacheability being checked in too many places?
        if not from_cache and self.is_cacheable_method(request_method):
            # Check for any heuristics that might update headers
            # before trying to cache.
            if self.heuristic:
                self.heuristic.apply(response.headers, response.status_code)

            # apply any expiration heuristics
            if response.status_code == 304:
                # We must have sent an ETag request. This could mean
                # that we've been expired already or that we simply
                # have an etag. In either case, we want to try and
                # update the cache if that is the case.
                cached_response = self.controller.update_cached_response(
                    request_url, request_headers, response.headers
                )

                # We are done with the server response, read a
                # possible response body (compliant servers will
                # not return one, but we cannot be 100% sure) and
                # release the connection back to the pool.
                # TODO: This wont work for Async!
                for _ in response.stream:
                    pass
                response.stream.close()

            # We always cache the 301 responses
            elif response.status_code in PERMANENT_REDIRECT_STATUSES:
                self.controller.cache_response(
                    request_url, request_headers, response, None
                )
            else:
                # Wrap the response file with a wrapper that will cache the
                #   response when the stream has been consumed.
                # TODO: Should this be self.StreamWrapper?
                response.stream = SyncByteStreamWrapper(
                    response.stream,
                    functools.partial(
                        self.controller.cache_response,
                        request_url,
                        request_headers,
                        response,
                    ),
                )

        # See if we should invalidate the cache.
        if self.is_invalidating_method(request_method) and not codes.is_error(
            response.status_code
        ):
            cache_url = self.controller.cache_url(request_url)
            self.cache.delete(cache_url)

        if cached_response:
            return cached_response, True
        else:
            return response, from_cache

    def close(self):
        self.cache.close()
        self.transport.close()


class SyncHTTPCacheTransport(HTTPCacheTransport, httpcore.SyncHTTPTransport):
    # TODO: make sure supplied transport is sync

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
        cached_response, new_request_headers = self.pre_request(
            request.method, request.url, request.headers
        )

        if cached_response:
            response = cached_response
            from_cache = True
            request_made = False
        else:
            response = self.transport.request(
                request.method,
                request.url.raw,
                new_request_headers.raw,
                request.stream,
                ext,
            )
            response = Response.from_raw(response)
            from_cache = False
            request_made = True

        response, from_cache = self.post_request(
            request.url,
            request.method,
            request.headers,
            response,
            from_cache=from_cache,
        )

        response.ext["from_cache"] = from_cache
        if request_made:
            response.ext["real_request"] = httpx.Request(
                method=request.method,
                url=request.url,
                headers=new_request_headers,
                stream=request.stream,
            )

        return response.to_raw()


class AsyncHTTPCacheTransport(HTTPCacheTransport, httpcore.AsyncHTTPTransport):
    # TODO: make sure supplied transport is async

    async def request(self, *args, **kwargs):
        return await self.transport.request(*args, **kwargs)
