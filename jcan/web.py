import asyncio
import json
import queue as queue_module
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .history_db import HistoryDB
from .vin_decoder import VinDecodeError, decode_vin


class NotesUpdate(BaseModel):
    notes: str


async def _broadcast(clients: set, message: str) -> None:
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


def create_app(
    reader,
    db: HistoryDB,
    static_dir: str,
    debug_controls: bool = False,
    extra_on_reading=None,
) -> FastAPI:
    clients: set = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()

        def on_reading(name: str, value: float, unit: str) -> None:
            message = json.dumps({"type": "reading", "pid": name, "value": value, "unit": unit})
            asyncio.run_coroutine_threadsafe(_broadcast(clients, message), loop)
            if extra_on_reading is not None:
                extra_on_reading(name, value, unit)

        def on_status(status: str) -> None:
            message = json.dumps({"type": "status", "status": status})
            asyncio.run_coroutine_threadsafe(_broadcast(clients, message), loop)

        def on_readiness(status: dict) -> None:
            message = json.dumps({"type": "readiness", **status})
            asyncio.run_coroutine_threadsafe(_broadcast(clients, message), loop)

        reader.on_reading = on_reading
        reader.on_status = on_status
        reader.on_readiness = on_readiness
        reader.start()
        yield
        reader.stop()

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    @app.get("/dtcs")
    async def get_dtcs():
        result_queue = reader.submit("read_dtcs")
        try:
            status, payload = await asyncio.to_thread(result_queue.get, True, 5.0)
        except queue_module.Empty:
            raise HTTPException(status_code=503, detail="No response from vehicle")
        if status == "error":
            raise HTTPException(status_code=503, detail=payload)
        db.record_active_codes(payload, reader.current_vin)
        return db.active_events()

    @app.post("/dtcs/clear")
    async def clear_dtcs():
        result_queue = reader.submit("clear_dtcs")
        try:
            status, payload = await asyncio.to_thread(result_queue.get, True, 5.0)
        except queue_module.Empty:
            raise HTTPException(status_code=503, detail="No response from vehicle")
        if status == "error":
            raise HTTPException(status_code=503, detail=payload)
        db.clear_active_events()
        return {"cleared": True}

    @app.get("/dtcs/history")
    async def get_history():
        return db.all_events()

    @app.patch("/dtcs/{event_id}/notes")
    async def update_notes(event_id: int, body: NotesUpdate):
        updated = db.set_notes(event_id, body.notes)
        if not updated:
            raise HTTPException(status_code=404, detail="Event not found")
        return {"id": event_id, "notes": body.notes}

    @app.get("/vehicles")
    async def get_vehicles():
        rows = db.vehicles_view()
        for row in rows:
            raw_json = row.pop("raw_json")
            row["raw"] = json.loads(raw_json) if raw_json else None
        return rows

    @app.post("/vehicles/{vin}/decode")
    async def decode_vehicle(vin: str):
        try:
            decoded = await asyncio.to_thread(decode_vin, vin)
        except VinDecodeError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        db.upsert_vehicle(
            vin, decoded["make"], decoded["model"], decoded["year"], json.dumps(decoded["raw"])
        )
        return {"vin": vin, "make": decoded["make"], "model": decoded["model"],
                "year": decoded["year"], "raw": decoded["raw"]}

    if debug_controls:
        @app.post("/debug/disconnect")
        async def debug_disconnect():
            result_queue = reader.submit("simulate_disconnect")
            try:
                await asyncio.to_thread(result_queue.get, True, 5.0)
            except queue_module.Empty:
                raise HTTPException(status_code=503, detail="No response from reader")
            return {"disconnected": True}

    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        return FileResponse(f"{static_dir}/index.html")

    return app
