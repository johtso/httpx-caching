import calendar
import logging
import time
import typing
from copy import copy
from dataclasses import dataclass
from email.utils import parsedate_tz
from enum import Enum
from typing import Awaitable, Callable, Generator, Iterable, Optional, Tuple, Union

from httpx import ByteStream, Headers, Request, codes

from ._heuristics import BaseHeuristic
from ._models import Response
from ._utils import async_callback_generator, sync_callback_generator

logger = logging.getLogger(__name__)

PERMANENT_REDIRECT_STATUSES = (
    301,
    308,
)

INVALIDATING_METHODS = ("PUT", "PATCH", "DELETE")

Source = Enum("Source", ["CACHE", "SERVER"])
Evaluation = Enum("Evaluation", ["GOOD", "INCONCLUSIVE"])
CacheVerb = Enum("CacheVerb", ["GET", "SET", "DELETE"])
VaryData = dict

# Cache actions


@dataclass
class CacheGet:
    key: str


@dataclass
class CacheSet:
    key: str
    response: Response
    vary_header_values: dict
    deferred: bool = False


@dataclass
class CacheDelete:
    key: str


CacheAction = Union[CacheGet, CacheSet, CacheDelete]


# HTTP request related IO actions


@dataclass
class MakeRequest:
    request: Request


@dataclass
class CloseResponseStream:
    response: Response


IOAction = Union[CacheAction, MakeRequest, CloseResponseStream]


AsyncIOCallback = Callable[[IOAction], Awaitable[Optional[Response]]]
SyncIOCallback = Callable[[IOAction], Optional[Response]]


@dataclass
class CachingPolicy:
    request: Request
    cache_etags: bool
    heuristic: Optional[BaseHeuristic]
    cacheable_methods: Iterable[str]
    cacheable_status_codes: Iterable[int]

    @typing.no_type_check
    def run(
        self,
        io_callback: SyncIOCallback,
    ) -> Tuple[Response, Source]:
        # TODO: Shouldn't need to make mypy ignore this should I?
        return sync_callback_generator(
            caching_policy,
            io_callback,
            dict(
                request=self.request,
                cache_etags=self.cache_etags,
                heuristic=self.heuristic,
                cacheable_methods=self.cacheable_methods,
                cacheable_status_codes=self.cacheable_status_codes,
            ),
        )

    @typing.no_type_check
    async def arun(
        self,
        io_callback: AsyncIOCallback,
    ) -> Tuple[Response, Source]:
        return await async_callback_generator(
            caching_policy,
            io_callback,
            dict(
                request=self.request,
                cache_etags=self.cache_etags,
                heuristic=self.heuristic,
                cacheable_methods=self.cacheable_methods,
                cacheable_status_codes=self.cacheable_status_codes,
            ),
        )


def caching_policy(
    request: Request,
    cache_etags: bool,
    heuristic: BaseHeuristic,
    cacheable_methods: Tuple[str],
    cacheable_status_codes: Tuple[int],
) -> Generator[IOAction, Response, Tuple[Response, Source]]:
    cached_response, evaluation = yield from try_from_cache_policy(
        request, cacheable_methods
    )
    logger.debug(f"evaluation: {evaluation}")
    if cached_response and evaluation == Evaluation.GOOD:
        return cached_response, Source.CACHE

    response, source = yield from try_from_server_policy(
        request,
        cached_response,
        heuristic,
        cache_etags,
        cacheable_status_codes,
        cacheable_methods,
    )
    return response, source


