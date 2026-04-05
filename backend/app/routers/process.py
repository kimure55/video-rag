from fastapi import APIRouter, HTTPException
from app.models.schemas import ProcessRequest, ProcessResponse
from app.services.chroma_service import VideoProcessor, ChromaService
import os
from typing import List

router = APIRouter()


@router.post("/", response_model=ProcessResponse)
async def process_videos(request: ProcessRequest):
    if not os.path.exists(request.folder_path):
        raise HTTPException(status_code=400, detail="Folder path does not exist")

    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
    video_files = [
        os.path.join(request.folder_path, f)
        for f in os.listdir(request.folder_path)
        if os.path.splitext(f.lower())[1] in video_extensions
    ]

    if not video_files:
        raise HTTPException(status_code=400, detail="No video files found in the specified folder")

    processor = VideoProcessor()
    chroma_service = ChromaService()

    total_frames = 0
    processed_videos = 0

    for video_path in video_files:
        try:
            results = processor.process_video(video_path)

            for result in results:
                chroma_service.add_frame(
                    frame_path=result["frame_path"],
                    description=result["description"],
                    video_path=result["video_path"],
                    timestamp=result["timestamp"],
                    start_time=result["start_time"],
                    end_time=result["end_time"]
                )
                total_frames += 1

            processed_videos += 1
        except Exception as e:
            print(f"Error processing video {video_path}: {e}")
            continue

    return ProcessResponse(
        status="success",
        message=f"Processed {processed_videos} videos with {total_frames} frames",
        processed_videos=processed_videos,
        total_frames=total_frames
    )


@router.get("/frames")
async def get_frames():
    from app.services.chroma_service import ChromaService
    chroma_service = ChromaService()
    try:
        results = chroma_service.collection.get()
        frames = []
        if results and results["ids"]:
            for i in range(len(results["ids"])):
                frames.append({
                    "id": results["ids"][i],
                    "frame_path": results["metadatas"][i]["frame_path"],
                    "video_path": results["metadatas"][i]["video_path"],
                    "timestamp": results["metadatas"][i]["timestamp"],
                    "start_time": results["metadatas"][i]["start_time"],
                    "end_time": results["metadatas"][i]["end_time"],
                    "description": results["metadatas"][i]["description"]
                })
        return {"frames": frames}
    except Exception as e:
        return {"frames": [], "error": str(e)}
