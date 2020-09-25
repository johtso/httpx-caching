# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

"""
Test for supporting redirect caches as needed.
"""
import pytest

from tests.conftest import cache_hit, make_async_client

pytestmark = pytest.mark.asyncio


class TestPermanentRedirects(object):
    def setup(self):
        self.async_client = make_async_client()

    async def test_redirect_response_is_cached(self, url):
        await self.async_client.get(url + "permanent_redirect", allow_redirects=False)

        resp = await self.async_client.get(
            url + "permanent_redirect", allow_redirects=False
        )
        assert cache_hit(resp)

    async def test_bust_cache_on_redirect(self, url):
        await self.async_client.get(url + "permanent_redirect", allow_redirects=False)

        resp = await self.async_client.get(
            url + "permanent_redirect",
            headers={"cache-control": "no-cache"},
            allow_redirects=False,
        )
        assert not cache_hit(resp)


class TestMultipleChoicesRedirects(object):
    def setup(self):
        self.async_client = make_async_client()

    async def test_multiple_choices_is_cacheable(self, url):
        await self.async_client.get(
            url + "multiple_choices_redirect", allow_redirects=False
        )

        resp = await self.async_client.get(
            url + "multiple_choices_redirect", allow_redirects=False
        )

        assert cache_hit(resp)

    async def test_bust_cache_on_redirect(self, url):
        await self.async_client.get(
            url + "multiple_choices_redirect", allow_redirects=False
        )

        resp = await self.async_client.get(
            url + "multiple_choices_redirect",
            headers={"cache-control": "no-cache"},
            allow_redirects=False,
        )

        assert not cache_hit(resp)
