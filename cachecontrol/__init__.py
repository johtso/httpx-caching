"""CacheControl import Interface.

Make it easy to import from cachecontrol without long namespaces.
"""

from .adapter import SyncHTTPCacheTransport

__all__ = [
    "SyncHTTPCacheTransport",
]
