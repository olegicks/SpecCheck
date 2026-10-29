"""Per-run event bus feeding Server-Sent Events.

Events are kept in a list so late subscribers (or reconnecting browsers sending
``Last-Event-ID``) get a full replay before live events.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from app.agent.schemas import AgentEvent


class EventBus:
    def __init__(self) -> None:
        self.events: list[AgentEvent] = []
        self.closed = False
        self._changed = asyncio.Condition()

    async def publish(self, event: AgentEvent) -> None:
        async with self._changed:
            self.events.append(event)
            self._changed.notify_all()

    async def close(self) -> None:
        async with self._changed:
            self.closed = True
            self._changed.notify_all()

    async def subscribe(
        self, after_seq: int = 0, heartbeat: float = 15.0
    ) -> AsyncIterator[AgentEvent | None]:
        """Yield events with ``seq > after_seq``; yields ``None`` as a keep-alive tick."""
        index = 0
        while True:
            async with self._changed:
                if index >= len(self.events) and not self.closed:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._changed.wait(), heartbeat)
                pending = self.events[index:]
                index = len(self.events)
                finished = self.closed and not pending
            if finished:
                return
            if not pending:
                yield None
            for event in pending:
                if event.seq > after_seq:
                    yield event
