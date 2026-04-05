from pydantic import BaseModel
from typing import List, Optional


class ProcessRequest(BaseModel):
    folder_path: str


class ProcessResponse(BaseModel):
    status: str
    message: str
    processed_videos: int
    total_frames: int


class ProcessStatus(BaseModel):
    is_processing: bool
    current_video: str
    current_video_index: int
    total_videos: int
    current_frame_index: int
    total_frames: int
    processed_videos: int
    processed_frames: int
    status: str
    message: str
    start_time: Optional[str] = None
    error: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 10


class VideoMetadata(BaseModel):
    video_path: str
    frame_path: str
    description: str
    timestamp: float


class SearchResult(BaseModel):
    video_path: str
    frame_path: str
    description: str
    timestamp: float
    start_time: float
    end_time: float
    score: float


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int
