# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import calendar
import time
from datetime import datetime, timedelta
from email.utils import formatdate, parsedate, parsedate_tz

TIME_FMT = "%a, %d %b %Y %H:%M:%S GMT"


def expire_after(delta, date=None):
    date = date or datetime.utcnow()
    return date + delta


def datetime_to_header(dt):
    return formatdate(calendar.timegm(dt.timetuple()))


class BaseHeuristic(object):
    def warning(self):
        """
        Return a valid 1xx warning header value describing the cache
        adjustments.

        The response is provided too allow warnings like 113
        http://tools.ietf.org/html/rfc7234#section-5.5.4 where we need
        to explicitly say response is over 24 hours old.
        """
        return '110 - "Response is Stale"'

    def update_headers(self, response_headers, response_status):
        """Update the response headers with any new headers.

        NOTE: This SHOULD always include some Warning header to
              signify that the response was cached by the client, not
              by way of the provided headers.
        """
        return {}

    def apply(self, response_headers, response_status):
        updated_headers = self.update_headers(response_headers, response_status)

        if updated_headers:
            response_headers.update(updated_headers)
            warning_header_value = self.warning()
            if warning_header_value is not None:
                response_headers.update({"Warning": warning_header_value})


class OneDayCacheHeuristic(BaseHeuristic):
    """
    Cache the response by providing an expires 1 day in the
    future.
    """

    def update_headers(self, response_headers, response_status):
        headers = {}

        if "expires" not in response_headers:
            date = parsedate(response_headers["date"])
            expires = expire_after(timedelta(days=1), date=datetime(*date[:6]))
            headers["expires"] = datetime_to_header(expires)
            headers["cache-control"] = "public"
        return headers


class ExpiresAfterHeuristic(BaseHeuristic):
    """
    Cache **all** requests for a defined time period.
    """

    def __init__(self, **kw):
        self.delta = timedelta(**kw)

    def update_headers(self, response_headers, response_status):
        expires = expire_after(self.delta)
        return {"expires": datetime_to_header(expires), "cache-control": "public"}

    def warning(self):
        tmpl = "110 - Automatically cached for %s. Response might be stale"
        return tmpl % self.delta


class LastModifiedHeuristic(BaseHeuristic):
    """
    If there is no Expires header already, fall back on Last-Modified
    using the heuristic from
    http://tools.ietf.org/html/rfc7234#section-4.2.2
    to calculate a reasonable value.

    Firefox also does something like this per
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching_FAQ
    http://lxr.mozilla.org/mozilla-release/source/netwerk/protocol/http/nsHttpResponseHead.cpp#397
    Unlike mozilla we limit this to 24-hr.
    """

    cacheable_by_default_statuses = {
        200,
        203,
        204,
        206,
        300,
        301,
        404,
        405,
        410,
        414,
        501,
    }

    def update_headers(self, response_headers, response_status):
        if "expires" in response_headers:
            return {}

        if (
            "cache-control" in response_headers
            and response_headers["cache-control"] != "public"
        ):
            return {}

        if response_status not in self.cacheable_by_default_statuses:
            return {}

        if "date" not in response_headers or "last-modified" not in response_headers:
            return {}

        date = calendar.timegm(parsedate_tz(response_headers["date"]))
        last_modified = parsedate(response_headers["last-modified"])
        if date is None or last_modified is None:
            return {}

        now = time.time()
        current_age = max(0, now - date)
        delta = date - calendar.timegm(last_modified)
        freshness_lifetime = max(0, min(delta / 10, 24 * 3600))
        if freshness_lifetime <= current_age:
            return {}

        expires = date + freshness_lifetime
        return {"expires": time.strftime(TIME_FMT, time.gmtime(expires))}

    def warning(self):
        return None
