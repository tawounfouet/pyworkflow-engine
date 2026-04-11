"""Routes — /api/v1/ws — WebSocket bidirectionnel.

Protocole JSON :
  Client → Server : {"command": "subscribe_run", "run_id": "..."}
  Client → Server : {"command": "run_job", "job_name": "...", "context": {...}}
  Server → Client : {"type": "run_update", "data": {...}}
  Server → Client : {"type": "run_started", "data": {"run_id": "..."}}
  Server → Client : {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from pyworkflow_engine.adapters.api.converters import run_to_detail
from pyworkflow_engine.models.enums import TERMINAL_STATUSES

router = APIRouter(tags=["websocket"])


@router.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket bidirectionnel — abonnements et commandes."""
    await websocket.accept()

    engine = websocket.app.state.engine

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            command = msg.get("command")

            if command == "subscribe_run":
                run_id = msg.get("run_id")
                if not run_id:
                    await websocket.send_json(
                        {"type": "error", "message": "Missing 'run_id'"}
                    )
                    continue
                while True:
                    job_run = engine.get_job_run(run_id)
                    if job_run is None:
                        await websocket.send_json(
                            {"type": "error", "message": f"Run {run_id} not found"}
                        )
                        break
                    detail = run_to_detail(job_run)
                    await websocket.send_json(
                        {
                            "type": "run_update",
                            "data": detail.model_dump(mode="json"),
                        }
                    )
                    if job_run.status in TERMINAL_STATUSES:
                        break
                    await asyncio.sleep(1.0)

            elif command == "run_job":
                job_name = msg.get("job_name")
                if not job_name:
                    await websocket.send_json(
                        {"type": "error", "message": "Missing 'job_name'"}
                    )
                    continue
                try:
                    job_run = await asyncio.to_thread(
                        engine.run_with_storage,
                        job_name,
                        initial_context=msg.get("context"),
                    )
                    await websocket.send_json(
                        {
                            "type": "run_started",
                            "data": {
                                "run_id": job_run.job_run_id,
                                "status": job_run.status.value,
                            },
                        }
                    )
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown command: {command}"}
                )

    except WebSocketDisconnect:
        pass
