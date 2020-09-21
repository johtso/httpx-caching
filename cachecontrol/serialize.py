# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import msgpack
import httpcore
from httpx import Headers


class Serializer(object):

    def dumps(
            self,
            request_headers,
            response_headers,
            response_status_code,
            response_http_version,
            response_reason_phrase,
            body
            ):
        # TODO: What was decode_content and strict flag caching about?

        response_headers = response_headers.copy()

        data = {
            "response": {
                "body": body,
                "headers": response_headers.raw,
                "status_code": response_status_code,
                "http_version": response_http_version,
                "reason_phrase": response_reason_phrase,
            },
            "vary": {}
        }

        # Construct our vary headers
        if "vary" in response_headers:
            varied_headers = response_headers["vary"].split(",")
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
        """Verify our vary headers match and return response values.
        """
        # Ensure that the Vary headers for the cached response match our
        # request
        for header, value in cached.get("vary", {}).items():
            if request_headers.get(header, None) != value:
                return

        cached_response = cached["response"]

        headers = Headers(cached_response["headers"])
        if headers.get("transfer-encoding", "") == "chunked":
            headers.pop("transfer-encoding")

        http_version = cached_response["http_version"]
        reason_phrase = cached_response["reason_phrase"]
        status_code = cached_response["status_code"]

        body = httpcore.PlainByteStream(cached_response["body"])

        return http_version, status_code, reason_phrase, headers, body

    def _loads_v0(self, request_headers, data):
        try:
            cached = msgpack.loads(data, raw=False)
        except ValueError:
            return

        return self.prepare_response(request_headers, cached)
