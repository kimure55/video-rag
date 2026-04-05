from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.routers import process, search
from app.services.chroma_service import ChromaService


chroma_service = None

frames_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frames")


def get_chroma_service() -> ChromaService:
    global chroma_service
    if chroma_service is None:
        chroma_service = ChromaService()
    return chroma_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(frames_dir, exist_ok=True)
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
    return {"status": "healthy", "service": "Video RAG API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
