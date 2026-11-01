from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("agent.telemetry")


@dataclass(frozen=True)
class RunEvent:
    """Structured real-time telemetry event emitted during agent task execution."""

    run_id: str
    sequence: int
    event_type: str
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"event: {self.event_type}\ndata: {self.to_json()}\n\n"


class EventBus:
    """Thread-safe and async-compatible publish-subscribe event bus with replay buffer."""

    def __init__(self, max_history_per_run: int = 1000) -> None:
        self.max_history_per_run = max_history_per_run
        self._lock = threading.Lock()
        self._history: dict[str, list[RunEvent]] = defaultdict(list)
        self._seq_counter: dict[str, int] = defaultdict(int)
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent | None]]] = defaultdict(set)

    def publish(
        self, run_id: str, event_type: str, payload: dict[str, Any] | None = None
    ) -> RunEvent:
        """Publish a new event to all active subscribers and append to replay history."""
        with self._lock:
            self._seq_counter[run_id] += 1
            seq = self._seq_counter[run_id]
            event = RunEvent(
                run_id=run_id,
                sequence=seq,
                event_type=event_type,
                timestamp=time.time(),
                payload=payload or {},
            )

            # Append to history with bounded size
            history = self._history[run_id]
            history.append(event)
            if len(history) > self.max_history_per_run:
                self._history[run_id] = history[-self.max_history_per_run :]

            queues = list(self._subscribers.get(run_id, set()))

        # Deliver to async subscriber queues
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue full for run %s, dropping event", run_id)

        return event

    def get_history(self, run_id: str) -> list[RunEvent]:
        """Retrieve recorded history of events for a run."""
        with self._lock:
            return list(self._history.get(run_id, []))

    def register_queue(self, run_id: str, queue: asyncio.Queue[RunEvent | None]) -> None:
        """Register a subscriber queue for live events."""
        with self._lock:
            self._subscribers[run_id].add(queue)

    def unregister_queue(self, run_id: str, queue: asyncio.Queue[RunEvent | None]) -> None:
        """Unregister a subscriber queue."""
        with self._lock:
            if run_id in self._subscribers:
                self._subscribers[run_id].discard(queue)
                if not self._subscribers[run_id]:
                    del self._subscribers[run_id]

    def close_run(self, run_id: str) -> None:
        """Signal all subscribers for a run that execution has closed."""
        with self._lock:
            queues = list(self._subscribers.get(run_id, set()))
        for q in queues:
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass


_GLOBAL_EVENT_BUS: EventBus | None = None
_GLOBAL_BUS_LOCK = threading.Lock()


def get_event_bus() -> EventBus:
    global _GLOBAL_EVENT_BUS
    if _GLOBAL_EVENT_BUS is None:
        with _GLOBAL_BUS_LOCK:
            if _GLOBAL_EVENT_BUS is None:
                _GLOBAL_EVENT_BUS = EventBus()
    return _GLOBAL_EVENT_BUS
