from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.models.schemas import SearchRequest, SearchResponse, SearchResult, FilterOptions
from app.services.singleton import get_chroma_service

router = APIRouter()

QUERY_EXPANSION = {
    "空镜": "纯场景镜头，无人出现，建筑，自然风光，空旷室内，环境氛围，没有人物",
    "环境": "环境镜头，场景描写，无人物，纯风景，室内外环境",
    "风景": "自然风景，室外场景，山水树木天空，没有人物",
    "室内": "室内场景，房间内景，家具陈设，没有户外",
    "人物": "有人物镜头，主角出现，演员表演，对话场景",
    "夜景": "夜晚场景，灯光照明，暗光环境，夜景氛围",
    "日景": "白天场景，阳光充足，日间拍摄，明亮光线",
}

BLACKLIST_PEOPLE = ["人物", "主角", "演员", "人脸", "人", "有人", "男子", "女子", "小孩", "多人"]
BLACKLIST_HARD = ["人脸", "人物", "主角", "演员"]

def expand_query(query: str) -> str:
    original = query
    for keyword, expansion in QUERY_EXPANSION.items():
        if keyword in query:
            query = expansion
            break
    if query != original:
        print(f"[QUERY] 扩展: '{original}' -> '{query}'")
    return query

def is_people_shot(query: str, description: str) -> bool:
    q_lower = query.lower()
    if any(kw in q_lower for kw in ["空镜", "环境", "风景", "室内"]):
        desc_lower = description.lower()
        return any(bl in desc_lower for bl in BLACKLIST_HARD)
    return False

def score_adjustment(query: str, description: str) -> float:
    q_lower = query.lower()
    if any(kw in q_lower for kw in ["空镜", "环境", "风景", "室内"]):
        desc_lower = description.lower()
        for bl in BLACKLIST_PEOPLE:
            if bl in desc_lower:
                return -50.0
    return 0.0


class ErrorResponse(BaseModel):
    error: str
    query: str
    results: List = []
    total: int = 0


@router.post("/", response_model=SearchResponse)
async def search_videos(request: SearchRequest):
    original_query = request.query.strip() if request.query else ""

    if not original_query:
        return ErrorResponse(error="搜索词不能为空", query=original_query)

    try:
        chroma_service = get_chroma_service()

        if not chroma_service.model_ready:
            return ErrorResponse(error="搜索模型未就绪，请检查后端日志", query=original_query)

        expanded_query = expand_query(original_query)
        top_k = request.top_k or 20
        results = chroma_service.search(query=expanded_query, top_k=top_k * 2)

        print(f"[SEARCH] 原始: '{original_query}' -> 扩展: '{expanded_query}'")
        print(f"[SEARCH] 搜索返回 {len(results)} 条结果")
        if results:
            raw_dist = results[0].get('distance')
            print(f"   第一条原始distance: {raw_dist:.4f}")

        search_results = []
        for r in results:
            distance = r.get("distance", 0.0)
            match_score = round(max(0.0, (1.0 - distance) * 100.0), 1)

            description = r.get("description", "")

            if is_people_shot(original_query, description):
                match_score = 0.0

            adjustment = score_adjustment(original_query, description)
            if adjustment != 0.0:
                match_score = max(0.0, match_score + adjustment)

            if match_score < 30.0:
                continue

            if request.filters:
                filters = request.filters
                if filters.min_score and match_score < filters.min_score:
                    continue
                if filters.max_score and match_score > filters.max_score:
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
                description=description,
                timestamp=r.get("timestamp", 0.0),
                start_time=r.get("start_time", 0.0),
                end_time=r.get("end_time", 0.0),
                score=match_score
            ))
            print(f"   -> 距离:{distance:.3f} -> 匹配度:{match_score:.1f}%")

        return SearchResponse(
            query=original_query,
            results=search_results,
            total=len(search_results)
        )

    except Exception as e:
        print(f"[ERROR] 搜索错误: {e}")
        return ErrorResponse(error=f"搜索失败: {str(e)}", query=original_query)


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
