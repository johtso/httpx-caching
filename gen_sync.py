from pathlib import Path

from unasync import unasync_files, Rule


unasync_files(
    [str(p) for p in Path("tests").rglob("*.py")],
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
                # "async_enabled": "async_disabled",
            }
        )
        # unasync.Rule(
        #     "test/with_dummyserver/async",
        #     "test/with_dummyserver/sync",
        #     additional_replacements={
        #         "AsyncPoolManager": "PoolManager",
        #         "test_all_backends": "test_sync_backend",
        #     },
        # )
    ],
)

