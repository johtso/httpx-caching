# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import httpx


def test_http11(url):
    resp = httpx.get(url)

    # Making sure our test server speaks HTTP/1.1
    assert resp.http_version == "HTTP/1.1"
