from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.jwt_service import decode_token
from app.services.websocket_service import websocket_manager

router = APIRouter()

@router.websocket("/mails/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        username = decode_token(token)
        if '@' in username:
            username = username.split('@')[0]
            
        await websocket_manager.connect(websocket, username)
        
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                await websocket_manager.disconnect(websocket, username)
                break
            
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        await websocket.close()