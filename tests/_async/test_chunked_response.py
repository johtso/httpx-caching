# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0
"""
Test for supporting streamed responses (Transfer-Encoding: chunked)
"""
import pytest

from tests.conftest import cache_hit

pytestmark = pytest.mark.asyncio


class TestChunkedResponses(object):
    async def test_cache_chunked_response(self, url, async_client):
        """
        Verify that an otherwise cacheable response is cached when the
        response is chunked.
        """
        url = url + "stream"
        r = await async_client.get(url)
        from pprint import pprint

        pprint(dict(r.headers))
        pprint(dict(r.request.headers))
        print(r.content)
        assert r.headers.get("transfer-encoding") == "chunked"

        r = await async_client.get(url, headers={"Cache-Control": "max-age=3600"})
        assert cache_hit(r)

    async def test_stream_is_cached(self, url, async_client):
        async with async_client.stream("GET", url + "stream") as resp_1:
            content_1 = await resp_1.aread()

        async with async_client.stream("GET", url + "stream") as resp_2:
            content_2 = await resp_2.aread()

        assert not cache_hit(resp_1)
        assert cache_hit(resp_2)
        assert content_1 == content_2

    @pytest.mark.xfail
    async def test_stream_is_not_cached_when_content_is_not_read(
        self, url, async_client
    ):
        # TODO: Is this really relevant with httpx?
        async with async_client.stream("GET", url + "stream"):
            pass
        async with async_client.stream("GET", url + "stream") as resp:
            assert not cache_hit(resp)
