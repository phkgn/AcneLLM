from huggingface_hub import HfApi

api = HfApi()

# ⚠️ Đổi "your-username" thành username Hugging Face của bạn
HF_USERNAME = "khangph05"
REPO_NAME = "AcneLLM-v2-Q4"
REPO_ID = f"{HF_USERNAME}/{REPO_NAME}"

GGUF_PATH = r"E:\project\AcneLLM\model\V2\Q4\Qwen2.5-7B-Instruct.Q4_K_M.gguf"

# Tạo repo trên HF Hub
print(f"Đang tạo repo: {REPO_ID} ...")
api.create_repo(
    repo_id=REPO_ID,
    repo_type="model",
    private=True,
    exist_ok=True  # không báo lỗi nếu repo đã tồn tại
)
print("Tạo repo xong!")

# Upload file GGUF (~4.4GB)
print(f"Đang upload {GGUF_PATH} ...")
print("(File ~4.4GB, có thể mất 10-30 phút tùy mạng)")

api.upload_file(
    path_or_fileobj=GGUF_PATH,
    path_in_repo="Qwen2.5-7B-Instruct.Q4_K_M.gguf",
    repo_id=REPO_ID,
    repo_type="model"
)

print(f"\n✅ Upload xong! Xem tại: https://huggingface.co/{REPO_ID}")
