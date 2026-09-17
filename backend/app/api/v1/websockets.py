from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import websocket_manager

router = APIRouter(tags=["websockets"])


async def _listen(channel: str, websocket: WebSocket) -> None:
    await websocket_manager.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(channel, websocket)


@router.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket) -> None:
    await _listen("dashboard", websocket)


@router.websocket("/ws/incidents/{incident_id}")
async def incident_socket(incident_id: UUID, websocket: WebSocket) -> None:
    await _listen(f"incident:{incident_id}", websocket)


@router.websocket("/ws/services/{service_id}")
async def service_socket(service_id: UUID, websocket: WebSocket) -> None:
    await _listen(f"service:{service_id}", websocket)
