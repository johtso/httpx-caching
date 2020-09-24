from typing import Callable, Iterator

import httpcore


class SyncByteStreamWrapper(httpcore.SyncByteStream):
    def __init__(
        self,
        stream: httpcore.SyncByteStream,
        callback: Callable,
    ) -> None:
        """
        A wrapper around a stream that calls a callback when stream is closed.
        """
        self.stream = stream
        self.callback = callback
        self.buffer = bytearray()

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:
            self.buffer.extend(chunk)
            yield chunk

    def close(self) -> None:
        self.stream.close()
        self.callback(bytes(self.buffer))
