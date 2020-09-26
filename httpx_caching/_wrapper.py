import httpcore

from httpx_caching._async._transport import AsyncCachingTransport
from httpx_caching._sync._transport import SyncCachingTransport
from httpx_caching._types import AnyClient


def CachingClient(client: AnyClient, *args, **kwargs) -> AnyClient:
    # TODO: Change this once HTTPX adds mounting functionality
    print(client)
    current_transport = client._transport
    print(current_transport)
    if "transport" not in kwargs:
        kwargs["transport"] = current_transport

    is_async = isinstance(current_transport, httpcore.AsyncHTTPTransport)
    print(f"is async: {is_async}")
    client._transport = (AsyncCachingTransport if is_async else SyncCachingTransport)(
        *args, **kwargs
    )
    print(client._transport)

    return client
