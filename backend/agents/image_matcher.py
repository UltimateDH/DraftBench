"""Choose the best picture from the teacher's uploaded files for each slide."""
import math
import os
import re
from typing import List, Optional

EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_MIN_SCORE = float(os.getenv("IMAGE_MIN_SCORE", "0.55"))   # cosine similarity needed without a page hint
KEYWORD_MIN_SCORE = 0.12
PICTURE_SLIDES = {"intro", "concept", "example"}                  # review slides stay text-only


def _slide_text(s: dict) -> str:
    parts = [s.get("title"), s.get("key_idea"), " ".join(s.get("bullets") or []), s.get("explanation")]
    return " ".join(p for p in parts if p)[:1200]


def _tokens(text: str) -> set:
    return set(re.findall(r"[\w\u0900-\u097F]{3,}", (text or "").lower()))


def _keyword_scores(slides: List[dict], images: List[dict]) -> List[List[float]]:
    st = [_tokens(_slide_text(s)) for s in slides]
    it = [_tokens(i.get("context", "")) for i in images]
    return [
        [len(a & b) / math.sqrt(len(a) * len(b)) if a and b else 0.0 for b in it]
        for a in st
    ]


def _embedding_scores(slides: List[dict], images: List[dict]) -> Optional[List[List[float]]]:
    try:
        import ollama
        texts = [_slide_text(s) or "slide" for s in slides] + [(i.get("context") or "image")[:800] for i in images]
        vecs = ollama.embed(model=EMBED_MODEL, input=texts)["embeddings"]
    except Exception as e:
        print(f"[image_matcher] embeddings unavailable ({e}); using keyword matching")
        return None

    def cos(u, v):
        nu = math.sqrt(sum(x * x for x in u)) or 1.0
        nv = math.sqrt(sum(x * x for x in v)) or 1.0
        return sum(a * b for a, b in zip(u, v)) / (nu * nv)

    sv, iv = vecs[: len(slides)], vecs[len(slides):]
    return [[cos(a, b) for b in iv] for a in sv]


def assign_images(slides: List[dict], images: List[dict]) -> int:
    """Sets slide['image_path'], slide['image_page'] where a picture fits. Returns how many slides got one."""
    if not slides or not images:
        return 0
    scores = _embedding_scores(slides, images)
    min_score = EMBED_MIN_SCORE
    if scores is None:
        scores, min_score = _keyword_scores(slides, images), KEYWORD_MIN_SCORE

    single_source = len({i.get('material') for i in images}) <= 1
    used, assigned = set(), 0
    for si, s in enumerate(slides):
        if (s.get("slide_type") or "concept") not in PICTURE_SLIDES:
            continue
        free = [j for j in range(len(images)) if j not in used]
        if not free:
            break
        pick = None
        page = s.get("source_page")
        if isinstance(page, int) and single_source:  # the planner said which page this slide is based on: trust that first
            near = [j for j in free if isinstance(images[j].get("page"), int) and abs(images[j]["page"] - page) <= 1]
            if near:
                pick = max(near, key=lambda j: scores[si][j])
        if pick is None:
            best = max(free, key=lambda j: scores[si][j])
            if scores[si][best] >= min_score:
                pick = best
        if pick is not None:
            used.add(pick)
            s["image_path"] = images[pick]["path"]
            s["image_page"] = images[pick].get("page")
            assigned += 1
    return assigned
