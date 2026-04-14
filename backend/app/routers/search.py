from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.models.schemas import SearchRequest, SearchResponse, SearchResult, FilterOptions
from app.services.singleton import get_chroma_service

router = APIRouter()


class ErrorResponse(BaseModel):
    error: str
    query: str
    results: List = []
    total: int = 0


@router.post("/", response_model=SearchResponse)
async def search_videos(request: SearchRequest):
    query = request.query.strip() if request.query else ""

    if not query:
        return ErrorResponse(error="搜索词不能为空", query=query)

    try:
        chroma_service = get_chroma_service()

        if not chroma_service.model_ready:
            return ErrorResponse(error="搜索模型未就绪，请检查后端日志", query=query)

        top_k = request.top_k or 20
        results = chroma_service.search(query=query, top_k=top_k)

        print(f"[SEARCH] 搜索返回 {len(results)} 条结果")
        if results:
            raw_dist = results[0].get('distance')
            print(f"   第一条原始distance: {raw_dist:.4f}")

        search_results = []
        for r in results:
            distance = r.get("distance", 0.0)
            similarity = max(0, int((1 - distance) * 100))

            if request.filters:
                filters = request.filters
                if filters.min_score and similarity < filters.min_score:
                    continue
                if filters.max_score and similarity > filters.max_score:
                    continue
                if filters.shot_size and filters.shot_size not in r.get("shot_size", ""):
                    continue
                if filters.camera_movement and filters.camera_movement not in r.get("camera_movement", ""):
                    continue
                if filters.lighting and filters.lighting not in r.get("lighting", ""):
                    continue

            search_results.append(SearchResult(
                video_path=r.get("video_path", ""),
                frame_path=r.get("frame_path", ""),
                description=r.get("description", ""),
                timestamp=r.get("timestamp", 0.0),
                start_time=r.get("start_time", 0.0),
                end_time=r.get("end_time", 0.0),
                score=similarity
            ))
            print(f"   → 距离:{distance:.3f} → 匹配度:{similarity:.1f}%")

        return SearchResponse(
            query=query,
            results=search_results,
            total=len(search_results)
        )

    except Exception as e:
        print(f"[ERROR] 搜索错误: {e}")
        return ErrorResponse(error=f"搜索失败: {str(e)}", query=query)


@router.get("/filters/options")
async def get_filter_options():
    chroma_service = get_chroma_service()
    try:
        all_data = chroma_service.collection.get()
        shot_sizes = set()
        camera_movements = set()
        lightings = set()

        if all_data and all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                if meta.get("shot_size"):
                    shot_sizes.add(meta["shot_size"])
                if meta.get("camera_movement"):
                    camera_movements.add(meta["camera_movement"])
                if meta.get("lighting"):
                    lightings.add(meta["lighting"])

        return {
            "shot_sizes": sorted(list(shot_sizes)),
            "camera_movements": sorted(list(camera_movements)),
            "lightings": sorted(list(lightings))
        }
    except Exception as e:
        return {
            "shot_sizes": [],
            "camera_movements": [],
            "lightings": [],
            "error": str(e)
        }


@router.get("/stats")
async def get_search_stats():
    chroma_service = get_chroma_service()
    try:
        videos = chroma_service.get_video_list()
        frames = chroma_service.get_all_frames()

        resolutions = set()
        for frame in frames:
            res = frame.get("video_resolution", "")
            if res:
                resolutions.add(res)

        return {
            "total_videos": len(videos),
            "total_frames": len(frames),
            "resolutions": sorted(list(resolutions))
        }
    except Exception as e:
        return {
            "total_videos": 0,
            "total_frames": 0,
            "resolutions": [],
            "error": str(e)
        }
