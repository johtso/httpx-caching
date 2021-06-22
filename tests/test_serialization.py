# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import msgpack

from httpx_caching._models import Response
from httpx_caching._serializer import Serializer


class TestSerializer(object):
    def setup(self):
        self.serializer = Serializer()
        self.response_data = {
            "response": {
                "body": b"Hello World",
                "headers": {
                    "Content-Type": "text/plain",
                    "Expires": "87654",
                    "Cache-Control": "public",
                },
                "status_code": 200,
                "extensions": {},
            },
            "vary": {},
        }

    def test_read_version_v0(self):
        resp, _vary_fields = self.serializer._loads_v0(
            msgpack.dumps(self.response_data)
        )
        assert resp.stream.read() == b"Hello World"

    def test_dumps(self):
        assert self.serializer.dumps(
            Response.from_raw((200, {}, b"foo", {})),
            {},
            b"foo",
        )
