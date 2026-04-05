import base64
import requests
import cv2
import numpy as np

# 1. 用 numpy 捏一张纯黑的测试小图 (512x512)
# 这样做直接排除了 FFmpeg 抽帧太大的嫌疑
blank_image = np.zeros((512, 512, 3), np.uint8)

# 2. 压缩成 JPEG 并转为 Base64
encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
_, buffer = cv2.imencode('.jpg', blank_image, encode_param)
# 注意这里的 .decode('utf-8') 极其关键，绝不能带 'b' 前缀或 'data:image/jpeg' 头
base64_str = base64.b64encode(buffer).decode('utf-8')

print(f"✅ 测试图已生成，Base64 长度: {len(base64_str)}")

# 3. 直接呼叫 Ollama
payload = {
    "model": "llava",
    "prompt": "用中文描述这张图片的内容",
    "images": [base64_str],
    "stream": False,
    "options": {"num_ctx": 2048} # 强制限制显存
}

print("🚀 正在呼叫 Ollama，请盯紧你的 4070 Ti Super...")
try:
    response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=30)
    if response.status_code == 200:
        print("🎉 成功！Ollama 回复：", response.json().get("response"))
    else:
        print(f"❌ 翻车！状态码：{response.status_code}，报错信息：{response.text}")
except Exception as e:
    print(f"❌ 彻底连不上：{e}")