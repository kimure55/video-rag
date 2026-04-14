from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pathlib import Path
import os

from app.routers import process, search
from app.services.singleton import init_chroma_service
from app.services.websocket_manager import ws_manager


frames_dir = str(Path(__file__).parent.parent / "frames")


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(frames_dir, exist_ok=True)
    init_chroma_service()
    yield


app = FastAPI(
    title="Video RAG API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frames", StaticFiles(directory=frames_dir), name="frames")

app.include_router(process.router, prefix="/process", tags=["process"])
app.include_router(search.router, prefix="/search", tags=["search"])


@app.get("/health")
async def health_check():
    abs_frames_path = str(Path(frames_dir).resolve())
    return {
        "status": "healthy",
        "service": "Video RAG API",
        "frames_dir": abs_frames_path
    }


@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] WebSocket异常: {e}")
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