def try_from_cache_policy(
    request: Request,
    cacheable_methods: Iterable[str],
) -> Generator[
    CacheAction,
    Tuple[Response, VaryData],
    Union[Tuple[Response, Evaluation], Tuple[None, None]],
]:
    """
    yield cache actions
    expects responses in return
    may finally return valid response as StopIteration value
    """
    # Will only yield GET or DELETE CacheActions. Does not write to cache.
    cache_key = get_cache_key(request)

    if request.method not in cacheable_methods:
        return None, None

    cc = parse_cache_control_directives(request.headers)

    # Bail out if the request insists on fresh data
    if "no-cache" in cc:
        logger.debug('Request header has "no-cache", cache bypassed')
        return None, None

    if cc.get("max-age") == 0:
        logger.debug('Request header has "max_age" as 0, cache bypassed')
        return None, None

    logger.debug(f'Looking up "{cache_key}" in the cache')
    cached_response: Optional[Response]
    cached_vary_data: dict
    cached_response, cached_vary_data = yield CacheGet(cache_key)
    if cached_response is None:
        logger.debug("No cache entry available")
        return None, None

    if not check_vary_headers(request.headers, cached_vary_data):
        logger.debug("Ignoring cache entry due to vary header mismatch")
        return None, None

    # If we have a cached permanent redirect, return it immediately. We
    # don't need to test our response for other headers b/c it is
    # intrinsically "cacheable" as it is Permanent.
    #
    # See:
    #   https://tools.ietf.org/html/rfc7231#section-6.4.2
    #
    # Client can try to refresh the value by repeating the request
    # with cache busting headers as usual (ie no-cache).
    if cached_response.status_code in PERMANENT_REDIRECT_STATUSES:
        msg = (
            "Returning cached permanent redirect response "
            "(ignoring date and etag information)"
        )
        logger.debug(msg)
        return cached_response, Evaluation.GOOD

    if "date" not in cached_response.headers:
        if "etag" not in cached_response.headers:
            # Without date or etag, the cached response can never be used
            # and should be deleted.
            logger.debug("Purging cached response: no date or etag")
            yield CacheDelete(cache_key)
            return None, None
        logger.debug("Ignoring cached response: no date")
        # TODO: Should this return None? Is the cached response now no longer relevant to this request?
        return cached_response, Evaluation.INCONCLUSIVE

    now = time.time()
    # TODO: parsedate_tz might return None (no date value or malformed)
    date = calendar.timegm(parsedate_tz(cached_response.headers["date"]))  # type: ignore
    current_age = max(0, now - date)
    logger.debug("Current age based on date: %i", current_age)

    resp_cc = parse_cache_control_directives(cached_response.headers)

    # determine freshness
    freshness_lifetime = 0

    # Check the max-age pragma in the cache control header
    if "max-age" in resp_cc:
        freshness_lifetime = resp_cc["max-age"]
        logger.debug("Freshness lifetime from max-age: %i", freshness_lifetime)
    # If there isn't a max-age, check for an expires header
    elif "expires" in cached_response.headers:
        expires = parsedate_tz(cached_response.headers["expires"])
        if expires is not None:
            expire_time = calendar.timegm(expires) - date  # type: ignore
            freshness_lifetime = max(0, expire_time)
            logger.debug("Freshness lifetime from expires: %i", freshness_lifetime)

    # Determine if we are setting freshness limit in the
    # request. Note, this overrides what was in the response.
    if "max-age" in cc:
        freshness_lifetime = cc["max-age"]
        logger.debug("Freshness lifetime from request max-age: %i", freshness_lifetime)

    if "min-fresh" in cc:
        min_fresh = cc["min-fresh"]
        # adjust our current age by our min fresh
        current_age += min_fresh
        logger.debug("Adjusted current age from min-fresh: %i", current_age)

    # Return entry if it is fresh enough
    if freshness_lifetime > current_age:
        logger.debug('The response is "fresh", returning cached response')
        logger.debug("%i > %i", freshness_lifetime, current_age)
        return cached_response, Evaluation.GOOD

    # we're not fresh. If we don't have an Etag, clear it out
    if "etag" not in cached_response.headers:
        logger.debug('The cached response is "stale" with no etag, purging')
        yield CacheDelete(cache_key)
        return None, None

    # No conclusive response yet.
    return cached_response, Evaluation.INCONCLUSIVE


def try_from_server_policy(
    request: Request,
    cached_response: Optional[Response],
    heuristic: BaseHeuristic,
    cache_etags: bool,
    cacheable_status_codes: Iterable[int],
    cacheable_methods: Iterable[str],
) -> Generator[IOAction, Response, Tuple[Response, Source]]:
    cache_key = get_cache_key(request)
    logger.debug("we have this from the cache:", cached_response)
    updated_headers = request.headers.copy()
    if cached_response:
        # Add conditional headers based on cached response
        for source, target in [
            ("etag", "If-None-Match"),
            ("last-modified", "If-Modified-Since"),
        ]:
            if source in cached_response.headers:
                updated_headers[target] = cached_response.headers[source]

    request = Request(
        method=request.method,
        url=request.url,
        headers=updated_headers,
        stream=request.stream,
    )
    server_response = yield MakeRequest(request)

    # See if we should invalidate the cache.
    if is_invalidating_method(request.method) and not codes.is_error(
        server_response.status_code
    ):
        yield CacheDelete(cache_key)

    if request.method not in cacheable_methods:
        return server_response, Source.SERVER

    # Check for any heuristics that might update headers
    # before trying to cache.
    if heuristic:
        # TODO: don't modify things, return things.
        heuristic.apply(server_response.headers, server_response.status_code)

    # apply any expiration heuristics
    if server_response.status_code == 304:
        # Make sure to clean up the ETag response stream just in case.
        # Compliant servers will not return a body with ETag responses
        yield CloseResponseStream(server_response)

        # We must have sent an ETag request. This could mean
        # that we've been expired already or that we simply
        # have an ETag. In either case, we want to try and
        # update the cache if that is the case.
        if cached_response:
            updated_cached_response = update_with_304_response(
                cached_response, new_response_headers=server_response.headers
            )
            vary_header_values = get_vary_headers(
                request.headers, updated_cached_response
            )
            yield CacheSet(cache_key, updated_cached_response, vary_header_values)
            return updated_cached_response, Source.CACHE

        return server_response, Source.SERVER

    # We have a new response, let's make any changes necessary to the cache (store/delete)
    cache_exists = bool(cached_response)
    cache_action = cache_response_action(
        request,
        server_response,
        cache_exists,
        cache_etags,
        cacheable_status_codes,
    )
    if cache_action:
        wrapped_stream_response = yield cache_action
        if wrapped_stream_response:
            server_response = wrapped_stream_response

    return server_response, Source.SERVER


