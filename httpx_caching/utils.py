from typing import AsyncIterator, Callable, Iterator, Union

from httpcore import AsyncByteStream, SyncByteStream


class ByteStreamWrapper(SyncByteStream, AsyncByteStream):
    def __init__(
        self,
        stream: Union[SyncByteStream, AsyncByteStream],
        callback: Callable,
    ) -> None:
        """
        A wrapper around a stream that calls a callback when stream is closed.
        """
        self.stream = stream
        self.callback = callback
        self.buffer = bytearray()

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:  # type: ignore
            self.buffer.extend(chunk)
            yield chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:  # type: ignore
            self.buffer.extend(chunk)
            yield chunk

    def close(self) -> None:
        self.stream.close()  # type: ignore
        self.callback(bytes(self.buffer))

    async def aclose(self) -> None:
        await self.stream.aclose()  # type: ignore
        self.callback(bytes(self.buffer))
