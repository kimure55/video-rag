from fastapi import APIRouter, HTTPException
from app.models.schemas import ProcessRequest, ProcessResponse, ProcessStatus
from app.services.chroma_service import VideoProcessor, ChromaService
import os
from typing import List
from datetime import datetime

router = APIRouter()

process_status = {
    "is_processing": False,
    "current_video": "",
    "current_video_index": 0,
    "total_videos": 0,
    "current_frame_index": 0,
    "total_frames": 0,
    "processed_videos": 0,
    "processed_frames": 0,
    "status": "idle",
    "message": "",
    "start_time": None,
    "error": None
}


def reset_status():
    global process_status
    process_status = {
        "is_processing": False,
        "current_video": "",
        "current_video_index": 0,
        "total_videos": 0,
        "current_frame_index": 0,
        "total_frames": 0,
        "processed_videos": 0,
        "processed_frames": 0,
        "status": "idle",
        "message": "",
        "start_time": None,
        "error": None
    }


def update_status(**kwargs):
    global process_status
    for key, value in kwargs.items():
        if key in process_status:
            process_status[key] = value


@router.get("/status")
async def get_status():
    return process_status


@router.post("/", response_model=ProcessResponse)
async def process_videos(request: ProcessRequest):
    global process_status

    if process_status["is_processing"]:
        raise HTTPException(status_code=409, detail="Processing already in progress")

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

    reset_status()
    process_status["is_processing"] = True
    process_status["total_videos"] = len(video_files)
    process_status["status"] = "processing"
    process_status["start_time"] = datetime.now().isoformat()

    processor = VideoProcessor()
    chroma_service = ChromaService()

    total_frames = 0
    processed_videos = 0

    try:
        for idx, video_path in enumerate(video_files):
            video_name = os.path.basename(video_path)
            update_status(
                current_video=video_name,
                current_video_index=idx + 1,
                current_frame_index=0
            )

            try:
                results = processor.process_video(video_path)

                for frame_idx, result in enumerate(results):
                    chroma_service.add_frame(
                        frame_path=result["frame_path"],
                        description=result["description"],
                        video_path=result["video_path"],
                        timestamp=result["timestamp"],
                        start_time=result["start_time"],
                        end_time=result["end_time"]
                    )
                    total_frames += 1
                    process_status["processed_frames"] = total_frames
                    process_status["current_frame_index"] = frame_idx + 1

                processed_videos += 1
                process_status["processed_videos"] = processed_videos

            except Exception as e:
                print(f"Error processing video {video_path}: {e}")
                process_status["error"] = str(e)
                continue

        process_status["status"] = "completed"
        process_status["message"] = f"Processed {processed_videos} videos with {total_frames} frames"
        process_status["is_processing"] = False

        return ProcessResponse(
            status="success",
            message=process_status["message"],
            processed_videos=processed_videos,
            total_frames=total_frames
        )

    except Exception as e:
        process_status["status"] = "error"
        process_status["error"] = str(e)
        process_status["is_processing"] = False
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/frames")
async def get_frames():
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
