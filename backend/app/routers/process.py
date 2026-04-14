from fastapi import APIRouter, HTTPException
from app.models.schemas import ProcessRequest, ProcessResponse, ProcessStatus, WatchFolderRequest, WatchFolderResponse
from app.services.chroma_service import VideoProcessor, ChromaService
from app.services.watchdog_service import WatchdogService
from app.services.singleton import get_chroma_service
from app.services.websocket_manager import ws_manager
import os
import threading
from typing import List, Optional
from datetime import datetime
import asyncio

router = APIRouter()

watchdog_service: Optional[WatchdogService] = None
processing_thread: Optional[threading.Thread] = None

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
    "error": None,
    "watch_mode": False,
    "watch_path": None
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
        "error": None,
        "watch_mode": process_status.get("watch_mode", False),
        "watch_path": process_status.get("watch_path", None)
    }


def update_status(**kwargs):
    global process_status
    for key, value in kwargs.items():
        if key in process_status:
            process_status[key] = value


@router.get("/status")
async def get_status():
    result = {
        "is_processing": process_status["is_processing"],
        "current_video": process_status["current_video"],
        "current_video_index": process_status["current_video_index"],
        "total_videos": process_status["total_videos"],
        "current_frame_index": process_status["current_frame_index"],
        "processed_videos": process_status["processed_videos"],
        "processed_frames": process_status["processed_frames"],
        "status": process_status["status"],
        "message": process_status["message"],
        "start_time": process_status["start_time"],
        "error": process_status["error"],
        "watch_mode": process_status.get("watch_mode", False),
        "watch_path": process_status.get("watch_path", None)
    }
    return result


def process_videos_in_background(video_files: List[str]):
    global process_status

    processor = VideoProcessor()
    chroma_service = get_chroma_service()

    def broadcast_ws(msg: str, data: dict):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(ws_manager.send_progress({
                "message": msg,
                **data
            }))
            loop.close()
        except Exception as e:
            print(f"[WS] 广播失败: {e}")

    total_frames = 0
    processed_videos = 0
    skipped_videos = 0

    try:
        for idx, video_path in enumerate(video_files):
            video_name = os.path.basename(video_path)

            if chroma_service.is_video_processed(video_path):
                print(f"[SKIP] 跳过已处理视频: {video_name}")
                skipped_videos += 1
                update_status(
                    current_video=video_name,
                    current_video_index=idx + 1,
                    message=f"跳过已处理: {video_name}"
                )
                broadcast_ws(f"跳过已处理: {video_name}", {
                    "current_video": video_name,
                    "current_video_index": idx + 1,
                    "total_videos": len(video_files)
                })
                continue

            update_status(
                current_video=video_name,
                current_video_index=idx + 1,
                current_frame_index=0,
                status="processing"
            )
            broadcast_ws(f"正在解析第 {idx + 1}/{len(video_files)} 个视频: {video_name}", {
                "current_video": video_name,
                "current_video_index": idx + 1,
                "total_videos": len(video_files),
                "status": "processing"
            })

            try:
                results = processor.process_video(video_path)

                if results:
                    chroma_service.add_frames_batch(results)
                    chroma_service.mark_video_processed(video_path)

                total_frames += len(results)
                processed_videos += 1
                process_status["processed_videos"] = processed_videos
                process_status["processed_frames"] = total_frames
                process_status["current_frame_index"] = len(results)
                broadcast_ws(f"已完成: {video_name} ({len(results)} 帧)", {
                    "current_video": video_name,
                    "processed_videos": processed_videos,
                    "total_frames": total_frames,
                    "current_frame_index": len(results)
                })

            except Exception as e:
                print(f"[ERROR] 处理视频失败 {video_path}: {e}")
                process_status["error"] = str(e)
                broadcast_ws(f"处理失败: {video_name}", {"error": str(e)})
                continue

        process_status["status"] = "completed"
        process_status["message"] = f"处理完成: {processed_videos} 个视频, {total_frames} 帧 (跳过 {skipped_videos} 个已处理)"
        broadcast_ws("处理完成", {
            "status": "completed",
            "processed_videos": processed_videos,
            "total_frames": total_frames
        })

    except Exception as e:
        process_status["status"] = "error"
        process_status["error"] = str(e)
        broadcast_ws("处理异常", {"error": str(e)})
    finally:
        process_status["is_processing"] = False


@router.post("/", response_model=ProcessResponse)
async def process_videos(request: ProcessRequest):
    global process_status, processing_thread

    if process_status["is_processing"]:
        raise HTTPException(status_code=409, detail="Processing already in progress")

    if not os.path.exists(request.folder_path):
        raise HTTPException(status_code=400, detail="Folder path does not exist")

    if not os.path.isdir(request.folder_path):
        raise HTTPException(status_code=400, detail="Path is not a directory")

    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
    video_files = []
    for f in os.listdir(request.folder_path):
        ext = os.path.splitext(f.lower())[1]
        if ext in video_extensions:
            video_files.append(os.path.join(request.folder_path, f))

    if not video_files:
        raise HTTPException(status_code=400, detail="No video files found in the specified folder")

    reset_status()
    process_status["is_processing"] = True
    process_status["total_videos"] = len(video_files)
    process_status["status"] = "processing"
    process_status["start_time"] = datetime.now().isoformat()

    processing_thread = threading.Thread(
        target=process_videos_in_background,
        args=(video_files,),
        daemon=True
    )
    processing_thread.start()

    return ProcessResponse(
        status="success",
        message="已开始处理视频",
        processed_videos=0,
        total_frames=0
    )


