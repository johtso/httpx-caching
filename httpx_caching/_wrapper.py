from typing import TypeVar

from httpx import AsyncClient, Client

from ._transport import CachingTransport

AnyClient = TypeVar("AnyClient", Client, AsyncClient)


def CachingClient(client: AnyClient, *args, **kwargs) -> AnyClient:
    # TODO: Change this once HTTPX adds mounting functionality
    if "transport" not in kwargs:
        kwargs["transport"] = client._transport

    client._transport = CachingTransport(*args, **kwargs)

    return client
