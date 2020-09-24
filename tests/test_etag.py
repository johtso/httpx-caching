# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

from urllib.parse import urljoin

import pytest
from freezegun import freeze_time
from httpx import Client, Limits, Timeout

from cachecontrol import SyncHTTPCacheTransport
from cachecontrol.cache import DictCache
from cachecontrol.models import Response

from .conftest import cache_hit, raw_resp


def assert_in_cache(cache, url, response):
    assert cache.get(url) == raw_resp(response)


class TestETag(object):
    """Test our equal priority caching with ETags

    Equal Priority Caching is a term I've defined to describe when
    ETags are cached orthgonally from Time Based Caching.
    """

    @pytest.fixture()
    def client(self, url):
        self.etag_url = urljoin(url, "/etag")
        self.update_etag_url = urljoin(url, "/update_etag")
        self.cache = DictCache()
        client = Client()
        client._transport = SyncHTTPCacheTransport(
            transport=client._transport,
            cache=self.cache,
        )

        yield client

        client.close()

    def test_etags_get_example(self, client, server):
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
        r1 = client.get(self.etag_url)
        # make sure we cached it
        assert self.cache.get(self.etag_url)

        # make the same request
        r2 = client.get(self.etag_url)
        assert raw_resp(r2) == raw_resp(r1)
        assert cache_hit(r2)

        # tell the server to change the etags of the response
        client.get(self.update_etag_url)

        r3 = client.get(self.etag_url)
        assert raw_resp(r3) != raw_resp(r1)
        assert not cache_hit(r3)

        r4 = client.get(self.etag_url)
        assert raw_resp(r4) == raw_resp(r3)
        assert cache_hit(r4)


class TestDisabledETags(object):
    """Test our use of ETags when the response is stale and the
    response has an ETag.
    """

    @pytest.fixture()
    def client(self, server, url):
        self.etag_url = urljoin(url, "/etag")
        self.update_etag_url = urljoin(url, "/update_etag")
        self.cache = DictCache()

        client = Client()
        client._transport = SyncHTTPCacheTransport(
            transport=client._transport,
            cache=self.cache,
        )

        return client

    def test_expired_etags_if_none_match_response(self, client):
        """Make sure an expired response that contains an ETag uses
        the If-None-Match header.
        """
        # Cache an old etag response
        with freeze_time("2012-01-14"):
            client.get(self.etag_url)

        assert self.cache.get(self.etag_url)

        r2 = client.get(self.etag_url)
        assert cache_hit(r2)

        real_request = r2.ext["real_request"]
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

    def test_not_modified_releases_connection(self, server, url):
        self.etag_url = urljoin(url, "/etag")

        client = Client(
            timeout=Timeout(1, pool=0.1),
            limits=Limits(max_connections=1, max_keepalive_connections=1),
        )
        client._transport = SyncHTTPCacheTransport(
            transport=client._transport,
        )

        # make sure the pool doesn't time out
        for i in range(3):
            client.get(self.etag_url)
