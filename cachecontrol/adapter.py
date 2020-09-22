# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import functools
from typing import Callable, Iterator, Tuple

import httpcore
from httpcore import _types as httpcore_types
from httpx import codes, Headers, URL

from .controller import CacheController, PERMANENT_REDIRECT_STATUSES
from .cache import DictCache
from .models import Response


class SyncByteStreamWrapper(httpcore.SyncByteStream):
    def __init__(
        self,
        stream: httpcore.SyncByteStream,
        callback: Callable,
    ) -> None:
        """
        A wrapper around a stream that calls a callback when stream is closed.
        """
        self.stream = stream
        self.callback = callback
        self.buffer = bytearray()

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:
            self.buffer.extend(chunk)
            yield chunk

    def close(self) -> None:
        self.stream.close()
        self.callback(bytes(self.buffer))


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
        debug=False,
    ):
        self.cache = DictCache() if cache is None else cache
        self.heuristic = heuristic
        self.cacheable_methods = cacheable_methods or (b"GET",)

        controller_factory = controller_class or CacheController
        self.controller = controller_factory(
            self.cache, cache_etags=cache_etags, serializer=serializer
        )
        if transport:
            self.transport = transport
        self.debug = debug

    def pre_request(self, request_method, request_url, request_headers):
        # TODO: CacheControl allowed passing cacheable_methods as part of the request?

        cached_response = None
        new_request_headers = request_headers.copy()

        if request_method in self.cacheable_methods:
            cached_response = self.controller.cached_request(request_url, request_headers)

        # check for etags and add headers if appropriate
        new_request_headers.update(self.controller.conditional_headers(request_url, request_headers))

        return cached_response, new_request_headers

    def post_request(
        self,
        request_url,
        request_method,
        request_headers,
        response,
        from_cache
            ):

        cached_response = None
        # TODO: is cacheability being checked in too many places?
        if not from_cache and request_method in self.cacheable_methods:
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
                # TODO: Is this enough to release the connection to the pool?
                for _ in response.stream:
                    pass
                response.stream.close()

            # We always cache the 301 responses
            elif response.status_code in PERMANENT_REDIRECT_STATUSES:
                self.controller.cache_response(
                     request_url,
                     request_headers,
                     response
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
                        response
                    ),
                )

        # See if we should invalidate the cache.
        if request_method in self.invalidating_methods and not codes.is_error(response_status_code):
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
        url: httpcore_types.URL,
        headers: httpcore_types.Headers = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, httpcore_types.Headers, httpcore.SyncByteStream, dict]:
        url = URL(url)
        headers = Headers(headers)

        cached_response, new_request_headers = self.pre_request(method, url, headers)

        if cached_response:
            response = cached_response
            from_cache = True
        else:
            response = self.transport.request(method, url.raw, new_request_headers.raw, stream, ext)
            response = Response.from_raw(response)
            from_cache = False

        # TODO: Could still be from cache?
        response, from_cache = self.post_request(url, method, headers, response, from_cache=from_cache)
        if self.debug:
            response.headers['x-cache'] = 'hit' if from_cache else 'miss'

        return response.to_raw()


class AsyncHTTPCacheTransport(HTTPCacheTransport, httpcore.AsyncHTTPTransport):
    # TODO: make sure supplied transport is async

    async def request(self, *args, **kwargs):
        return await self.transport.request(*args, **kwargs)