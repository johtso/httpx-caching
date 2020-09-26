# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0
from typing import Optional, Tuple

import httpcore
import msgpack

from ._models import Response


class Serializer(object):
    def dumps(self, response: Response, vary_header_data: dict, response_body: bytes):
        # TODO: kludge while we put unserializable requests in ext
        ext = response.ext.copy()
        ext.pop("real_request", None)

        data = {
            "response": {
                "body": response_body,
                "headers": response.headers.raw,
                "status_code": response.status_code,
                # TODO: Make sure we don't explode if there's something naughty in ext
                "ext": ext,
            },
            "vary": vary_header_data,
        }

        return b",".join([b"cc=0", msgpack.dumps(data, use_bin_type=True)])

    def loads(self, data: bytes) -> Tuple[Optional[Response], Optional[dict]]:
        # Short circuit if we've been given an empty set of data
        if not data:
            return None, None

        # Determine what version of the serializer the data was serialized
        # with
        try:
            ver, data = data.split(b",", 1)
        except ValueError:
            ver = b"cc=0"

        # Make sure that our "ver" is actually a version and isn't a false
        # positive from a , being in the data stream.
        if ver[:3] != b"cc=":
            data = ver + data
            ver = b"cc=0"

        # Get the version number out of the cc=N
        version = ver.split(b"=", 1)[-1].decode("ascii")

        # Dispatch to the actual load method for the given version
        try:
            return getattr(self, "_loads_v{}".format(version))(data)

        except AttributeError:
            # This is a version we don't have a loads function for, so we'll
            # just treat it as a miss and return None
            return None, None

    def prepare_response(self, cached_data: dict):
        """Construct a response from cached data"""

        cached_response = cached_data["response"]

        status_code = cached_response["status_code"]
        headers = cached_response["headers"]
        stream = httpcore.PlainByteStream(cached_response["body"])
        ext = cached_response["ext"]

        response = Response.from_raw((status_code, headers, stream, ext))

        if response.headers.get("transfer-encoding", "") == "chunked":
            response.headers.pop("transfer-encoding")

        return response, cached_data["vary"]

    def _loads_v0(self, data):
        try:
            cached = msgpack.loads(data, raw=False)
        except ValueError:
            return

        return self.prepare_response(cached)
