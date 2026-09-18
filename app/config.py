import os
from dotenv import load_dotenv

load_dotenv(override=True)

raw_keys = os.getenv("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in raw_keys.split(",") if k.strip()]
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
PORT = int(os.getenv("PORT", "8000"))
