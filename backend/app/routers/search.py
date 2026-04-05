from fastapi import APIRouter, HTTPException
from app.models.schemas import SearchRequest, SearchResponse, SearchResult
from app.services.chroma_service import ChromaService

router = APIRouter()


@router.post("/", response_model=SearchResponse)
async def search_videos(request: SearchRequest):
    if not request.query or len(request.query.strip()) == 0:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    try:
        chroma_service = ChromaService()
        results = chroma_service.search(query=request.query, top_k=request.top_k)

        search_results = [
            SearchResult(
                video_path=r["video_path"],
                frame_path=r["frame_path"],
                description=r["description"],
                timestamp=r["timestamp"],
                score=r["score"]
            )
            for r in results
        ]

        return SearchResponse(
            query=request.query,
            results=search_results,
            total=len(search_results)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")
