import threading
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Iterator,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

import anyio
import httpx
from httpcore import AsyncByteStream, SyncByteStream

AsyncLock = anyio.create_lock
SyncLock = threading.Lock


class ByteStreamWrapper(SyncByteStream, AsyncByteStream):
    def __init__(
        self,
        stream: Union[SyncByteStream, AsyncByteStream],
        callback: Optional[Callable] = None,
    ) -> None:
        """
        A wrapper around a stream that calls a callback once with
        the full contents of the stream after it has been fully read.
        """
        print("wrapping", stream)
        self.stream = stream
        self.callback = callback or (lambda *args, **kwargs: None)

        self.buffer = bytearray()
        self.callback_called = False

    def _on_read_finish(self):
        if not self.callback_called:
            self.callback(bytes(self.buffer))
            self.callback_called = True

    async def a_on_read_finish(self):
        if not self.callback_called:
            await self.callback(bytes(self.buffer))
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
        await self.a_on_read_finish()

    def close(self) -> None:
        self.stream.close()  # type: ignore

    async def aclose(self) -> None:
        await self.stream.aclose()  # type: ignore


YieldType = TypeVar("YieldType")
SendType = TypeVar("SendType")
ReturnType = TypeVar("ReturnType")


async def async_callback_generator(
    genfunction: Callable[..., Generator[YieldType, SendType, ReturnType]],
    callback: Callable[[YieldType], Awaitable[SendType]],
    kwargs: dict,
):
    gen = genfunction(**kwargs)
    try:
        yielded = next(gen)
        while True:
            print("output:", yielded)
            to_send = await callback(yielded)
            print("input:", to_send)
            yielded = gen.send(to_send)
    except StopIteration as e:
        print("result:", e.value)
        print()
        return e.value


def sync_callback_generator(
    genfunction: Callable[..., Generator[YieldType, SendType, ReturnType]],
    callback: Callable[[YieldType], SendType],
    kwargs: dict,
):
    gen = genfunction(**kwargs)
    try:
        yielded = next(gen)
        while True:
            to_send = callback(yielded)
            yielded = gen.send(to_send)
    except StopIteration as e:
        return e.value


def request_to_raw(request: httpx.Request) -> Tuple:
    return (
        request.method.encode("ascii"),
        request.url.raw,
        request.headers.raw,
        request.stream,
        {},  # TODO: need to sort out ext preservation
    )
