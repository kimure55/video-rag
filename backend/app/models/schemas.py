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


class FilterOptions(BaseModel):
    min_score: Optional[float] = 0.0
    max_score: Optional[float] = 100.0
    resolution: Optional[str] = None
    shot_size: Optional[str] = None
    camera_movement: Optional[str] = None
    lighting: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 20
    filters: Optional[FilterOptions] = None


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


class WatchFolderRequest(BaseModel):
    folder_path: str


class WatchFolderResponse(BaseModel):
    status: str
    message: str
    watch_path: str


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total: int
