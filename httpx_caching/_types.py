from typing import TypeVar, Union

from httpx import AsyncClient, AsyncHTTPTransport, Client, HTTPTransport

AnyClient = TypeVar("AnyClient", Client, AsyncClient)
AnyTransport = Union[HTTPTransport, AsyncHTTPTransport]