def cache_response_action(
    request: Request,
    server_response: Response,
    cache_exists: bool,
    cache_etags: bool,
    cacheable_status_codes: Iterable[int],
) -> Optional[Union[CacheSet, CacheDelete]]:
    """
    Algorithm for caching responses.

    Does some checks on request and response and deletes cache if appropriate

    Then either:
    No cache
    Cache immediately with no body for redirects
    Cache with body, this must be deferred.

    Returns:
    May return a request that has had its stream wrapped to trigger caching once read.
    """
    cache_key = get_cache_key(request)

    # From httplib2: Don't cache 206's since we aren't going to
    #                handle byte range requests
    if server_response.status_code not in cacheable_status_codes:
        logger.debug(
            "Status code %s not in %s",
            server_response.status_code,
            cacheable_status_codes,
        )
        return None

    logger.debug('Updating cache with response from "%s"', cache_key)

    # TODO: Do this once on the request/response?
    cc_req = parse_cache_control_directives(request.headers)
    cc = parse_cache_control_directives(server_response.headers)

    # Delete it from the cache if we happen to have it stored there
    no_store = False
    if "no-store" in cc:
        no_store = True
        logger.debug('Response header has "no-store"')
    if "no-store" in cc_req:
        no_store = True
        logger.debug('Request header has "no-store"')
    if no_store and cache_exists:
        logger.debug('Purging existing cache entry to honor "no-store"')
        return CacheDelete(cache_key)
    if no_store:
        return None

    # https://tools.ietf.org/html/rfc7234#section-4.1:
    # A Vary header field-value of "*" always fails to match.
    # Storing such a response leads to a deserialization warning
    # during cache lookup and is not allowed to ever be served,
    # so storing it can be avoided.
    if "*" in server_response.headers.get("vary", ""):
        logger.debug('Response header has "Vary: *"')
        return None

    # If we've been given an etag, then keep the response
    if cache_etags and "etag" in server_response.headers:
        logger.debug("Caching due to etag")

    # Add to the cache any permanent redirects. We do this before looking
    # that the Date headers.
    elif int(server_response.status_code) in PERMANENT_REDIRECT_STATUSES:
        logger.debug("Caching permanent redirect")
        response_body = b""
        response = Response(
            server_response.status_code,
            server_response.headers,
            # TODO: This is naff, maybe we just use httpx.Response
            ByteStream(response_body),
        )
        vary_header_values = get_vary_headers(request.headers, response)
        return CacheSet(cache_key, response, vary_header_values)

    # Add to the cache if the response headers demand it. If there
    # is no date header then we can't do anything about expiring
    # the cache.
    elif "date" in server_response.headers:
        # cache when there is a max-age > 0
        if "max-age" in cc and cc["max-age"] > 0:
            logger.debug("Caching b/c date exists and max-age > 0")

        # If the request can expire, it means we should cache it
        # in the meantime.
        elif "expires" in server_response.headers:
            if server_response.headers["expires"]:
                logger.debug("Caching b/c of expires header")
        else:
            return None
    else:
        return None

    vary_header_values = get_vary_headers(request.headers, server_response)
    return CacheSet(cache_key, server_response, vary_header_values, deferred=True)


def get_cache_key(request: Request) -> str:
    return str(request.url)


def is_invalidating_method(method: str):
    return method in INVALIDATING_METHODS


def parse_cache_control_directives(headers: Headers):
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


def update_with_304_response(
    cached_response: Response, new_response_headers: Headers
) -> Response:
    """On a 304 we will get a new set of headers that we want to
    update our cached value with, assuming we have one.

    This should only ever be called when we've sent an ETag and
    gotten a 304 as the response.
    """
    updated_response = copy(cached_response)

    # Lets update our headers with the headers from the new request:
    # http://tools.ietf.org/html/draft-ietf-httpbis-p4-conditional-26#section-4.1
    #
    # The server isn't supposed to send headers that would make
    # the cached body invalid. But... just in case, we'll be sure
    # to strip out ones we know that might be problematic due to
    # typical assumptions.
    excluded_headers = ["content-length"]

    updated_response.headers.update(
        dict(
            (k, v)
            for k, v in new_response_headers.items()
            # TODO: Don't think .lower() is necessary
            if k.lower() not in excluded_headers
        )
    )

    # we want a 200 b/c we have content via the cache
    updated_response.status_code = 200

    return updated_response


def check_vary_headers(request_headers: Headers, cached_vary_data: dict) -> bool:
    """Verify our vary headers match."""
    # Ensure that the Vary headers for the cached response match our
    # request
    # TODO: this should not be here, no reason for request headers to be so deep in deserialization.
    for header, value in cached_vary_data.items():
        if request_headers.get(header, None) != value:
            return False

    return True


def get_vary_headers(request_headers: Headers, response: Response):
    """Get vary headers values for persisting in the cache for later checking"""
    vary = {}

    # Construct our vary headers
    if "vary" in response.headers:
        varied_headers = response.headers["vary"].split(",")
        for header in varied_headers:
            header = header.strip()
            header_value = request_headers.get(header, None)
            vary[header] = header_value

    return vary
