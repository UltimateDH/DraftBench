"""Pull pictures out of uploaded PDFs, Word files and PowerPoint files,
together with the text that sits around each picture (used to match pictures to slides)."""
import hashlib
import io
import os
from typing import Dict, List, Optional

MIN_SIDE_PX = 140      # ignore icons, bullets and tiny decorations
MAX_SIDE_PX = 1400     # keep slide files small
MAX_IMAGES = 40
MAX_ASPECT = 4.0       # ignore thin rules and banners
RENDER_DPI = 150


def _save(pil, out_dir: str, name: str) -> Optional[Dict]:
    """Flatten onto white, size-check and save as PNG. Returns {path, hash} or None."""
    from PIL import Image
    try:
        im = pil.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im).convert("RGB")
    except Exception:
        return None
    w, h = im.size
    if min(w, h) < MIN_SIDE_PX or max(w, h) / max(min(w, h), 1) > MAX_ASPECT:
        return None
    if max(w, h) > MAX_SIDE_PX:
        im.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    digest = hashlib.md5(buf.getvalue()).hexdigest()
    path = os.path.join(out_dir, f"{name}.png")
    with open(path, "wb") as f:
        f.write(buf.getvalue())
    return {"path": path, "hash": digest}


def _from_pdf(path: str, out_dir: str, tag: str, max_page: int) -> List[Dict]:
    import pdfplumber
    found = []
    scale = RENDER_DPI / 72.0
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            if pno > max_page:
                break
            area = float(page.width * page.height)
            full, text = None, None
            for k, im in enumerate(page.images):
                x0, x1 = max(im["x0"], 0), min(im["x1"], page.width)
                top, bottom = max(im["top"], 0), min(im["bottom"], page.height)
                w, h = x1 - x0, bottom - top
                if w < 50 or h < 50 or (w * h) / area > 0.85:  # skip tiny pieces and full-page scans
                    continue
                try:
                    if full is None:
                        full = page.to_image(resolution=RENDER_DPI).original
                    crop = full.crop((int(x0 * scale), int(top * scale), int(x1 * scale), int(bottom * scale)))
                except Exception:
                    continue
                saved = _save(crop, out_dir, f"{tag}_p{pno}_{k}")
                if not saved:
                    continue
                if text is None:
                    text = (page.extract_text() or "")[:1500]
                found.append({**saved, "page": pno, "context": text})
    return found


def _from_docx(path: str, out_dir: str, tag: str) -> List[Dict]:
    import docx
    from PIL import Image
    d = docx.Document(path)
    paras = d.paragraphs
    found = []
    for i, para in enumerate(paras):
        for k, rid in enumerate(para._element.xpath(".//a:blip/@r:embed")):
            try:
                blob = d.part.related_parts[rid].blob
                pil = Image.open(io.BytesIO(blob))
                pil.load()
            except Exception:
                continue  # unsupported formats such as EMF/WMF
            saved = _save(pil, out_dir, f"{tag}_d{i}_{k}")
            if saved:
                near = " ".join(p.text for p in paras[max(0, i - 2): i + 3])[:1500]
                found.append({**saved, "page": None, "context": near})
    return found


def _from_pptx(path: str, out_dir: str, tag: str) -> List[Dict]:
    from pptx import Presentation
    from PIL import Image
    found = []
    for sno, slide in enumerate(Presentation(path).slides, 1):
        text = " ".join(
            sh.text_frame.text for sh in slide.shapes if sh.has_text_frame
        )[:1500]
        for k, sh in enumerate(slide.shapes):
            if sh.shape_type != 13:  # 13 = picture
                continue
            try:
                pil = Image.open(io.BytesIO(sh.image.blob))
                pil.load()
            except Exception:
                continue
            saved = _save(pil, out_dir, f"{tag}_s{sno}_{k}")
            if saved:
                found.append({**saved, "page": sno, "context": text})
    return found


def extract_images(path: str, ext: str, out_dir: str, tag: str, max_page: int = 40) -> List[Dict]:
    """Return [{path, page, context, hash}] for the useful pictures in a file. Never raises."""
    os.makedirs(out_dir, exist_ok=True)
    try:
        if ext == ".pdf":
            found = _from_pdf(path, out_dir, tag, max_page)
        elif ext == ".docx":
            found = _from_docx(path, out_dir, tag)
        elif ext == ".pptx":
            found = _from_pptx(path, out_dir, tag)
        else:
            return []
    except Exception as e:
        print(f"[media_extractor] could not read pictures from {os.path.basename(path)}: {e}")
        return []

    # Pictures that repeat on 3+ pages are logos or headers: drop them
    counts = {}
    for f in found:
        counts[f["hash"]] = counts.get(f["hash"], 0) + 1
    kept, seen = [], set()
    for f in found:
        if counts[f["hash"]] >= 3 or f["hash"] in seen:
            continue
        seen.add(f["hash"])
        kept.append(f)
    return kept[:MAX_IMAGES]
