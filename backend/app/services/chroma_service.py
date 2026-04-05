import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

import cv2
import base64
import requests
import numpy as np
import uuid
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from PIL import Image
from typing import List, Optional, Tuple


class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.collection_name = "video_frames"
        self.model_ready = False
        self._init_chroma()
        self._init_embedding_model()

    def _init_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            print("⏳ 正在加载 moka-ai/m3e-base 嵌入模型（CPU）...")
            self.encoder = SentenceTransformer('moka-ai/m3e-base', device='cpu')
            self.model_ready = True
            print("✅ moka-ai/m3e-base 嵌入模型加载成功！")
        except Exception as e:
            print(f"❌ 嵌入模型加载失败: {e}")
            print("💡 请手动下载模型：https://huggingface.co/moka-ai/m3e-base")
            self.model_ready = False

    def _init_chroma(self):
        try:
            self.chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(anonymized_telemetry=False)
            )

            expected_dim = 768

            try:
                self.collection = self.chroma_client.get_collection(name=self.collection_name)
                existing_dim = self.collection.metadata.get("embedding_dimension", 0)

                if existing_dim != expected_dim:
                    print(f"⚠️ 数据库维度不匹配（现有: {existing_dim}, 需要: {expected_dim}），正在删除旧数据库...")
                    self.chroma_client.delete_collection(name=self.collection_name)
                    self.collection = self.chroma_client.get_or_create_collection(
                        name=self.collection_name,
                        metadata={
                            "description": "Video frame descriptions for semantic search",
                            "embedding_dimension": expected_dim
                        }
                    )
                    print("✅ 新数据库已创建（768维度）")
                else:
                    print(f"✅ 数据库维度匹配: {existing_dim}")

            except Exception:
                self.collection = self.chroma_client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={
                        "description": "Video frame descriptions for semantic search",
                        "embedding_dimension": expected_dim
                    }
                )
                print("✅ 新数据库已创建（768维度）")

        except Exception as e:
            print(f"❌ ChromaDB 初始化失败: {e}")
            raise

    def add_frame(self, frame_path: str, description: str, video_path: str,
                  timestamp: float, start_time: float, end_time: float):
        if not self.model_ready:
            print("⚠️ 嵌入模型未就绪，跳过添加")
            return

        doc_id = str(uuid.uuid4())

        try:
            embedding = self.encoder.encode(description).tolist()

            self.collection.add(
                embeddings=[embedding],
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
        except Exception as e:
            print(f"❌ 添加帧数据失败: {e}")

    def search(self, query: str, top_k: int = 10) -> List[dict]:
        if not query or not query.strip():
            return []

        if not self.model_ready:
            print("⚠️ 嵌入模型未就绪，无法执行搜索")
            return []

        try:
            query_embedding = self.encoder.encode(query.strip()).tolist()

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )

            search_results = []
            if results and results["ids"] and len(results["ids"]) > 0:
                for i in range(len(results["ids"][0])):
                    search_results.append({
                        "video_path": results["metadatas"][0][i].get("video_path", ""),
                        "frame_path": results["metadatas"][0][i].get("frame_path", ""),
                        "description": results["metadatas"][0][i].get("description", ""),
                        "timestamp": results["metadatas"][0][i].get("timestamp", 0.0),
                        "start_time": results["metadatas"][0][i].get("start_time", 0.0),
                        "end_time": results["metadatas"][0][i].get("end_time", 0.0),
                        "distance": float(results["distances"][0][i]) if results.get("distances") else 1.0
                    })

            return search_results

        except Exception as e:
            print(f"❌ 搜索失败: {e}")
            return []

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

    def _resize_and_compress_image(self, frame_data):
        if not frame_data:
            return ""

        img = None

        if isinstance(frame_data, str):
            abs_path = os.path.abspath(frame_data)
            if os.path.exists(abs_path):
                img = cv2.imread(abs_path)
            else:
                print(f"❌ 找不到图片文件: {abs_path}")
                return ""
        elif hasattr(frame_data, 'shape'):
            img = frame_data
        else:
            print("❌ 传入的数据既不是路径也不是图像！")
            return ""

        if img is None:
            return ""

        height, width = img.shape[:2]
        max_size = 768

        if width > max_size or height > max_size:
            scale = max_size / max(width, height)
            img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 70]
        success, buffer = cv2.imencode('.jpg', img, encode_param)

        if not success:
            print("❌ 图片压缩失败！")
            return ""

        return base64.b64encode(buffer).decode('utf-8')

    def describe_frame(self, frame):
        base64_str = self._resize_and_compress_image(frame)
        if not base64_str:
            return "无效画面"

        payload = {
            "model": "llava",
            "prompt": "作为专业视频导演，用中文简短描述画面的内容，光影和氛围，20字以内。",
            "images": [base64_str],
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.2
            }
        }

        try:
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
        self.diff_threshold = 0.20
        self.time_window = 5.0

    def _get_video_duration(self, video_path: str) -> float:
        abs_path = os.path.normpath(video_path)
        print(f"📹 读取视频路径: {abs_path}")

        try:
            cap = cv2.VideoCapture(abs_path)
            if not cap.isOpened():
                print(f"❌ OpenCV 无法打开视频: {abs_path}")
                return 60

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps if fps > 0 else 60
            cap.release()

            print(f"⏱️ 视频时长: {duration} 秒 (FPS: {fps}, 帧数: {frame_count})")
            return duration

        except Exception as e:
            print(f"❌ 获取视频时长失败: {e}")
            return 60

    def _extract_frame(self, video_path: str, timestamp: float, output_path: str) -> Optional[np.ndarray]:
        abs_video_path = os.path.normpath(video_path)
        abs_output_path = os.path.normpath(output_path)

        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)

        try:
            cap = cv2.VideoCapture(abs_video_path)
            if not cap.isOpened():
                print(f"❌ OpenCV 无法打开视频: {abs_video_path}")
                return None

            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                print(f"❌ 无法读取帧 (timestamp={timestamp})")
                return None

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            success, buffer = cv2.imencode('.jpg', frame, encode_param)

            if success:
                with open(abs_output_path, 'wb') as f:
                    f.write(buffer.tobytes())
                print(f"✅ 已生成图片: {abs_output_path} ({os.path.getsize(abs_output_path)} bytes)")
                return frame
            else:
                print(f"❌ 编码图片失败: {abs_output_path}")
                return None

        except Exception as e:
            print(f"❌ 抽帧异常 (timestamp={timestamp}): {type(e).__name__}: {e}")
            return None

    def _extract_frame_for_comparison(self, video_path: str, timestamp: float, output_path: str) -> Optional[np.ndarray]:
        abs_video_path = os.path.normpath(video_path)
        abs_output_path = os.path.normpath(output_path)

        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)

        try:
            cap = cv2.VideoCapture(abs_video_path)
            if not cap.isOpened():
                print(f"❌ OpenCV 无法打开视频: {abs_video_path}")
                return None

            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                print(f"❌ 无法读取帧 (timestamp={timestamp})")
                return None

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            success, buffer = cv2.imencode('.jpg', gray, encode_param)

            if success:
                with open(abs_output_path, 'wb') as f:
                    f.write(buffer.tobytes())
                return gray
            else:
                print(f"❌ 编码图片失败: {abs_output_path}")
                return None

        except Exception as e:
            print(f"❌ 抽帧异常 (timestamp={timestamp}): {type(e).__name__}: {e}")
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
        abs_video_path = os.path.normpath(video_path)
        print(f"🎬 开始处理视频: {abs_video_path}")

        duration = self._get_video_duration(abs_video_path)
        safe_name = "".join(c if c.isalnum() else "_" for c in os.path.basename(abs_video_path))

        print(f"🔍 策略1: 场景切换检测 (阈值: {self.diff_threshold})")
        candidate_timestamps = []
        second = 0
        while second < duration:
            candidate_timestamps.append(second)
            second += 1

        key_frames = []
        prev_gray = None

        for ts in candidate_timestamps:
            temp_gray_path = os.path.join(self.frame_dir, f"{safe_name}_temp_gray_{int(ts)}.jpg")
            temp_color_path = os.path.join(self.frame_dir, f"{safe_name}_temp_color_{int(ts)}.jpg")

            gray = self._extract_frame_for_comparison(abs_video_path, ts, temp_gray_path)
            color_frame = self._extract_frame(abs_video_path, ts, temp_color_path)

            if gray is None or color_frame is None:
                continue

            if prev_gray is not None:
                diff = self._calculate_histogram_diff(prev_gray, gray)

                if diff >= self.diff_threshold:
                    start_time, end_time = self._calculate_time_range(ts, duration)
                    final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(ts)}.jpg")
                    try:
                        if os.path.exists(temp_color_path):
                            os.rename(temp_color_path, final_path)
                            key_frames.append((final_path, ts, start_time, end_time))
                            print(f"🖼️ 关键帧: {ts}s -> {final_path} (差异度: {diff:.3f})")
                    except Exception as e:
                        print(f"❌ 移动文件失败: {e}")
                    try:
                        if os.path.exists(temp_gray_path):
                            os.remove(temp_gray_path)
                    except Exception:
                        pass
                else:
                    try:
                        if os.path.exists(temp_gray_path):
                            os.remove(temp_gray_path)
                        if os.path.exists(temp_color_path):
                            os.remove(temp_color_path)
                    except Exception:
                        pass
            else:
                start_time, end_time = self._calculate_time_range(ts, duration)
                final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(ts)}.jpg")
                try:
                    if os.path.exists(temp_color_path):
                        os.rename(temp_color_path, final_path)
                        key_frames.append((final_path, ts, start_time, end_time))
                        print(f"🖼️ 首帧: {ts}s -> {final_path}")
                    if os.path.exists(temp_gray_path):
                        os.remove(temp_gray_path)
                except Exception as e:
                    print(f"❌ 移动文件失败: {e}")

            prev_gray = gray

        print(f"📊 场景检测结果: {len(key_frames)} 个关键帧")

        if len(key_frames) < 2:
            print(f"🔄 关键帧太少，启用保底策略: 每5秒抽一帧")
            key_frames = []
            prev_gray = None

            fallback_ts = 0
            while fallback_ts < duration:
                temp_gray_path = os.path.join(self.frame_dir, f"{safe_name}_fallback_gray_{int(fallback_ts)}.jpg")
                temp_color_path = os.path.join(self.frame_dir, f"{safe_name}_fallback_color_{int(fallback_ts)}.jpg")

                gray = self._extract_frame_for_comparison(abs_video_path, fallback_ts, temp_gray_path)
                color_frame = self._extract_frame(abs_video_path, fallback_ts, temp_color_path)

                if gray is not None and color_frame is not None:
                    start_time, end_time = self._calculate_time_range(fallback_ts, duration)
                    final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_{int(fallback_ts)}.jpg")
                    try:
                        if os.path.exists(temp_color_path):
                            os.rename(temp_color_path, final_path)
                            key_frames.append((final_path, fallback_ts, start_time, end_time))
                            print(f"🖼️ 保底帧: {fallback_ts}s -> {final_path}")
                        if os.path.exists(temp_gray_path):
                            os.remove(temp_gray_path)
                    except Exception:
                        pass

                fallback_ts += 5

            print(f"📊 保底策略结果: {len(key_frames)} 个帧")

        if not key_frames:
            last_ts = max(0, duration - 1)
            start_time, end_time = self._calculate_time_range(last_ts, duration)
            final_path = os.path.join(self.frame_dir, f"{safe_name}_frame_last.jpg")
            color_frame = self._extract_frame(abs_video_path, last_ts, final_path)
            if color_frame is not None:
                key_frames.append((final_path, last_ts, start_time, end_time))
                print(f"🖼️ 末尾帧: {last_ts}s -> {final_path}")

        return key_frames

    def process_video(self, video_path: str) -> List[dict]:
        abs_video_path = os.path.normpath(video_path)
        duration = self._get_video_duration(abs_video_path)
        frames = self.extract_frames(abs_video_path)
        print(f"Detected {len(frames)} key frames")
        results = []

        for i, (frame_path, timestamp, start_time, end_time) in enumerate(frames):
            print(f"Processing frame {i+1}/{len(frames)} at {timestamp}s (segment: {start_time:.1f}s - {end_time:.1f}s)...")
            description = self.ollama_service.describe_frame(frame_path)
            if description:
                results.append({
                    "frame_path": frame_path,
                    "video_path": abs_video_path,
                    "timestamp": timestamp,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description
                })

        return results
