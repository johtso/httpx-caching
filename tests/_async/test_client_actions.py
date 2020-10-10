# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import mock
import pytest

from httpx_caching import AsyncDictCache
from tests.conftest import cache_hit

pytestmark = pytest.mark.asyncio


class TestClientActions(object):
    async def test_get_caches(self, url, async_client):
        await async_client.get(url)
        r2 = await async_client.get(url)
        assert cache_hit(r2)

    async def test_get_with_no_cache_does_not_cache(self, url, async_client):
        await async_client.get(url)
        r2 = await async_client.get(url, headers={"Cache-Control": "no-cache"})
        assert not cache_hit(r2)

    async def test_put_invalidates_cache(self, url, async_client):
        await async_client.get(url)
        await async_client.put(url, data={"foo": "bar"})
        r3 = await async_client.get(url)
        assert not cache_hit(r3)

    async def test_patch_invalidates_cache(self, url, async_client):
        await async_client.get(url)
        await async_client.patch(url, data={"foo": "bar"})
        r3 = await async_client.get(url)
        assert not cache_hit(r3)

    async def test_delete_invalidates_cache(self, url, async_client):
        await async_client.get(url)
        await async_client.delete(url)
        r3 = await async_client.get(url)
        assert not cache_hit(r3)

    @pytest.mark.xfail
    async def test_close(self, url, async_client):
        mock_cache = mock.Mock(spec=AsyncDictCache)
        async_client._transport.cache = mock_cache

        # TODO: httpx does not close transport if nothing has been done with the client
        # await async_client.get(url)

        await async_client.aclose()
        assert mock_cache.close.called
