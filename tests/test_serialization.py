# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import msgpack
import httpx

from mock import Mock

from cachecontrol.serialize import Serializer


class TestSerializer(object):

    def setup(self):
        self.serializer = Serializer()
        self.response_data = {
            u"response": {
                # Encode the body as bytes b/c it will eventually be
                # converted back into a BytesIO object.
                u"body": "Hello World".encode("utf-8"),
                u"headers": {
                    u"Content-Type": u"text/plain",
                    u"Expires": u"87654",
                    u"Cache-Control": u"public",
                },
                u"status": 200,
                u"version": 11,
                u"reason": u"",
                u"strict": True,
                u"decode_content": True,
            }
        }

    def test_read_version_v0(self):
        req = Mock()
        resp = self.serializer._loads_v0(req, msgpack.dumps(self.response_data))
        # We have to decode our urllib3 data back into a unicode string.
        assert resp.data == "Hello World".encode("utf-8")

    def test_read_latest_version_streamable(self, url):
        original_resp = httpx.get(url, stream=True)
        req = original_resp.request

        resp = self.serializer.loads(req, self.serializer.dumps(req, original_resp.raw, original_resp.content))

        assert resp.read()

    def test_read_latest_version(self, url):
        original_resp = httpx.get(url)
        data = original_resp.content
        req = original_resp.request

        resp = self.serializer.loads(
            req, self.serializer.dumps(req, original_resp.raw, data)
        )

        assert resp.read() == data

    def test_no_vary_header(self, url):
        original_resp = httpx.get(url)
        data = original_resp.content
        req = original_resp.request

        # We make sure our response has a Vary header and that the
        # request doesn't have the header.
        original_resp.raw.headers["vary"] = "Foo"

        assert self.serializer.loads(
            req, self.serializer.dumps(req, original_resp.raw, data)
        )
