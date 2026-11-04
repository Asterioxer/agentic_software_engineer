from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from app.domain import TaskSpec
from app.main import app
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import get_default_store
from app.telemetry import EventBus, RunEvent
from app.tools import build_default_registry


def test_event_bus_pub_sub() -> None:
    bus = EventBus(max_history_per_run=10)
    run_id = "test-run-101"

    ev1 = bus.publish(run_id, "step:start", {"step_id": "step_1"})
    assert ev1.sequence == 1
    assert ev1.event_type == "step:start"
    assert ev1.payload["step_id"] == "step_1"

    ev2 = bus.publish(run_id, "step:finish", {"step_id": "step_1", "status": "completed"})
    assert ev2.sequence == 2

    history = bus.get_history(run_id)
    assert len(history) == 2
    assert history[0].sequence == 1
    assert history[1].sequence == 2


@pytest.mark.anyio
async def test_event_bus_queue_delivery() -> None:
    bus = EventBus()
    run_id = "test-async-run"
    queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

    bus.register_queue(run_id, queue)
    bus.publish(run_id, "log", {"text": "hello streaming"})

    event = await queue.get()
    assert event is not None
    assert event.event_type == "log"
    assert event.payload["text"] == "hello streaming"

    # Close run
    bus.close_run(run_id)
    term = await queue.get()
    assert term is None

    bus.unregister_queue(run_id, queue)


def test_event_to_sse_format() -> None:
    ev = RunEvent(run_id="r1", sequence=1, event_type="test_event", payload={"key": "val"})
    sse_str = ev.to_sse()
    assert sse_str.startswith("event: test_event\n")
    assert "data: " in sse_str
    assert sse_str.endswith("\n\n")


def test_stream_endpoint_404_on_missing_run() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/runs/non-existent-run-xyz/stream")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_stream_endpoint_replays_history_for_completed_run(tmp_path: Path) -> None:
    client = TestClient(app)

    # Dispatch a fast dry-run task
    task = TaskSpec(
        title="Check status test",
        description="Dry run task to test streaming replay",
        repository=str(tmp_path),
        dry_run=True,
    )
    store = get_default_store()
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=store)
    res = run.execute()
    run_id = str(res["run_id"])

    # Stream should replay all past events and terminate
    with client.stream("GET", f"/api/v1/runs/{run_id}/stream") as stream_resp:
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers["content-type"]
        body = "".join(chunk for chunk in stream_resp.iter_text())
        assert "status:" in body
        assert run_id in body


def test_websocket_missing_run() -> None:
    client = TestClient(app)
    with pytest.raises(Exception), client.websocket_connect("/api/v1/ws/runs/non-existent-ws-run"):  # noqa: B017
        pass


def test_websocket_connect_ping_and_approval(tmp_path: Path) -> None:
    client = TestClient(app)

    # Create a run awaiting approval
    task = TaskSpec(
        title="WebSocket interactive test",
        description="Verify interactive websocket approval",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )
    store = get_default_store()
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=store)
    res = run.execute()
    run_id = str(res["run_id"])
    assert res["status"] == "awaiting_approval"

    with client.websocket_connect(f"/api/v1/ws/runs/{run_id}") as websocket:
        # Test ping action
        websocket.send_json({"action": "ping"})
        pong_resp = None
        for _ in range(10):
            msg = websocket.receive_json()
            if msg.get("event_type") == "pong":
                pong_resp = msg
                break
        assert pong_resp is not None
        assert pong_resp.get("event_type") == "pong"

        # Test interactive approval over WebSocket
        websocket.send_json({"action": "approve"})
        action_resp = None
        for _ in range(15):
            msg = websocket.receive_json()
            if msg.get("event_type") == "action_result":
                action_resp = msg
                break
        assert action_resp is not None
        assert action_resp.get("action") == "approve"
        assert action_resp.get("status") == "completed"
