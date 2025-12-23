from pathlib import Path
import os
from dotenv import load_dotenv

# 优先加载同目录 .env
env_path = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=str(env_path) if env_path.exists() else None)

def mask(v: str | None) -> str:
    if not v:
        return "<not set>"
    return (v[:3] + "***" + v[-4:]) if len(v) >= 8 else "<set>"

print("--- Embedding env ---")
print("EMBED_MODEL_TYPE:", os.getenv("EMBED_MODEL_TYPE"))
print("EMBED_MODEL_NAME:", os.getenv("EMBED_MODEL_NAME") or "<default>")
print("EMBED_API_KEY:", mask(os.getenv("EMBED_API_KEY")))
print("EMBED_BASE_URL:", os.getenv("EMBED_BASE_URL") or "<sdk-mode>")
print("----------------------")

from hello_agents.memory.embedding import refresh_embedder

embedder = refresh_embedder()
print("Embedder class:", type(embedder).__name__)
print("Embedder dimension:", getattr(embedder, "dimension", None))

vec = embedder.encode("hello world")
try:
    import numpy as np
    arr = np.array(vec)
    print("Vector shape:", arr.shape)
    print("Vector head:", arr.flatten()[:6])
except Exception:
    # 非 numpy 情况
    if isinstance(vec, (list, tuple)):
        print("Vector length:", len(vec))
        print("Vector head:", vec[:6])
    else:
        print("Vector scalar value:", vec)

print("OK: embedding configuration works")
