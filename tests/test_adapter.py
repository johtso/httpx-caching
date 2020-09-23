# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import mock

from cachecontrol.cache import DictCache

from .conftest import cache_hit


class TestClientActions(object):

    def test_get_caches(self, url, client):
        client.get(url)
        print(client._transport.cache.data)
        r2 = client.get(url)
        assert cache_hit(r2)

    def test_get_with_no_cache_does_not_cache(self, url, client):
        client.get(url)
        r2 = client.get(url, headers={"Cache-Control": "no-cache"})
        assert not cache_hit(r2)

    def test_put_invalidates_cache(self, url, client):
        client.get(url)
        r2 = client.put(url, data={"foo": "bar"})
        client.get(url)
        assert not cache_hit(r2)

    def test_patch_invalidates_cache(self, url, client):
        client.get(url)
        r2 = client.patch(url, data={"foo": "bar"})
        client.get(url)
        assert not cache_hit(r2)

    def test_delete_invalidates_cache(self, url, client):
        client.get(url)
        r2 = client.delete(url)
        client.get(url)
        assert not cache_hit(r2)

    def test_close(self, url, client):
        mock_cache = mock.Mock(spec=DictCache)
        client._transport.cache = mock_cache

        # TODO: httpx does not close transport if nothing has been done with the client
        # client.get(url)

        client.close()
        assert mock_cache.close.called
