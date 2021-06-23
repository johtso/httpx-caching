# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0


import pytest
from freezegun import freeze_time
from httpx import AsyncClient, Limits, Request, Timeout

from httpx_caching import AsyncCachingTransport, AsyncDictCache
from tests.conftest import cache_hit, raw_resp

pytestmark = pytest.mark.asyncio


def get_last_request(client):
    (
        method,
        url,
        headers,
        stream,
        _ext,
    ) = client._transport.transport.handle_async_request.call_args[0]
    return Request(
        method=method,
        url=url,
        headers=headers,
        stream=stream,
    )


@pytest.fixture()
async def async_client(mocker):
    async_client = AsyncClient()
    transport = AsyncCachingTransport(
        transport=async_client._transport,
        cache=AsyncDictCache(),
    )
    async_client._transport = transport

    mocker.patch.object(
        transport.transport,
        "handle_async_request",
        wraps=transport.transport.handle_async_request,
    )

    yield async_client

    await async_client.aclose()


class TestETag(object):
    """Test our equal priority caching with ETags

    Equal Priority Caching is a term I've defined to describe when
    ETags are cached orthgonally from Time Based Caching.
    """

    async def test_etags_get_example(self, async_client, url):
        """RFC 2616 14.26

        The If-None-Match request-header field is used with a method to make
        it conditional. A client that has one or more entities previously
        obtained from the resource can verify that none of those entities
        is current by including a list of their associated entity tags in
        the If-None-Match header field. The purpose of this feature is to
        allow efficient updates of cached information with a minimum amount
        of transaction overhead

        If any of the entity tags match the entity tag of the entity that
        would have been returned in the response to a similar GET request
        (without the If-None-Match header) on that resource, [...] then
        the server MUST NOT perform the requested method, [...]. Instead, if
        the request method was GET or HEAD, the server SHOULD respond with
        a 304 (Not Modified) response, including the cache-related header
        fields (particularly ETag) of one of the entities that matched.

        (Paraphrased) A server may provide an ETag header on a response. On
        subsequent queries, the client may reference the value of this Etag
        header in an If-None-Match header; on receiving such a header, the
        server can check whether the entity at that URL has changed from the
        clients last version, and if not, it can return a 304 to indicate
        the client can use it's current representation.
        """
        r1 = await async_client.get(url + "etag")
        # make sure we cached it
        assert await async_client._transport.cache.aget(url + "etag")

        # make the same request
        r2 = await async_client.get(url + "etag")
        assert cache_hit(r2)
        assert raw_resp(r2) == raw_resp(r1)

        # make the same request a 3rd time to make sure we don't mess anything up
        # after a cache hit
        r3 = await async_client.get(url + "etag")
        assert cache_hit(r3)
        assert raw_resp(r3) == raw_resp(r1)

        # tell the server to change the etags of the response
        await async_client.get(url + "update_etag")

        r4 = await async_client.get(url + "etag")
        assert not cache_hit(r4)
        assert raw_resp(r4) != raw_resp(r1)

        r5 = await async_client.get(url + "etag")
        assert cache_hit(r5)
        assert raw_resp(r5) == raw_resp(r4)


class TestDisabledETags(object):
    """Test our use of ETags when the response is stale and the
    response has an ETag.
    """

    async def test_expired_etags_if_none_match_response(self, async_client, url):
        """Make sure an expired response that contains an ETag uses
        the If-None-Match header.
        """
        # Cache an old etag response
        with freeze_time("2012-01-14"):
            await async_client.get(url + "etag")

        assert await async_client._transport.cache.aget(url + "etag")

        r2 = await async_client.get(url + "etag")
        assert cache_hit(r2)

        real_request = get_last_request(async_client)
        assert "if-none-match" in real_request.headers
        assert r2.status_code == 200


class TestReleaseConnection(object):
    """
    On 304s we still make a request using our connection pool, yet
    we do not call the parent adapter, which releases the connection
    back to the pool. This test ensures that when the parent `get`
    method is not called we consume the response (which should be
    empty according to the HTTP spec) and release the connection.
    """

    @pytest.mark.timeout(5)
    async def test_not_modified_releases_connection(self, url):
        async_client = AsyncClient(
            timeout=Timeout(1, pool=0.1),
            limits=Limits(max_connections=1, max_keepalive_connections=1),
        )
        async_client._transport = AsyncCachingTransport(
            transport=async_client._transport,
        )

        # make sure the pool doesn't time out
        for _i in range(3):
            await async_client.get(url + "etag")

        await async_client.aclose()
