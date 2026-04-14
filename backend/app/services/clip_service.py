import torch
from PIL import Image
import base64
import io
import os
import tempfile

# 暂时禁用CLIP，使用m3e-base
class CLIPService:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        print(f"[CLIP] 暂时禁用，使用m3e-base回退方案")
        print(f"[CLIP] 原因: Windows缓存权限问题")
        self.available = False

    def encode_image(self, image_path: str) -> list:
        return None

    def encode_text(self, text: str) -> list:
        return None

    def image_to_image_similarity(self, image1_path: str, image2_path: str) -> float:
        return 0.0


clip_service = None

def get_clip_service() -> CLIPService:
    global clip_service
    if clip_service is None:
        clip_service = CLIPService()
    return clip_service
