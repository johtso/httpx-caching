# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import print_function

import pytest
from freezegun import freeze_time

from .conftest import cache_hit, make_client


class TestMaxAge(object):
    @pytest.fixture()
    def client(self, url):
        self.url = url
        client = make_client()

        return client

    def test_client_max_age_0(self, client):
        """
        Making sure when the client uses max-age=0 we don't get a
        cached copy even though we're still fresh.
        """
        cache = client._transport.cache

        print("first request")
        r = client.get(self.url)
        assert cache.get(self.url)

        print("second request")
        r = client.get(self.url, headers={"Cache-Control": "max-age=0"})

        # don't remove from the cache
        assert cache.get(self.url)
        assert not cache_hit(r)

    def test_client_max_age_3600(self, client):
        """
        Verify we get a cached value when the client has a
        reasonable max-age value.
        """
        cache = client._transport.cache
        with freeze_time("2012-01-14"):
            r = client.get(self.url)
            assert cache.get(self.url)

            # request that we don't want a new one unless
            r = client.get(self.url, headers={"Cache-Control": "max-age=3600"})
            assert cache_hit(r)

        # now lets grab one that forces a new request b/c the cache has expired
        r = client.get(self.url)
        assert not cache_hit(r)
