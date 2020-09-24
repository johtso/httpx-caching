# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import msgpack
import httpx

from mock import Mock

from cachecontrol.serialize import Serializer
from cachecontrol.models import Response


class TestSerializer(object):
    def setup(self):
        self.serializer = Serializer()
        self.response_data = {
            "response": {
                "body": "Hello World",
                "headers": {
                    "Content-Type": "text/plain",
                    "Expires": "87654",
                    "Cache-Control": "public",
                },
                "status_code": 200,
                "ext": {},
            },
            "vary": {},
        }

    def test_read_version_v0(self):
        req = Mock()
        resp = self.serializer._loads_v0(req, msgpack.dumps(self.response_data))
        assert resp.stream._content == "Hello World"

    def test_dumps(self):
        assert self.serializer.dumps(
            httpx.Headers({"vary": "foo"}),
            Response(200, httpx.Headers(), "foo", {}),
            "foo",
        )
