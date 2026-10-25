"""Picks pictures from the teacher's uploaded files for slides, by CONTENT (not by page guesses).

How it works
- Every extracted picture gets the text of the page it sits on (from the "[Page N]" markers in the material text).
- Each slide is compared with that text using IDF-weighted keyword overlap on title + key idea + visual description.
- Best (slide, picture) pairs are assigned first; each picture is used once.
- A slide with no convincing match gets NO picture (the slide layout then shows its example or key word instead).
"""
import math
import os
import re

STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were", "has", "have", "had", "its", "their",
    "into", "which", "what", "when", "where", "how", "why", "can", "will", "not", "but", "all", "any", "each",
    "than", "then", "there", "these", "those", "they", "them", "about", "also", "other", "such", "more", "most",
    "some", "one", "two", "use", "used", "using", "diagram", "picture", "image", "figure", "shows", "show",
}


def _tokens(text: str) -> list:
    out = []
    for w in re.findall(r"[a-z0-9\u0900-\u097F]+", (text or "").lower()):
        if len(w) < 3 or w in STOP:
            continue
        if w.endswith("s") and len(w) > 4 and not w.endswith("ss"):
            w = w[:-1]  # light plural stemming
        out.append(w)
    return out


def _page_texts(material_text: str) -> dict:
    parts = re.split(r"\[Page (\d+)\]", material_text or "")
    pages = {}
    for i in range(1, len(parts) - 1, 2):
        pages[int(parts[i])] = pages.get(int(parts[i]), "") + " " + parts[i + 1]
    return pages


def _image_path(im: dict):
    return im.get("path") or im.get("image_path") or im.get("file")


def assign_images(slides: list, images: list, material_text: str = "", min_score: float = 0.30, min_shared: int = 2) -> int:
    """Sets slide['image_path'] and slide['image_page'] where a picture really matches. Returns how many matched."""
    if not slides or not images:
        return 0
    pages = _page_texts(material_text)

    pics = []
    for im in images:
        path = _image_path(im)
        if not path or not os.path.exists(path):
            continue
        w, h = im.get("width"), im.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and (w < 100 or h < 100):
            continue  # logos, bullets and rules
        context = im.get("context") or im.get("caption") or pages.get(im.get("page"), "")
        toks = set(_tokens(context))
        if toks:
            pics.append({"path": path, "page": im.get("page"), "toks": toks})
    if not pics:
        return 0

    n = len(pics)
    df = {}
    for p in pics:
        for t in p["toks"]:
            df[t] = df.get(t, 0) + 1
    idf = lambda t: math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    pairs = []
    for si, s in enumerate(slides):
        weights = {}
        for text, weight in ((s.get("title"), 2.0), (s.get("visual_desc"), 2.0), (s.get("key_idea"), 1.0)):
            for t in _tokens(text or ""):
                weights[t] = max(weights.get(t, 0), weight)
        for t in [x["term"] for x in (s.get("key_terms") or []) if isinstance(x, dict) and x.get("term")]:
            for tok in _tokens(t):
                weights[tok] = max(weights.get(tok, 0), 1.5)
        total = sum(w * idf(t) for t, w in weights.items())
        if not total:
            continue
        for pi, p in enumerate(pics):
            shared = [t for t in weights if t in p["toks"]]
            if len(shared) < min_shared:
                continue
            score = sum(weights[t] * idf(t) for t in shared) / total
            if score >= min_score:
                pairs.append((score, si, pi))

    pairs.sort(reverse=True)
    used_slides, used_pics, matched = set(), set(), 0
    for score, si, pi in pairs:
        if si in used_slides or pi in used_pics:
            continue
        used_slides.add(si)
        used_pics.add(pi)
        slides[si]["image_path"] = pics[pi]["path"]
        if pics[pi]["page"]:
            slides[si]["image_page"] = pics[pi]["page"]
        matched += 1
    return matched
