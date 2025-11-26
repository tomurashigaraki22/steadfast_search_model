import json
import re
import requests
from io import BytesIO
import numpy as np
from typing import Dict, List
from PIL import Image
from sentence_transformers import SentenceTransformer
from .config import load_config

_model = None

def get_model():
    """
    Lazily loads and returns a CLIP model for both text and image embeddings.
    """
    global _model
    if _model is None:
        cfg = load_config()
        name = cfg.get("MYSQL_URL")  # avoid unused
        model_name = (cfg.get("EMBEDDING_MODEL") or os.environ.get("EMBEDDING_MODEL") or "clip-ViT-B-32")
        _model = SentenceTransformer(model_name)
    return _model

def get_embedding_dim() -> int:
    """
    Returns embedding dimension robustly. Some models may not populate
    get_sentence_embedding_dimension; fall back to encoding a sample.
    """
    model = get_model()
    try:
        dim = model.get_sentence_embedding_dimension()
        if dim:
            return int(dim)
    except Exception:
        pass
    try:
        v = model.encode(["dim_probe"], convert_to_numpy=True, normalize_embeddings=False)[0]
        return int(v.shape[0])
    except Exception:
        pass
    return 512

def _normalize(vec: np.ndarray) -> np.ndarray:
    """
    L2-normalizes a vector for cosine similarity via inner product.
    """
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-12)

def _extract_image_urls(row: Dict) -> List[str]:
    urls = []
    val = row.get("image_urls")
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                urls = [u for u in parsed if isinstance(u, str)]
        except Exception:
            pass
    return urls

_url_re = re.compile(r"^https?://", re.IGNORECASE)

def _is_url(s: str) -> bool:
    return bool(_url_re.match(s or ""))

def _fetch_image(url: str) -> Image.Image:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    img = Image.open(BytesIO(resp.content)).convert("RGB")
    return img

def embed_image(img: Image.Image) -> np.ndarray:
    model = get_model()
    emb = model.encode([img], convert_to_numpy=True, normalize_embeddings=False)[0]
    return _normalize(emb.astype("float32"))

def embed_text(text: str) -> np.ndarray:
    model = get_model()
    emb = model.encode([text], convert_to_numpy=True, normalize_embeddings=False)[0]
    return _normalize(emb.astype("float32"))

def get_embedding_for_product(row: Dict) -> np.ndarray:
    """
    Generates the embedding for a product:
    - If image URLs exist, embed the first image content.
    - Otherwise, embed name + description as text.
    """
    urls = _extract_image_urls(row)
    for u in urls:
        try:
            img = _fetch_image(u)
            return embed_image(img)
        except Exception:
            continue
    name = str(row.get("name") or "")
    desc = str(row.get("description") or "")
    text = (name + " " + desc).strip()
    return embed_text(text)

def get_embedding_for_query(query: str) -> np.ndarray:
    """
    Generates an embedding for a query (image URL or text).
    If the query looks like a URL, treat it as an image and embed the pixels.
    """
    q = query.strip()
    if _is_url(q):
        try:
            img = _fetch_image(q)
            return embed_image(img)
        except Exception:
            pass
    return embed_text(q)
