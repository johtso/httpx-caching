# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

"""
The httplib2 algorithms ported for use with requests.
"""
import calendar
import logging
import time
from email.utils import parsedate_tz
from typing import Any, Iterable, Optional

from httpx import URL, Headers

from ._cache import BaseCache, DictCache
from ._models import Response
from ._serializer import Serializer

logger = logging.getLogger(__name__)

PERMANENT_REDIRECT_STATUSES = (301, 308)


class CacheController(object):
    """An interface to see if request should cached or not."""

    def __init__(
        self,
        cache: BaseCache = None,
        cache_etags: bool = True,
        # TODO: Define a BaseSerializer?
        serializer: Any = None,
        status_codes: Iterable[int] = None,
    ):
        self.cache = DictCache() if cache is None else cache
        self.cache_etags = cache_etags
        self.serializer = serializer or Serializer()
        self.cacheable_status_codes = status_codes or (200, 203, 300, 301, 308)

    @classmethod
    def cache_key(cls, url: URL) -> str:
        return str(url)

    # TODO: Tricky type hinting
    @classmethod
    def parse_cache_control(cls, headers: Headers):
        known_directives = {
            # https://tools.ietf.org/html/rfc7234#section-5.2
            "max-age": (int, True),
            "max-stale": (int, False),
            "min-fresh": (int, True),
            "no-cache": (None, False),
            "no-store": (None, False),
            "no-transform": (None, False),
            "only-if-cached": (None, False),
            "must-revalidate": (None, False),
            "public": (None, False),
            "private": (None, False),
            "proxy-revalidate": (None, False),
            "s-maxage": (int, True),
        }

        cc_headers = headers.get("cache-control", "")

        retval = {}  # type: ignore

        for cc_directive in cc_headers.split(","):
            if not cc_directive.strip():
                continue

            parts = cc_directive.split("=", 1)
            directive = parts[0].strip()

            try:
                typ, required = known_directives[directive]
            except KeyError:
                logger.debug("Ignoring unknown cache-control directive: %s", directive)
                continue

            if not typ or not required:
                retval[directive] = None
            if typ:
                try:
                    retval[directive] = typ(parts[1].strip())
                except IndexError:
                    if required:
                        logger.debug(
                            "Missing value for cache-control " "directive: %s",
                            directive,
                        )
                except ValueError:
                    logger.debug(
                        "Invalid value for cache-control directive " "%s, must be %s",
                        directive,
                        typ.__name__,
                    )

        return retval

    def get_cached_response(
        self,
        request_url: URL,
        request_headers: Headers,
    ) -> Optional[Response]:
        """
        Return a valid cached response if it exists in the cache.

        If cached response is stale is is purged from cache.
        """
        cache_url = self.cache_key(request_url)
        logger.debug('Looking up "%s" in the cache', cache_url)
        cc = self.parse_cache_control(request_headers)

        # Bail out if the request insists on fresh data
        if "no-cache" in cc:
            logger.debug('Request header has "no-cache", cache bypassed')
            return None

        if "max-age" in cc and cc["max-age"] == 0:
            logger.debug('Request header has "max_age" as 0, cache bypassed')
            return None

        # Request allows serving from the cache, let's see if we find something
        cache_data = self.cache.get(cache_url)
        if cache_data is None:
            logger.debug("No cache entry available")
            return None

        # Check whether it can be deserialized
        response = self.serializer.loads(request_headers, cache_data)

        if not response:
            logger.warning("Cache entry deserialization failed, entry ignored")
            return None

        # If we have a cached permanent redirect, return it immediately. We
        # don't need to test our response for other headers b/c it is
        # intrinsically "cacheable" as it is Permanent.
        #
        # See:
        #   https://tools.ietf.org/html/rfc7231#section-6.4.2
        #
        # Client can try to refresh the value by repeating the request
        # with cache busting headers as usual (ie no-cache).
        if response.status_code in PERMANENT_REDIRECT_STATUSES:
            msg = (
                "Returning cached permanent redirect response "
                "(ignoring date and etag information)"
            )
            logger.debug(msg)
            return response

        if not response.headers or "date" not in response.headers:
            if "etag" not in response.headers:
                # Without date or etag, the cached response can never be used
                # and should be deleted.
                logger.debug("Purging cached response: no date or etag")
                self.cache.delete(cache_url)
            logger.debug("Ignoring cached response: no date")
            return None

        now = time.time()
        # TODO: parsedate_tz might return None (no date value or malformed)
        date = calendar.timegm(parsedate_tz(response.headers["date"]))  # type: ignore
        current_age = max(0, now - date)
        logger.debug("Current age based on date: %i", current_age)

        resp_cc = self.parse_cache_control(response.headers)

        # determine freshness
        freshness_lifetime = 0

        # Check the max-age pragma in the cache control header
        if "max-age" in resp_cc:
            freshness_lifetime = resp_cc["max-age"]
            logger.debug("Freshness lifetime from max-age: %i", freshness_lifetime)

        # If there isn't a max-age, check for an expires header
        elif "expires" in response.headers:
            expires = parsedate_tz(response.headers["expires"])
            if expires is not None:
                expire_time = calendar.timegm(expires) - date  # type: ignore
                freshness_lifetime = max(0, expire_time)
                logger.debug("Freshness lifetime from expires: %i", freshness_lifetime)

        # Determine if we are setting freshness limit in the
        # request. Note, this overrides what was in the response.
        if "max-age" in cc:
            freshness_lifetime = cc["max-age"]
            logger.debug(
                "Freshness lifetime from request max-age: %i", freshness_lifetime
            )

        if "min-fresh" in cc:
            min_fresh = cc["min-fresh"]
            # adjust our current age by our min fresh
            current_age += min_fresh
            logger.debug("Adjusted current age from min-fresh: %i", current_age)

        # Return entry if it is fresh enough
        if freshness_lifetime > current_age:
            logger.debug('The response is "fresh", returning cached response')
            logger.debug("%i > %i", freshness_lifetime, current_age)
            return response

        # we're not fresh. If we don't have an Etag, clear it out
        if "etag" not in response.headers:
            logger.debug('The cached response is "stale" with no etag, purging')
            self.cache.delete(cache_url)

        # return the original handler
        return None

    def conditional_headers(
        self, request_url: URL, request_headers: Headers
    ) -> Headers:
        cache_url = self.cache_key(request_url)
        response = self.serializer.loads(request_headers, self.cache.get(cache_url))
        new_headers = Headers()

        if response:
            if "etag" in response.headers:
                new_headers["If-None-Match"] = response.headers["ETag"]

            if "last-modified" in response.headers:
                new_headers["If-Modified-Since"] = response.headers["Last-Modified"]

        return new_headers

    def cache_response(
        self,
        request_url: URL,
        request_headers: Headers,
        response: Response,
        response_body: bytes,
    ) -> None:
        """
        Algorithm for caching responses.
        """
        # From httplib2: Don't cache 206's since we aren't going to
        #                handle byte range requests
        if response.status_code not in self.cacheable_status_codes:
            logger.debug(
                "Status code %s not in %s",
                response.status_code,
                self.cacheable_status_codes,
            )
            return

        # If we've been given a body, our response has a Content-Length, that
        # Content-Length is valid then we can check to see if the body we've
        # been given matches the expected size, and if it doesn't we'll just
        # skip trying to cache it.
        if (
            response_body is not None
            and "content-length" in response.headers
            and response.headers["content-length"].isdigit()
            and int(response.headers["content-length"]) != len(response_body)
        ):
            return

        cc_req = self.parse_cache_control(request_headers)
        cc = self.parse_cache_control(response.headers)

        cache_url = self.cache_key(request_url)
        logger.debug('Updating cache with response from "%s"', cache_url)

        # Delete it from the cache if we happen to have it stored there
        no_store = False
        if "no-store" in cc:
            no_store = True
            logger.debug('Response header has "no-store"')
        if "no-store" in cc_req:
            no_store = True
            logger.debug('Request header has "no-store"')
        if no_store and self.cache.get(cache_url):
            logger.debug('Purging existing cache entry to honor "no-store"')
            self.cache.delete(cache_url)
        if no_store:
            return

        # https://tools.ietf.org/html/rfc7234#section-4.1:
        # A Vary header field-value of "*" always fails to match.
        # Storing such a response leads to a deserialization warning
        # during cache lookup and is not allowed to ever be served,
        # so storing it can be avoided.
        if "*" in response.headers.get("vary", ""):
            logger.debug('Response header has "Vary: *"')
            return

        # If we've been given an etag, then keep the response
        if self.cache_etags and "etag" in response.headers:
            logger.debug("Caching due to etag")

        # Add to the cache any permanent redirects. We do this before looking
        # that the Date headers.
        elif int(response.status_code) in PERMANENT_REDIRECT_STATUSES:
            logger.debug("Caching permanent redirect")
            response_body = b""

        # Add to the cache if the response headers demand it. If there
        # is no date header then we can't do anything about expiring
        # the cache.
        elif "date" in response.headers:
            # cache when there is a max-age > 0
            if "max-age" in cc and cc["max-age"] > 0:
                logger.debug("Caching b/c date exists and max-age > 0")

            # If the request can expire, it means we should cache it
            # in the meantime.
            elif "expires" in response.headers:
                if response.headers["expires"]:
                    logger.debug("Caching b/c of expires header")
            else:
                return
        else:
            return

        self.cache.set(
            cache_url, self.serializer.dumps(request_headers, response, response_body)
        )

    def update_cached_response(
        self, request_url: URL, request_headers: Headers, response_headers: Headers
    ) -> Optional[Response]:
        """On a 304 we will get a new set of headers that we want to
        update our cached value with, assuming we have one.

        This should only ever be called when we've sent an ETag and
        gotten a 304 as the response.
        """
        cache_url = self.cache_key(request_url)

        cached_response = self.serializer.loads(
            request_headers, self.cache.get(cache_url)
        )

        if not cached_response:
            # we didn't have a cached response
            return None

        # Lets update our headers with the headers from the new request:
        # http://tools.ietf.org/html/draft-ietf-httpbis-p4-conditional-26#section-4.1
        #
        # The server isn't supposed to send headers that would make
        # the cached body invalid. But... just in case, we'll be sure
        # to strip out ones we know that might be problematic due to
        # typical assumptions.
        excluded_headers = ["content-length"]

        cached_response.headers.update(
            dict(
                (k, v)
                for k, v in response_headers.items()
                if k.lower() not in excluded_headers
            )
        )

        # we want a 200 b/c we have content via the cache
        cached_response.status_code = 200

        # update our cache
        self.cache.set(
            cache_url,
            self.serializer.dumps(
                request_headers, cached_response, cached_response.stream
            ),
        )

        return cached_response
