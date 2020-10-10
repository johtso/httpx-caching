from typing import List, Optional, Tuple, TypeVar, Union

from httpcore import AsyncHTTPTransport, SyncHTTPTransport
from httpx import AsyncClient, Client

RawURL = Tuple[bytes, bytes, Optional[int], bytes]
RawHeaders = List[Tuple[bytes, bytes]]

AnyClient = TypeVar("AnyClient", Client, AsyncClient)
AnyTransport = Union[SyncHTTPTransport, AsyncHTTPTransport]
