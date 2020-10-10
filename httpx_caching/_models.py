import dataclasses
from typing import Union

from httpcore import AsyncByteStream, PlainByteStream, SyncByteStream
from httpx import Headers


@dataclasses.dataclass
class Response:
    """
    Simple wrapper for the raw response returned by a transport.
    """

    status_code: int
    headers: Headers
    stream: Union[SyncByteStream, AsyncByteStream]
    ext: dict = dataclasses.field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw_response):
        values = list(raw_response)
        values[1] = Headers(values[1])
        if isinstance(values[2], bytes):
            values[2] = PlainByteStream(values[2])
        return cls(*values)

    def to_raw(self):
        raw = []
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if field.name == "headers":
                value = value.raw
            raw.append(value)
        return tuple(raw)
