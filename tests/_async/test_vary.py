# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

from urllib.parse import urljoin

import pytest

from httpx_caching import AsyncDictCache
from tests.conftest import cache_hit, make_async_client

pytestmark = pytest.mark.asyncio


class TestVary(object):
    @pytest.fixture()
    def cache(self):
        return AsyncDictCache()

    @pytest.fixture()
    async def async_client(self, cache):
        async_client = make_async_client(cache=cache)
        yield async_client
        await async_client.aclose()

    def assert_cached_equal(self, cached, resp):
        print(cached, resp)
        # remove any transfer-encoding headers as they don't apply to
        # a cached value
        if "chunked" in resp.headers.get("transfer-encoding", ""):
            resp.headers.pop("transfer-encoding")

        assert [cached.stream.read(), cached.headers, cached.status_code] == [
            resp.content,
            resp.headers,
            resp.status_code,
        ]

    async def test_vary_example(self, async_client, cache, url):
        """RFC 2616 13.6

        When the cache receives a subsequent request whose Request-URI
        specifies one or more cache entries including a Vary header field,
        the cache MUST NOT use such a cache entry to construct a response
        to the new request unless all of the selecting request-headers
        present in the new request match the corresponding stored
        request-headers in the original request.

        Or, in simpler terms, when you make a request and the server
        returns defines a Vary header, unless all the headers listed
        in the Vary header are the same, it won't use the cached
        value.
        """
        vary_url = urljoin(url, "/vary_accept")

        r = await async_client.get(vary_url, headers={"foo": "a"})
        cached_response, _vary_data = await cache.aget(vary_url)

        # make the same request
        resp = await async_client.get(vary_url, headers={"foo": "b"})
        assert cache_hit(resp)

        # make a similar request, changing the accept header
        resp = await async_client.get(
            vary_url, headers={"Accept": "text/plain, text/html", "foo": "c"}
        )

        with pytest.raises(AssertionError):
            self.assert_cached_equal(cached_response, resp)
        assert not cache_hit(resp)

        # Just confirming two things here:
        #
        #   1) The server used the vary header
        #   2) We have more than one header we vary on
        #
        # The reason for this is that when we don't specify the header
        # in the request, it is considered the same in terms of
        # whether or not to use the cached value.
        assert "vary" in r.headers
        assert len(r.headers["vary"].replace(" ", "").split(",")) == 2
