# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import httpcore
import msgpack

from ._models import Response


class Serializer(object):
    def dumps(self, request_headers, response, response_body):
        # TODO: kludge while we put unserializable requests in ext
        ext = response.ext.copy()
        ext.pop("real_request", None)

        if isinstance(response_body, httpcore.PlainByteStream):
            response_body = response_body._content

        data = {
            "response": {
                "body": response_body,
                "headers": response.headers.raw,
                "status_code": response.status_code,
                # TODO: Make sure we don't explode if there's something naughty in ext
                "ext": ext,
            },
            "vary": {},
        }

        # Construct our vary headers
        if "vary" in response.headers:
            varied_headers = response.headers["vary"].split(",")
            for header in varied_headers:
                header = header.strip()
                header_value = request_headers.get(header, None)
                data["vary"][header] = header_value

        return b",".join([b"cc=0", msgpack.dumps(data, use_bin_type=True)])

    def loads(self, request_headers, data):
        # Short circuit if we've been given an empty set of data
        if not data:
            return

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
        ver = ver.split(b"=", 1)[-1].decode("ascii")

        # Dispatch to the actual load method for the given version
        try:
            return getattr(self, "_loads_v{}".format(ver))(request_headers, data)

        except AttributeError:
            # This is a version we don't have a loads function for, so we'll
            # just treat it as a miss and return None
            return

    def prepare_response(self, request_headers, cached):
        """Verify our vary headers match and return response values."""
        # Ensure that the Vary headers for the cached response match our
        # request
        # TODO: this should not be here, no reason for request headers to be so deep in deserialization.
        for header, value in cached.get("vary", {}).items():
            if request_headers.get(header, None) != value:
                return

        cached_response = cached["response"]

        status_code = cached_response["status_code"]
        headers = cached_response["headers"]
        stream = httpcore.PlainByteStream(cached_response["body"])
        ext = cached_response["ext"]

        response = Response.from_raw((status_code, headers, stream, ext))

        if response.headers.get("transfer-encoding", "") == "chunked":
            response.headers.pop("transfer-encoding")

        return response

    def _loads_v0(self, request_headers, data):
        try:
            cached = msgpack.loads(data, raw=False)
        except ValueError:
            return

        return self.prepare_response(request_headers, cached)
