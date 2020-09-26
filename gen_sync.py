from pathlib import Path

from unasync import unasync_files, Rule

directories = [
    Path("httpx_caching"),
    Path("tests"),
]
file_paths = set()
for directory in directories:
    for p in directory.rglob("*.py"):
        file_paths.add(str(p))

unasync_files(
    file_paths,
    rules=[
        Rule(
            fromdir="/_async/",
            todir="/_sync/",
            additional_replacements={
                "async_client": "client",
                "AsyncClient": "Client",
                "make_async_client": "make_client",
                "asyncio": "sync",
                "aclose": "close",
                "aread": "read",
                "AsyncCachingTransport": "SyncCachingTransport",
                "async_vanilla_request": "sync_vanilla_request",
                "arun": "run",
                "aio_handler": "io_handler",
                "arequest": "request",
                "aget": "get",
                "aset": "set",
                "adelete": "delete",
                '"arequest"': '"request"',
                # "async_enabled": "async_disabled",
            }
        ),
    ],
)

