from typing import AsyncIterator, Callable, Iterator, Union

from httpcore import AsyncByteStream, SyncByteStream


class ByteStreamWrapper(SyncByteStream, AsyncByteStream):
    def __init__(
        self,
        stream: Union[SyncByteStream, AsyncByteStream],
        callback: Callable,
    ) -> None:
        """
        A wrapper around a stream that calls a callback once with
        the full contents of the stream after it has been fully read.
        """
        self.stream = stream
        self.callback = callback

        self.buffer = bytearray()
        self.callback_called = False

    def _on_read_finish(self):
        if not self.callback_called:
            self.callback(bytes(self.buffer))
            self.callback_called = True

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.stream:  # type: ignore
            self.buffer.extend(chunk)
            yield chunk
        self._on_read_finish()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self.stream:  # type: ignore
            self.buffer.extend(chunk)
            yield chunk
        self._on_read_finish()

    def close(self) -> None:
        self.stream.close()  # type: ignore

    async def aclose(self) -> None:
        await self.stream.aclose()  # type: ignore
