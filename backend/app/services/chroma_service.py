import os
import numpy as np
import uuid
import httpx
import base64
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from PIL import Image
from io import BytesIO
from typing import List, Optional, Tuple
import numpy as np


class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.collection_name = "video_frames"
        self._init_chroma()

    def _init_chroma(self):
        self.chroma_client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()

        try:
            self.collection = self.chroma_client.get_collection(name=self.collection_name)
            self.collection.delete(where={})
        except Exception:
            pass
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": "Video frame descriptions for semantic search"}
        )

    def add_frame(self, frame_path: str, description: str, video_path: str,
                  timestamp: float, start_time: float, end_time: float):
        doc_id = str(uuid.uuid4())

        self.collection.add(
            documents=[description],
            metadatas=[{
                "frame_path": frame_path,
                "video_path": video_path,
                "timestamp": timestamp,
                "start_time": start_time,
                "end_time": end_time,
                "description": description
            }],
            ids=[doc_id]
        )

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )

        search_results = []
        if results["ids"] and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                search_results.append({
                    "video_path": results["metadatas"][0][i]["video_path"],
                    "frame_path": results["metadatas"][0][i]["frame_path"],
                    "description": results["metadatas"][0][i]["description"],
                    "timestamp": results["metadatas"][0][i]["timestamp"],
                    "start_time": results["metadatas"][0][i]["start_time"],
                    "end_time": results["metadatas"][0][i]["end_time"],
                    "score": float(results["distances"][0][i]) if "distances" in results else 0.0
                })

        return search_results

    def clear(self):
        try:
            self.collection.delete(where={})
        except Exception:
            pass


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "llava"
        self.max_dim = 768
        self.jpeg_quality = 70

    def _resize_and_compress_image(self, frame):
        """
        终极万能图像瘦身：防 502 报错，且兼容路径、Base64 和 OpenCV 图像实体
        """
        if not frame:
            return ""

        img = None

        # 1. 智能侦测：看看传进来的 frame 到底是什么物种
        if isinstance(frame, str):
            # 情况 A：它传了一个文件路径过来
            if os.path.exists(frame):
                img = cv2.imread(frame)
            else:
                # 情况 B：它传了一串已经转好的 Base64 文本过来
                try:
                    img_data = base64.b64decode(frame)
                    nparr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                except Exception:
                    print("❌ 传入的字符串既不是文件路径，也不是有效的 Base64！")
                    return ""
        elif hasattr(frame, 'shape'):
            # 情况 C：非常标准，传的就是 OpenCV 图像实体
            img = frame
        else:
            print("❌ 未知格式的视频帧数据")
            return ""

        # 防御性判断，如果都没解析出来图片，直接放弃
        if img is None:
            return ""

        # 2. 限制物理分辨率：最大边长 768 像素 (Ollama 甜点区)
        height, width = img.shape[:2]
        max_size = 768
        
        if width > max_size or height > max_size:
            scale = max_size / max(width, height)
            img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        # 3. 限制体积：JPEG 高压缩
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        success, buffer = cv2.imencode('.jpg', img, encode_param)
        
        if not success:
            print("❌ OpenCV 压缩图片失败！")
            return ""
            
        # 4. 干净的 Base64 转码
        return base64.b64encode(buffer).decode('utf-8')

    def describe_frame(self, frame):
        """
        调用 Ollama 生成画面描述，带显存硬控
        """
        base64_str = self._resize_and_compress_image(frame)
        if not base64_str:
            return "无效画面"

        payload = {
            "model": "llava",
            "prompt": "作为专业视频导演，用中文简短描述画面的内容、光影和氛围，20字以内。",
            "images": [base64_str],
            "stream": False,
            "options": {
                "num_ctx": 2048,      # 锁死显存，防止大图撑爆
                "temperature": 0.2    # 降低 AI 幻觉
            }
        }

        try:
            import requests
            # 发送给本地的 Ollama
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                print(f"❌ Ollama 报错，状态码: {response.status_code}")
                return "大模型处理失败"
        except Exception as e:
            print(f"❌ 无法连接到 Ollama: {e}")
            return "连接超时"

