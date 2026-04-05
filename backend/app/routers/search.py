from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.models.schemas import SearchRequest, SearchResponse, SearchResult
from app.services.chroma_service import ChromaService

router = APIRouter()


class ErrorResponse(BaseModel):
    error: str
    query: str
    results: List = []
    total: int = 0


@router.post("/")
async def search_videos(request: SearchRequest):
    query = request.query.strip() if request.query else ""

    if not query:
        return ErrorResponse(error="搜索词不能为空", query=query)

    try:
        chroma_service = ChromaService()

        if not chroma_service.model_ready:
            return ErrorResponse(error="搜索模型未就绪，请检查后端日志", query=query)

        results = chroma_service.search(query=query, top_k=request.top_k or 10)
        print(f"🔍 搜索返回 {len(results)} 条结果")
        if results:
            print(f"   第一条: distance={results[0].get('distance')}")

        search_results = []
        for r in results:
            distance = r.get("distance", 0.0)
            similarity = 100.0 / (1.0 + distance)
            search_results.append(SearchResult(
                video_path=r.get("video_path", ""),
                frame_path=r.get("frame_path", ""),
                description=r.get("description", ""),
                timestamp=r.get("timestamp", 0.0),
                start_time=r.get("start_time", 0.0),
                end_time=r.get("end_time", 0.0),
                score=similarity
            ))
            print(f"   → 最终相似度: {similarity:.2f}%")

        return SearchResponse(
            query=query,
            results=search_results,
            total=len(search_results)
        )

    except Exception as e:
        print(f"❌ 搜索错误: {e}")
        return ErrorResponse(error=f"搜索失败: {str(e)}", query=query)
