import dataclasses
from typing import Union

from httpx import ByteStream, Headers

from ._utils import ByteStreamWrapper


@dataclasses.dataclass
class Response:
    """
    Simple wrapper for the raw response returned by a transport.
    """

    status_code: int
    headers: Headers
    stream: Union[ByteStream, ByteStreamWrapper]
    extensions: dict = dataclasses.field(default_factory=dict)
