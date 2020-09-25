# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

"""
Test for supporting redirect caches as needed.
"""
from .conftest import cache_hit, make_client


class TestPermanentRedirects(object):
    def setup(self):
        self.client = make_client()

    def test_redirect_response_is_cached(self, url):
        self.client.get(url + "permanent_redirect", allow_redirects=False)

        resp = self.client.get(url + "permanent_redirect", allow_redirects=False)
        assert cache_hit(resp)

    def test_bust_cache_on_redirect(self, url):
        self.client.get(url + "permanent_redirect", allow_redirects=False)

        resp = self.client.get(
            url + "permanent_redirect",
            headers={"cache-control": "no-cache"},
            allow_redirects=False,
        )
        assert not cache_hit(resp)


class TestMultipleChoicesRedirects(object):
    def setup(self):
        self.client = make_client()

    def test_multiple_choices_is_cacheable(self, url):
        self.client.get(url + "multiple_choices_redirect", allow_redirects=False)

        resp = self.client.get(url + "multiple_choices_redirect", allow_redirects=False)

        assert cache_hit(resp)

    def test_bust_cache_on_redirect(self, url):
        self.client.get(url + "multiple_choices_redirect", allow_redirects=False)

        resp = self.client.get(
            url + "multiple_choices_redirect",
            headers={"cache-control": "no-cache"},
            allow_redirects=False,
        )

        assert not cache_hit(resp)
