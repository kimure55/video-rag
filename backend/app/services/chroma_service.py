import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

import cv2
import base64
import requests
import numpy as np
import uuid
import hashlib
import time
import threading
import chromadb
from chromadb.config import Settings
from PIL import Image
from typing import List, Optional, Tuple, Dict, Set
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import threading


class ChromaService:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.collection_name = "video_frames"
        self.model_ready = False
        self._processed_videos: Set[str] = set()
        self._lock = threading.Lock()
        self._init_chroma()
        self._init_embedding_model()
        self._load_processed_videos()

    def _init_embedding_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            print("[WAIT] 正在加载 moka-ai/m3e-base 嵌入模型（CPU）...")
            self.encoder = SentenceTransformer('moka-ai/m3e-base', device='cpu')
            self.model_ready = True
            print("[OK] moka-ai/m3e-base 嵌入模型加载成功！")
        except Exception as e:
            print(f"[ERROR] 嵌入模型加载失败: {e}")
            print("[TIP] 请手动下载模型：https://huggingface.co/moka-ai/m3e-base")
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
                    print(f"[WARN] 数据库维度不匹配（现有: {existing_dim}, 需要: {expected_dim}），正在删除旧数据库...")
                    self.chroma_client.delete_collection(name=self.collection_name)
                    self.collection = self._create_collection_with_hnsw()
                else:
                    print(f"[OK] 数据库维度匹配: {existing_dim}")

            except Exception:
                self.collection = self._create_collection_with_hnsw()

        except Exception as e:
            print(f"[ERROR] ChromaDB 初始化失败: {e}")
            raise

    def _create_collection_with_hnsw(self):
        print("[CONFIG] 创建 Collection (cosine similarity)")
        collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "description": "Video frame descriptions for semantic search",
                "embedding_dimension": 768,
                "hnsw:space": "cosine"
            }
        )
        print("[OK] 新数据库已创建")
        return collection

    def _ensure_hnsw_index(self):
        try:
            current_m = self.collection.metadata.get("hnsw:M")
            if current_m != 32:
                print(f"[CONFIG] 更新 HNSW 参数: M=32, ef=128")
                self.collection.modify(
                    metadata={
                        "hnsw:M": 32,
                        "hnsw:ef_construction": 200,
                        "hnsw:ef_search": 128
                    }
                )
        except Exception as e:
            print(f"[WARN] HNSW参数更新失败: {e}")

    def _load_processed_videos(self):
        try:
            all_data = self.collection.get()
            if all_data and all_data["metadatas"]:
                for meta in all_data["metadatas"]:
                    video_path = meta.get("video_path", "")
                    if video_path:
                        self._processed_videos.add(self._normalize_path(video_path))
            print(f"[LOAD] 已加载 {len(self._processed_videos)} 个已处理视频记录")
        except Exception as e:
            print(f"[WARN] 加载已处理视频记录失败: {e}")

    def _normalize_path(self, path: str) -> str:
        return os.path.normpath(os.path.abspath(path))

    def _get_video_hash(self, video_path: str) -> str:
        normalized = self._normalize_path(video_path)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def is_video_processed(self, video_path: str) -> bool:
        normalized = self._normalize_path(video_path)
        return normalized in self._processed_videos

    def mark_video_processed(self, video_path: str):
        normalized = self._normalize_path(video_path)
        with self._lock:
            self._processed_videos.add(normalized)

    def add_frame(self, frame_path: str, description: str, video_path: str,
                  timestamp: float, start_time: float, end_time: float):
        if not self.model_ready:
            print("[WARN] 嵌入模型未就绪，跳过添加")
            return False

        doc_id = str(uuid.uuid4())
        normalized_video = self._normalize_path(video_path)

        try:
            embedding = self.encoder.encode(description).tolist()

            self.collection.add(
                embeddings=[embedding],
                documents=[description],
                metadatas=[{
                    "frame_path": frame_path,
                    "video_path": normalized_video,
                    "video_hash": self._get_video_hash(normalized_video),
                    "timestamp": timestamp,
                    "start_time": start_time,
                    "end_time": end_time,
                    "description": description,
                    "shot_size": "",
                    "camera_movement": "",
                    "lighting": "",
                    "composition": "",
                    "action": "",
                    "processed_at": str(np.datetime64('now'))
                }],
                ids=[doc_id]
            )
            return True
        except Exception as e:
            print(f"[ERROR] 添加帧数据失败: {e}")
            return False

    def add_frames_batch(self, frames: List[dict], max_workers: int = 4) -> int:
        if not frames:
            return 0

        successful = 0
        embedding_lock = threading.Lock()

        def encode_frame(desc):
            return self.encoder.encode(desc).tolist()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_frame = {
                executor.submit(encode_frame, frame["description"]): frame
                for frame in frames
            }

            embeddings_list = []
            for future in as_completed(future_to_frame):
                frame = future_to_frame[future]
                try:
                    embedding = future.result()
                    embeddings_list.append(embedding)
                except Exception as e:
                    print(f"[WARN] Embedding失败: {e}")
                    embeddings_list.append(None)

        embeddings_to_add = []
        documents_to_add = []
        metadatas_to_add = []
        ids_to_add = []

        for i, frame in enumerate(frames):
            if embeddings_list[i] is None:
                continue

            doc_id = str(uuid.uuid4())
            normalized_video = self._normalize_path(frame["video_path"])

            embeddings_to_add.append(embeddings_list[i])
            documents_to_add.append(frame["description"])
            metadatas_to_add.append({
                "frame_path": frame["frame_path"],
                "video_path": normalized_video,
                "video_hash": self._get_video_hash(normalized_video),
                "timestamp": frame["timestamp"],
                "start_time": frame["start_time"],
                "end_time": frame["end_time"],
                "description": frame["description"],
                "shot_size": frame.get("shot_size", ""),
                "camera_movement": frame.get("camera_movement", ""),
                "lighting": frame.get("lighting", ""),
                "composition": frame.get("composition", ""),
                "action": frame.get("action", ""),
                "processed_at": str(np.datetime64('now'))
            })
            ids_to_add.append(doc_id)

        if embeddings_to_add:
            try:
                self.collection.add(
                    embeddings=embeddings_to_add,
                    documents=documents_to_add,
                    metadatas=metadatas_to_add,
                    ids=ids_to_add
                )
                successful = len(embeddings_to_add)
                print(f"[OK] 批量添加 {successful} 个帧到数据库")
            except Exception as e:
                print(f"[ERROR] 批量添加失败: {e}")

        return successful

    def search(self, query: str, top_k: int = 10, min_score: float = 0.0) -> List[dict]:
        if not query or not query.strip():
            return []

        if not self.model_ready:
            print("[WARN] 嵌入模型未就绪，无法执行搜索")
            return []

        try:
            query_embedding = self.encoder.encode(query.strip()).tolist()

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"timestamp": {"$gte": 0}}
            )

            search_results = []
            if results and results["ids"] and len(results["ids"]) > 0:
                for i in range(len(results["ids"][0])):
                    distance = float(results["distances"][0][i]) if results.get("distances") else 1.0
                    match_score = round(max(0.0, (1.0 - distance) * 100.0), 1)

                    if match_score >= min_score:
                        search_results.append({
                            "video_path": results["metadatas"][0][i].get("video_path", ""),
                            "frame_path": results["metadatas"][0][i].get("frame_path", ""),
                            "description": results["metadatas"][0][i].get("description", ""),
                            "timestamp": results["metadatas"][0][i].get("timestamp", 0.0),
                            "start_time": results["metadatas"][0][i].get("start_time", 0.0),
                            "end_time": results["metadatas"][0][i].get("end_time", 0.0),
                            "distance": distance,
                            "match_score": match_score,
                            "shot_size": results["metadatas"][0][i].get("shot_size", ""),
                            "camera_movement": results["metadatas"][0][i].get("camera_movement", ""),
                            "lighting": results["metadatas"][0][i].get("lighting", ""),
                            "composition": results["metadatas"][0][i].get("composition", ""),
                            "action": results["metadatas"][0][i].get("action", ""),
                            "processed_at": results["metadatas"][0][i].get("processed_at", "")
                        })

            return search_results

        except Exception as e:
            print(f"[ERROR] 搜索失败: {e}")
            return []

    def get_all_frames(self, video_path: Optional[str] = None) -> List[dict]:
        try:
            if video_path:
                where_filter = {"video_path": self._normalize_path(video_path)}
                results = self.collection.get(where=where_filter)
            else:
                results = self.collection.get()

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
            return frames
        except Exception as e:
            print(f"[ERROR] 获取帧列表失败: {e}")
            return []

    def get_video_list(self) -> List[dict]:
        try:
            all_data = self.collection.get()
            video_info = {}

            if all_data and all_data["metadatas"]:
                for meta in all_data["metadatas"]:
                    video_path = meta.get("video_path", "")
                    if video_path and video_path not in video_info:
                        video_info[video_path] = {
                            "video_path": video_path,
                            "frame_count": 0,
                            "processed_at": meta.get("processed_at", "")
                        }
                    if video_path:
                        video_info[video_path]["frame_count"] += 1

            return list(video_info.values())
        except Exception as e:
            print(f"[ERROR] 获取视频列表失败: {e}")
            return []

    def delete_video_frames(self, video_path: str) -> bool:
        try:
            normalized = self._normalize_path(video_path)
            self.collection.delete(where={"video_path": normalized})
            if normalized in self._processed_videos:
                self._processed_videos.discard(normalized)
            print(f"[DELETE] 已删除视频 {video_path} 的所有帧")
            return True
        except Exception as e:
            print(f"[ERROR] 删除视频帧失败: {e}")
            return False

    def clear(self):
        try:
            self.collection.delete(where={})
            self._processed_videos.clear()
        except Exception:
            pass


class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.model = "llava"
        self.max_dim = 768
        self.jpeg_quality = 85
        self._process_pool = None
        self._thread_pool = None
        self.max_workers = min(4, max(1, cpu_count() - 1))
        self._ollama_lock = threading.Lock()
        self._ollama_concurrent = 0
        self._ollama_max_concurrent = 2

    def _get_process_pool(self):
        if self._process_pool is None:
            self._process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        return self._process_pool

    def _get_thread_pool(self):
        if self._thread_pool is None:
            self._thread_pool = ThreadPoolExecutor(max_workers=self.max_workers * 2)
        return self._thread_pool

    def describe_frame(self, frame_path: str) -> dict:
        base64_str = self._encode_image_safe(frame_path)
        if not base64_str:
            return self._empty_description()

        prompt = """你是一位专业影视摄影师。请用一段自然的行业术语描述这个画面。

严格按以下格式开头（必须包含方括号）：
[有/无人物] [室内/室外] [时间] [主要场景]

然后用一段连贯的话描述：主体的动作表情、画面的影调氛围（冷/暖/高反差等）、以及镜头传达的情绪。如果画面有文字请记录。

禁止使用"1.景别 2.光影"这种编号格式。""".replace("\n", " ").strip()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64_str],
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "temperature": 0.1,
                "top_p": 0.9
            }
        }

        max_retries = 3
        for attempt in range(max_retries):
            with self._ollama_lock:
                while self._ollama_concurrent >= self._ollama_max_concurrent:
                    time.sleep(0.5)
                self._ollama_concurrent += 1
            try:
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=60
                )
                if response.status_code == 200:
                    result = response.json().get("response", "").strip()
                    return self._parse_description_result(result)
                else:
                    print(f"[WARN] Ollama 响应错误: {response.status_code}")
            except requests.exceptions.Timeout:
                print(f"[WAIT] Ollama 超时 (尝试 {attempt + 1}/{max_retries})")
            except Exception as e:
                print(f"[ERROR] Ollama 请求失败: {e}")
            finally:
                with self._ollama_lock:
                    self._ollama_concurrent = max(0, self._ollama_concurrent - 1)

        return self._empty_description()

    def _empty_description(self) -> dict:
        return {
            "shot_size": "",
            "camera_movement": "",
            "lighting": "",
            "composition": "",
            "action": "",
            "full_description": ""
        }

    def _parse_description_result(self, text: str) -> dict:
        result = {
            "shot_size": "",
            "camera_movement": "",
            "lighting": "",
            "composition": "",
            "action": "",
            "full_description": text.strip()
        }

        text_lower = text.lower()

        shot_sizes = ["特写", "近景", "中景", "远景", "全景", "大远景", "中近景", "双人"]
        for s in shot_sizes:
            if s in text:
                result["shot_size"] = s
                break

        movements = ["固定", "推镜", "拉镜", "摇镜", "移镜", "跟拍", "手持", "航拍", "升降"]
        for m in movements:
            if m in text:
                result["camera_movement"] = m
                break

        lights = ["自然光", "硬光", "软光", "逆光", "侧光", "顶光", "柔光", "强光", "暗光"]
        for l in lights:
            if l in text:
                result["lighting"] = l
                break

        return result

    def describe_frames_parallel(self, frame_paths: List[str], max_workers: int = 4) -> List[dict]:
        results = [self._empty_description()] * len(frame_paths)
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(self.describe_frame, path): i
                for i, path in enumerate(frame_paths)
                if path
            }

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                    completed += 1
                    if completed % 5 == 0:
                        print(f"[STAT] 已完成 {completed}/{len(frame_paths)} 帧描述")
                except Exception as e:
                    print(f"[WARN] 帧描述失败 [{index}]: {e}")

        return results

    def _encode_image_safe(self, image_path: str) -> str:
        try:
            abs_path = os.path.abspath(image_path)
            if not os.path.exists(abs_path):
                print(f"[ERROR] 图片不存在: {abs_path}")
                return ""

            img = cv2.imread(abs_path)
            if img is None:
                img = self._try_pil_read(abs_path)
            if img is None:
                return ""

            height, width = img.shape[:2]
            max_size = 1024

            if width > max_size or height > max_size:
                scale = max_size / max(width, height)
                img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            success, buffer = cv2.imencode('.jpg', img, encode_param)

            if success:
                return base64.b64encode(buffer).decode('utf-8')
            return ""

        except Exception as e:
            print(f"[ERROR] 图片编码失败 ({image_path}): {e}")
            return ""

    def _try_pil_read(self, path: str) -> Optional[np.ndarray]:
        try:
            from PIL import Image
            img = Image.open(path)
            img = img.convert('RGB')
            return np.array(img)
        except Exception:
            return None

    def shutdown(self):
        if self._process_pool:
            self._process_pool.shutdown(wait=False)
            self._process_pool = None
        if self._thread_pool:
            self._thread_pool.shutdown(wait=False)
            self._thread_pool = None


class VideoProcessor:
    def __init__(self):
        self.ollama_service = OllamaService()
        self.frame_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frames")
        os.makedirs(self.frame_dir, exist_ok=True)
        self.diff_threshold = 0.15
        self.time_window = 3.0
        self.sample_interval = 1.0
        self.max_frames_per_video = 500

    def _normalize_path(self, path: str) -> str:
        return os.path.normpath(os.path.abspath(path))

    def _safe_filename(self, video_path: str) -> str:
        hash_str = str(hash(video_path))
        return f"video_{hash_str}"

    def _get_video_info(self, video_path: str) -> dict:
        abs_path = os.path.normpath(os.path.abspath(video_path))

        try:
            cap = cv2.VideoCapture(abs_path)
            if not cap.isOpened():
                try:
                    cap.release()
                    cap = cv2.VideoCapture(abs_path)
                except:
                    pass

            if not cap.isOpened():
                print(f"[ERROR] OpenCV 无法打开视频: {abs_path}")
                return {"duration": 60, "fps": 30, "width": 1920, "height": 1080, "frame_count": 1800}

            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 60

            cap.release()

            return {
                "duration": duration,
                "fps": fps,
                "width": width,
                "height": height,
                "frame_count": frame_count,
                "resolution": f"{width}x{height}"
            }
        except Exception as e:
            print(f"[ERROR] 获取视频信息失败: {e}")
            return {"duration": 60, "fps": 30, "width": 1920, "height": 1080, "frame_count": 1800, "resolution": "1920x1080"}

    def _extract_frame_safe(self, video_path: str, timestamp: float, output_path: str) -> Optional[np.ndarray]:
        abs_video_path = os.path.normpath(os.path.abspath(video_path))
        abs_output_path = os.path.normpath(os.path.abspath(output_path))

        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)

        try:
            cap = cv2.VideoCapture(abs_video_path)
            if not cap.isOpened():
                try:
                    cap.release()
                    cap = cv2.VideoCapture(abs_video_path)
                except:
                    pass

            if not cap.isOpened():
                print(f"[ERROR] 无法打开视频: {abs_video_path}")
                return None

            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                return None

            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
            success, buffer = cv2.imencode('.jpg', frame, encode_param)

            if success:
                buffer.tofile(abs_output_path)
                return frame
            return None

        except Exception as e:
            print(f"[ERROR] 抽帧异常: {type(e).__name__}: {e}")
            return None

    def _calculate_scene_diff(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        if frame1 is None or frame2 is None:
            return 0.0

        try:
            gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

            hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
            hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])

            cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
            cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)

            diff = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
            return 1.0 - max(0, diff)
        except:
            return 0.0

    def _calculate_time_range(self, timestamp: float, duration: float) -> Tuple[float, float]:
        half_window = self.time_window / 2
        start_time = max(0.0, timestamp - half_window)
        end_time = min(duration, timestamp + half_window)
        return start_time, end_time

    def extract_keyframes(self, video_path: str, force: bool = False) -> List[Tuple[str, float, float, float, dict]]:
        abs_video_path = os.path.normpath(os.path.abspath(video_path))
        safe_name = self._safe_filename(video_path)
        video_info = self._get_video_info(abs_video_path)
        duration = video_info["duration"]
        cpu_cores = min(4, max(1, cpu_count() - 1))

        print(f"[VIDEO] 处理视频: {abs_video_path}")
        print(f"   分辨率: {video_info['resolution']}, 时长: {duration:.1f}s, CPU核心: {cpu_cores}")

        frame_pattern = os.path.join(self.frame_dir, f"{safe_name}_kf_*.jpg")
        existing_frames = sorted([
            f for f in glob.glob(frame_pattern)
            if os.path.exists(f)
        ])

        if existing_frames and not force:
            print(f"[LOAD] 找到 {len(existing_frames)} 个已存在关键帧，跳过抽帧")
            keyframes = []
            for frame_path in existing_frames:
                try:
                    ts_str = os.path.basename(frame_path).split('_kf_')[1].replace('.jpg', '')
                    timestamp = float(ts_str)
                    start_time, end_time = self._calculate_time_range(timestamp, duration)
                    keyframes.append((frame_path, timestamp, start_time, end_time, video_info))
                except:
                    continue
            return keyframes

        timestamps_to_extract = []
        t = 0.0
        while t < duration and len(timestamps_to_extract) < self.max_frames_per_video:
            timestamps_to_extract.append(t)
            t += self.sample_interval

        def extract_single(ts):
            temp_path = os.path.join(self.frame_dir, f"{safe_name}_temp_{int(ts * 1000)}.jpg")
            frame = self._extract_frame_safe(abs_video_path, ts, temp_path)
            return (ts, frame, temp_path)

        key_frames = []
        prev_frame = None
        prev_gray = None

        with ThreadPoolExecutor(max_workers=cpu_cores) as executor:
            futures = {executor.submit(extract_single, ts): ts for ts in timestamps_to_extract}
            results = []
            for future in as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda x: x[0])

        for ts, current_frame, temp_path in results:
            if current_frame is not None:
                current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)

                should_save = False

                if prev_gray is None:
                    should_save = True
                else:
                    diff = self._calculate_scene_diff(prev_frame, current_frame)
                    if diff >= self.diff_threshold:
                        should_save = True
                        print(f"   场景切换 @ {ts:.1f}s (差异: {diff:.3f})")

                if should_save:
                    final_path = os.path.join(self.frame_dir, f"{safe_name}_kf_{int(ts)}.jpg")

                    if temp_path != final_path:
                        try:
                            if os.path.exists(final_path):
                                os.remove(final_path)
                            os.rename(temp_path, final_path)
                        except Exception as e:
                            print(f"[WARN] 文件重命名失败: {e}")
                            final_path = temp_path

                    start_time, end_time = self._calculate_time_range(ts, duration)
                    key_frames.append((final_path, ts, start_time, end_time, video_info))

                else:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                    except:
                        pass

                prev_frame = current_frame
                prev_gray = current_gray

        print(f"[STAT] 关键帧提取完成: {len(key_frames)} 个")
        return key_frames

    def process_video(self, video_path: str, force_reprocess: bool = False) -> List[dict]:
        abs_video_path = self._normalize_path(video_path)
        video_info = self._get_video_info(abs_video_path)

        keyframes = self.extract_keyframes(abs_video_path, force=force_reprocess)

        if not keyframes:
            print(f"[WARN] 未提取到关键帧: {abs_video_path}")
            return []

        frame_paths = [kf[0] for kf in keyframes]
        print(f"[AI] 开始并行描述 {len(frame_paths)} 个关键帧...")

        descriptions = self.ollama_service.describe_frames_parallel(
            frame_paths,
            max_workers=2
        )

        results = []
        for i, (frame_path, timestamp, start_time, end_time, info) in enumerate(keyframes):
            desc = descriptions[i] if i < len(descriptions) else self.ollama_service._empty_description()

            full_desc = desc.get("full_description", "")
            if not full_desc:
                parts = [
                    desc.get("shot_size", ""),
                    desc.get("camera_movement", ""),
                    desc.get("lighting", ""),
                    desc.get("action", "")
                ]
                full_desc = " ".join([p for p in parts if p])

            results.append({
                "frame_path": frame_path,
                "video_path": abs_video_path,
                "timestamp": timestamp,
                "start_time": start_time,
                "end_time": end_time,
                "description": full_desc,
                "shot_size": desc.get("shot_size", ""),
                "camera_movement": desc.get("camera_movement", ""),
                "lighting": desc.get("lighting", ""),
                "composition": desc.get("composition", ""),
                "action": desc.get("action", ""),
                "video_resolution": info.get("resolution", ""),
                "video_duration": info.get("duration", 0)
            })

        return results


import glob
