# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0
"""
Test for supporting streamed responses (Transfer-Encoding: chunked)
"""
from __future__ import print_function, unicode_literals

from .conftest import cache_hit


class TestChunkedResponses(object):
    def test_cache_chunked_response(self, url, client):
        """
        Verify that an otherwise cacheable response is cached when the
        response is chunked.
        """
        url = url + "stream"
        r = client.get(url)
        from pprint import pprint

        pprint(dict(r.headers))
        pprint(dict(r.request.headers))
        print(r.content)
        assert r.headers.get("transfer-encoding") == "chunked"

        r = client.get(url, headers={"Cache-Control": "max-age=3600"})
        assert cache_hit(r)

    def test_stream_is_cached(self, url, client):
        resp_1 = client.get(url + "stream")
        content_1 = resp_1.content

        resp_2 = client.get(url + "stream")
        content_2 = resp_1.content

        assert not cache_hit(resp_1)
        assert cache_hit(resp_2)
        assert content_1 == content_2

    def test_stream_is_not_cached_when_content_is_not_read(self, url, client):
        # TODO: Is this really relevant with httpx?
        client.stream("GET", url + "stream")
        with client.stream("GET", url + "stream") as resp:
            assert not cache_hit(resp)
