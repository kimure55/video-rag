from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from typing import Optional, Callable, List
import threading
import time
import os


class VideoFileHandler(FileSystemEventHandler):
    def __init__(self, extensions: set = None):
        super().__init__()
        self.extensions = extensions or {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"}
        self.pending_videos: List[str] = []
        self._lock = threading.Lock()

    def is_video_file(self, path: str) -> bool:
        ext = os.path.splitext(path.lower())[1]
        return ext in self.extensions

    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self.is_video_file(event.src_path):
            with self._lock:
                if event.src_path not in self.pending_videos:
                    self.pending_videos.append(event.src_path)
                    print(f"[VIDEO] 检测到新视频: {event.src_path}")


class WatchdogService:
    def __init__(
        self,
        folder_path: str,
        chroma_service,
        video_processor,
        status_callback: Optional[Callable] = None
    ):
        self.watch_path = folder_path
        self.chroma_service = chroma_service
        self.video_processor = video_processor
        self.status_callback = status_callback
        self.observer: Optional[Observer] = None
        self.event_handler = VideoFileHandler()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            print("[WARN] Watchdog 已经在运行")
            return

        self._running = True
        self.observer = Observer()
        self.observer.schedule(self.event_handler, self.watch_path, recursive=False)
        self.observer.start()

        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

        print(f"[WATCH] Watchdog 已启动，监视: {self.watch_path}")

    def stop(self):
        self._running = False
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        print("[WATCH] Watchdog 已停止")

    def is_running(self) -> bool:
        return self._running and self.observer is not None and self.observer.is_alive()

    def _process_loop(self):
        while self._running:
            try:
                with self.event_handler._lock:
                    pending = self.event_handler.pending_videos.copy()
                    self.event_handler.pending_videos.clear()

                for video_path in pending:
                    if not self._running:
                        break

                    if not os.path.exists(video_path):
                        continue

                    if self.chroma_service.is_video_processed(video_path):
                        print(f"[SKIP] 跳过已处理: {video_path}")
                        continue

                    video_name = os.path.basename(video_path)
                    if self.status_callback:
                        self.status_callback(f"自动处理: {video_name}")

                    print(f"[AI] 自动处理新视频: {video_name}")

                    try:
                        results = self.video_processor.process_video(video_path)
                        if results:
                            self.chroma_service.add_frames_batch(results)
                            self.chroma_service.mark_video_processed(video_path)
                            print(f"[OK] 自动处理完成: {video_name} ({len(results)} 帧)")
                            if self.status_callback:
                                self.status_callback(f"处理完成: {video_name}")
                    except Exception as e:
                        print(f"[ERROR] 自动处理失败 {video_name}: {e}")
                        if self.status_callback:
                            self.status_callback(f"处理失败: {video_name}")

            except Exception as e:
                print(f"[WARN] Watchdog 处理循环异常: {e}")

            time.sleep(2)

    @property
    def pending_videos(self) -> List[str]:
        with self.event_handler._lock:
            return self.event_handler.pending_videos.copy()
