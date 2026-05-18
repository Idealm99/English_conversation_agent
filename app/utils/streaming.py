"""동기 generator → async iterator 브릿지.

Vertex AI 의 `generate_content(stream=True)` 같은 동기 generator 를 SSE 엔드포인트
같은 asyncio 컨텍스트에서 안전하게 소비하기 위해, 별도 스레드에서 돌리고
청크를 `asyncio.Queue` 로 전달한다. 호출자는 일반 async-for 로 쓰면 된다.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable, Iterator, TypeVar

T = TypeVar("T")


class _Sentinel:
    pass


_DONE = _Sentinel()


async def bridge_sync_to_async(
    sync_iter_factory: Callable[[], Iterator[T]],
) -> AsyncIterator[T]:
    """주어진 동기 iterator factory 를 별도 스레드에서 실행해 청크를 async yield.

    factory 호출은 스레드 안에서 일어나기 때문에 generator 가 호출 시점에
    네트워크 연결 등을 하는 경우도 이벤트 루프를 막지 않는다. 예외도 전파된다.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[object] = asyncio.Queue()

    def _producer() -> None:
        try:
            for chunk in sync_iter_factory():
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    producer_task = asyncio.create_task(asyncio.to_thread(_producer))
    try:
        while True:
            item = await queue.get()
            if item is _DONE:
                return
            if isinstance(item, Exception):
                raise item
            yield item  # type: ignore[misc]
    finally:
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass
