import asyncio

from app.agent.schemas import AgentEvent, EventType
from app.checks.events import EventBus


def event(seq: int) -> AgentEvent:
    return AgentEvent(seq=seq, type=EventType.SEARCH, title=f"e{seq}")


async def test_live_subscriber_receives_events_as_they_are_published() -> None:
    bus = EventBus()
    received: list[int] = []

    async def consume() -> None:
        async for e in bus.subscribe(heartbeat=5):
            if e is not None:
                received.append(e.seq)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    for seq in (1, 2, 3):
        await bus.publish(event(seq))
        await asyncio.sleep(0)
        assert received[-1] == seq  # delivered immediately, not at the end
    await bus.close()
    await asyncio.wait_for(task, 1)
    assert received == [1, 2, 3]


async def test_heartbeat_and_replay_after_seq() -> None:
    bus = EventBus()
    await bus.publish(event(1))
    await bus.publish(event(2))
    stream = bus.subscribe(after_seq=1, heartbeat=0.01)
    assert (await anext(stream)).seq == 2
    assert await anext(stream) is None  # keep-alive tick while idle
    await bus.close()
    assert [e async for e in stream] == []