class VideoProcessor:
    def __init__(self):
        self.ollama_service = OllamaService()
        self.frame_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frames")
        os.makedirs(self.frame_dir, exist_ok=True)
        self.ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"
        self.ffprobe_path = r"C:\ffmpeg\bin\ffprobe.exe"
        self.diff_threshold = 0.20
        self.time_window = 5.0

    def _get_video_duration(self, video_path: str) -> float:
        import subprocess
        try:
            result = subprocess.run(
                [self.ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
                capture_output=True,
                timeout=30
            )
            duration_str = result.stdout.decode('utf-8', errors='ignore').strip()
            return float(duration_str) if duration_str else 60
        except Exception:
            return 60

    def _extract_frame_as_gray(self, video_path: str, timestamp: float, output_path: str) -> Optional[np.ndarray]:
        import subprocess
        try:
            subprocess.run([
                self.ffmpeg_path, "-ss", str(timestamp), "-i", video_path,
                "-vframes", "1", "-vf", "rgb2gray", "-y", output_path
            ], capture_output=True, timeout=15)

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                img = Image.open(output_path)
                return np.array(img)
            return None
        except Exception as e:
            print(f"Error extracting frame at {timestamp}s: {e}")
            return None

    def _calculate_histogram_diff(self, gray1: np.ndarray, gray2: np.ndarray) -> float:
        hist1, _ = np.histogram(gray1, bins=256, range=(0, 256))
        hist2, _ = np.histogram(gray2, bins=256, range=(0, 256))

        hist1 = hist1.astype(float) / (hist1.sum() + 1e-10)
        hist2 = hist2.astype(float) / (hist2.sum() + 1e-10)

        diff = np.abs(hist1 - hist2).sum() / 2.0
        return diff

    def _calculate_time_range(self, timestamp: float, duration: float) -> Tuple[float, float]:
        start_time = max(0.0, timestamp - self.time_window)
        end_time = min(duration, timestamp + self.time_window)
        return start_time, end_time

    def extract_frames(self, video_path: str) -> List[Tuple[str, float, float, float]]:
        import subprocess

        duration = self._get_video_duration(video_path)
        safe_name = "".join(c if c.isalnum() else "_" for c in os.path.basename(video_path))

        candidate_timestamps = []
        second = 0
        while second < duration:
            candidate_timestamps.append(second)
            second += 1

        key_frames = []
        prev_gray = None
        prev_timestamp = None

        for ts in candidate_timestamps:
            temp_path = os.path.join(self.frame_dir, f"{safe_name}_temp_{int(ts)}.jpg")
            gray = self._extract_frame_as_gray(video_path, ts, temp_path)

            if gray is None:
                continue

            if prev_gray is not None:
                diff = self._calculate_histogram_diff(prev_gray, gray)

                if diff >= self.diff_threshold:
                    start_time, end_time = self._calculate_time_range(ts, duration)
                    final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(ts)}.jpg")
                    try:
                        os.rename(temp_path, final_path)
                        key_frames.append((final_path, ts, start_time, end_time))
                    except Exception:
                        pass
                else:
                    try:
                        os.remove(temp_path)
                    except Exception:
                        pass
            else:
                start_time, end_time = self._calculate_time_range(ts, duration)
                final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(ts)}.jpg")
                try:
                    os.rename(temp_path, final_path)
                    key_frames.append((final_path, ts, start_time, end_time))
                except Exception:
                    pass

            prev_gray = gray
            prev_timestamp = ts

        if not key_frames:
            last_ts = max(0, duration - 1)
            start_time, end_time = self._calculate_time_range(last_ts, duration)
            final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(last_ts)}.jpg")
            gray = self._extract_frame_as_gray(video_path, last_ts, final_path)
            if gray is not None:
                key_frames.append((final_path, last_ts, start_time, end_time))

        return key_frames

    def process_video(self, video_path: str) -> List[dict]:
        duration = self._get_video_duration(video_path)
        frames = self.extract_frames(video_path)
        print(f"Detected {len(frames)} key frames")
        results = []

        for i, (frame_path, timestamp, start_time, end_time) in enumerate(frames):
            print(f"Processing frame {i+1}/{len(frames)} at {timestamp}s (segment: {start_time:.1f}s - {end_time:.1f}s)...")
            description = self.ollama_service.describe_frame(frame_path)
            if description:
                results.append({
                    "frame_path": frame_path,
                    "video_path": video_path,
                    "timestamp": timestamp,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description
                })

        return results
