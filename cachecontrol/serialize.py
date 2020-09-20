# SPDX-FileCopyrightText: 2015 Eric Larson
#
# SPDX-License-Identifier: Apache-2.0

import io

import msgpack
from httpx import Headers, Response


class Serializer(object):

    def dumps(self, request, response, body):
        response_headers = Headers(response.headers)

        # NOTE: This is all a bit weird, but it's really important that on
        #       Python 2.x these objects are unicode and not str, even when
        #       they contain only ascii. The problem here is that msgpack
        #       understands the difference between unicode and bytes and we
        #       have it set to differentiate between them, however Python 2
        #       doesn't know the difference. Forcing these to unicode will be
        #       enough to have msgpack know the difference.
        data = {
            u"response": {
                u"body": body,
                u"headers": dict(
                    (text_type(k), text_type(v)) for k, v in response.headers.items()
                ),
                u"status": response.status,
                u"version": response.version,
                u"reason": text_type(response.reason),
                u"strict": response.strict,
                u"decode_content": response.decode_content,
            }
        }

        # Construct our vary headers
        data[u"vary"] = {}
        if u"vary" in response_headers:
            varied_headers = response_headers[u"vary"].split(",")
            for header in varied_headers:
                header = text_type(header).strip()
                header_value = request.headers.get(header, None)
                if header_value is not None:
                    header_value = text_type(header_value)
                data[u"vary"][header] = header_value

        return b",".join([b"cc=0", msgpack.dumps(data, use_bin_type=True)])

    def loads(self, request, data):
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
            return getattr(self, "_loads_v{}".format(ver))(request, data)

        except AttributeError:
            # This is a version we don't have a loads function for, so we'll
            # just treat it as a miss and return None
            return

    def prepare_response(self, request, cached):
        """Verify our vary headers match and construct a real Response object.
        """
        # Special case the '*' Vary value as it means we cannot actually
        # determine if the cached response is suitable for this request.
        # This case is also handled in the controller code when creating
        # a cache entry, but is left here for backwards compatibility.
        if "*" in cached.get("vary", {}):
            return

        # Ensure that the Vary headers for the cached response match our
        # request
        for header, value in cached.get("vary", {}).items():
            if request.headers.get(header, None) != value:
                return

        body_raw = cached["response"].pop("body")

        headers = Headers(data=cached["response"]["headers"])
        if headers.get("transfer-encoding", "") == "chunked":
            headers.pop("transfer-encoding")

        cached["response"]["headers"] = headers

        try:
            body = io.BytesIO(body_raw)
        except TypeError:
            # This can happen if cachecontrol serialized to v1 format (pickle)
            # using Python 2. A Python 2 str(byte string) will be unpickled as
            # a Python 3 str (unicode string), which will cause the above to
            # fail with:
            #
            #     TypeError: 'str' does not support the buffer interface
            body = io.BytesIO(body_raw.encode("utf8"))

        return Response(body=body, preload_content=False, **cached["response"])

    def _loads_v0(self, request, data):
        try:
            cached = msgpack.loads(data, raw=False)
        except ValueError:
            return

        return self.prepare_response(request, cached)
