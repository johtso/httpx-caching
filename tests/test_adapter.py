# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import mock
import pytest

from httpx import Client
from cachecontrol.transport import CacheControlTransport
from cachecontrol.cache import DictCache


class TestClientActions(object):

    def test_get_caches(self, url, client):
        r2 = client.get(url)
        assert r2.from_cache is True

    def test_get_with_no_cache_does_not_cache(self, url, client):
        r2 = client.get(url, headers={"Cache-Control": "no-cache"})
        assert not r2.from_cache

    def test_put_invalidates_cache(self, url, client):
        r2 = client.put(url, data={"foo": "bar"})
        client.get(url)
        assert not r2.from_cache

    def test_patch_invalidates_cache(self, url, client):
        r2 = client.patch(url, data={"foo": "bar"})
        client.get(url)
        assert not r2.from_cache

    def test_delete_invalidates_cache(self, url, client):
        r2 = client.delete(url)
        client.get(url)
        assert not r2.from_cache

    def test_close(self):
        cache = mock.Mock(spec=DictCache)
        client = Client(transport=CacheControlTransport(cache))

        client.close()
        assert cache.close.called