@router.post("/watch")
async def start_watch(request: WatchFolderRequest) -> WatchFolderResponse:
    global watchdog_service, process_status

    if not os.path.exists(request.folder_path):
        raise HTTPException(status_code=400, detail="Watch folder does not exist")

    if watchdog_service is not None:
        watchdog_service.stop()
        watchdog_service = None

    chroma_service = get_chroma_service()
    processor = VideoProcessor()

    watchdog_service = WatchdogService(
        folder_path=request.folder_path,
        chroma_service=chroma_service,
        video_processor=processor,
        status_callback=lambda msg: update_status(message=msg)
    )

    watchdog_service.start()

    process_status["watch_mode"] = True
    process_status["watch_path"] = request.folder_path

    return WatchFolderResponse(
        status="success",
        message=f"已开始监视: {request.folder_path}",
        watch_path=request.folder_path
    )


@router.post("/watch/stop")
async def stop_watch():
    global watchdog_service, process_status

    if watchdog_service is not None:
        watchdog_service.stop()
        watchdog_service = None

    process_status["watch_mode"] = False
    process_status["watch_path"] = None

    return {"status": "success", "message": "已停止文件夹监视"}


@router.get("/watch/status")
async def get_watch_status():
    global watchdog_service

    if watchdog_service is None:
        return {"watching": False, "watch_path": None}

    return {
        "watching": watchdog_service.is_running(),
        "watch_path": watchdog_service.watch_path,
        "pending_files": len(watchdog_service.pending_videos) if hasattr(watchdog_service, 'pending_videos') else 0
    }


@router.post("/resume")
async def resume_processing():
    global process_status

    if process_status["is_processing"]:
        raise HTTPException(status_code=409, detail="Processing already in progress")

    if not process_status.get("watch_path"):
        raise HTTPException(status_code=400, detail="No watch folder configured")

    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
    video_files = []
    for f in os.listdir(process_status["watch_path"]):
        ext = os.path.splitext(f.lower())[1]
        if ext in video_extensions:
            video_files.append(os.path.join(process_status["watch_path"], f))

    unprocessed = []
    chroma_service = get_chroma_service()
    for video_path in video_files:
        if not chroma_service.is_video_processed(video_path):
            unprocessed.append(video_path)

    if not unprocessed:
        return ProcessResponse(
            status="success",
            message="没有待处理的视频",
            processed_videos=0,
            total_frames=0
        )

    reset_status()
    process_status["is_processing"] = True
    process_status["total_videos"] = len(unprocessed)
    process_status["status"] = "resuming"
    process_status["start_time"] = datetime.now().isoformat()

    processing_thread = threading.Thread(
        target=process_videos_in_background,
        args=(unprocessed,),
        daemon=True
    )
    processing_thread.start()

    return ProcessResponse(
        status="success",
        message="已开始恢复处理",
        processed_videos=0,
        total_frames=0
    )


@router.get("/frames")
async def get_frames():
    chroma_service = get_chroma_service()
    try:
        results = chroma_service.collection.get()
        frames = []
        if results and results["ids"]:
            for i in range(len(results["ids"])):
                frames.append({
                    "id": results["ids"][i],
                    "frame_path": results["metadatas"][i].get("frame_path", ""),
                    "video_path": results["metadatas"][i].get("video_path", ""),
                    "timestamp": results["metadatas"][i].get("timestamp", 0.0),
                    "start_time": results["metadatas"][i].get("start_time", 0.0),
                    "end_time": results["metadatas"][i].get("end_time", 0.0),
                    "description": results["metadatas"][i].get("description", ""),
                    "shot_size": results["metadatas"][i].get("shot_size", ""),
                    "camera_movement": results["metadatas"][i].get("camera_movement", ""),
                    "lighting": results["metadatas"][i].get("lighting", ""),
                    "composition": results["metadatas"][i].get("composition", ""),
                    "action": results["metadatas"][i].get("action", "")
                })
        return {"frames": frames}
    except Exception as e:
        return {"frames": [], "error": str(e)}


@router.get("/videos")
async def get_videos():
    chroma_service = get_chroma_service()
    try:
        videos = chroma_service.get_video_list()
        return {"videos": videos}
    except Exception as e:
        return {"videos": [], "error": str(e)}


@router.delete("/video/{video_path:path}")
async def delete_video(video_path: str):
    chroma_service = get_chroma_service()
    try:
        success = chroma_service.delete_video_frames(video_path)
        if success:
            return {"status": "success", "message": f"已删除视频 {video_path} 的所有帧"}
        else:
            raise HTTPException(status_code=500, detail="删除失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
