# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import calendar
import time
from datetime import datetime
from email.utils import formatdate, parsedate
from pprint import pprint

import httpx
import pytest
from httpx import Headers
from mock import Mock

from httpx_caching._heuristics import (
    TIME_FMT,
    BaseHeuristic,
    ExpiresAfterHeuristic,
    LastModifiedHeuristic,
    OneDayCacheHeuristic,
)
from tests.conftest import cache_hit, make_async_client

pytestmark = pytest.mark.asyncio


class TestHeuristicWithoutWarning(object):
    def setup(self):
        class NoopHeuristic(BaseHeuristic):
            warning = Mock()

            def update_headers(self, resp_headers, resp_status):
                return {}

        self.heuristic = NoopHeuristic()
        self.async_client = make_async_client(heuristic=self.heuristic)

    async def test_no_header_change_means_no_warning_header(self, url):
        the_url = url + "optional_cacheable_request"
        await self.async_client.get(the_url)

        assert not self.heuristic.warning.called


class TestHeuristicWith3xxResponse(object):
    def setup(self):
        class DummyHeuristic(BaseHeuristic):
            def update_headers(self, resp_headers, resp_status):
                return {"x-dummy-header": "foobar"}

        self.async_client = make_async_client(heuristic=DummyHeuristic())

    async def test_heuristic_applies_to_301(self, url):
        the_url = url + "permanent_redirect"
        resp = await self.async_client.get(the_url)
        assert "x-dummy-header" in resp.headers

    async def test_heuristic_applies_to_304(self, url):
        the_url = url + "conditional_get"
        resp = await self.async_client.get(the_url)
        assert "x-dummy-header" in resp.headers


class TestOneDayCache(object):
    def setup(self):
        self.async_client = make_async_client(heuristic=OneDayCacheHeuristic())

    async def test_cache_for_one_day(self, url):
        the_url = url + "optional_cacheable_request"
        r = await self.async_client.get(the_url)

        assert "expires" in r.headers
        assert "warning" in r.headers

        pprint(dict(r.headers))

        r = await self.async_client.get(the_url)
        pprint(dict(r.headers))
        assert cache_hit(r)


class TestExpiresAfter(object):
    def setup(self):
        self.async_client = make_async_client(heuristic=ExpiresAfterHeuristic(days=1))

    async def test_expires_after_one_day(self, url):
        the_url = url + "no_cache"
        resp = httpx.get(the_url)
        assert resp.headers["cache-control"] == "no-cache"

        r = await self.async_client.get(the_url)

        assert "expires" in r.headers
        assert "warning" in r.headers
        assert r.headers["cache-control"] == "public"

        r = await self.async_client.get(the_url)
        assert cache_hit(r)


class TestLastModified(object):
    def setup(self):
        self.async_client = make_async_client(heuristic=LastModifiedHeuristic())

    async def test_last_modified(self, url):
        the_url = url + "optional_cacheable_request"
        r = await self.async_client.get(the_url)

        assert "expires" in r.headers
        assert "warning" not in r.headers

        pprint(dict(r.headers))

        r = await self.async_client.get(the_url)
        pprint(dict(r.headers))
        assert cache_hit(r)


def datetime_to_header(dt):
    return formatdate(calendar.timegm(dt.timetuple()))


@pytest.mark.sync
class TestModifiedUnitTests(object):
    def last_modified(self, period):
        return time.strftime(TIME_FMT, time.gmtime(self.time_now - period))

    def setup(self):
        self.heuristic = LastModifiedHeuristic()
        self.time_now = time.time()
        day_in_seconds = 86400
        self.year_ago = self.last_modified(day_in_seconds * 365)
        self.week_ago = self.last_modified(day_in_seconds * 7)
        self.day_ago = self.last_modified(day_in_seconds)
        self.now = self.last_modified(0)

        # NOTE: We pass in a negative to get a positive... Probably
        #       should refactor.
        self.day_ahead = self.last_modified(-day_in_seconds)

    def test_no_expiry_is_inferred_when_no_last_modified_is_present(self):
        assert self.heuristic.update_headers({}, 200) == {}

    def test_expires_is_not_replaced_when_present(self):
        headers = {"Expires": self.day_ahead}
        assert self.heuristic.update_headers(Headers(headers), 200) == {}

    def test_last_modified_is_used(self):
        headers = {"Date": self.now, "Last-Modified": self.week_ago}
        modified = self.heuristic.update_headers(Headers(headers), 200)
        assert ["expires"] == list(modified.keys())
        assert datetime(*parsedate(modified["expires"])[:6]) > datetime.now()  # type: ignore

    def test_last_modified_is_not_used_when_cache_control_present(self):
        headers = {
            "Date": self.now,
            "Last-Modified": self.week_ago,
            "Cache-Control": "private",
        }

        assert self.heuristic.update_headers(Headers(headers), 200) == {}

    def test_last_modified_is_not_used_when_status_is_unknown(self):
        headers = {"Date": self.now, "Last-Modified": self.week_ago}
        status = 299
        assert self.heuristic.update_headers(Headers(headers), status) == {}

    def test_last_modified_is_used_when_cache_control_public(self):
        headers = {
            "Date": self.now,
            "Last-Modified": self.week_ago,
            "Cache-Control": "public",
        }
        modified = self.heuristic.update_headers(Headers(headers), 200)
        assert ["expires"] == list(modified.keys())
        assert datetime(*parsedate(modified["expires"])[:6]) > datetime.now()  # type: ignore

    def test_expiry_is_no_more_than_twenty_four_hours(self):
        headers = {"Date": self.now, "Last-Modified": self.year_ago}
        modified = self.heuristic.update_headers(Headers(headers), 200)
        assert ["expires"] == list(modified.keys())
        assert self.day_ahead == modified["expires"]
