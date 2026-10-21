"""Gemma 4, running locally through Ollama, reads junk-named files and documents TabPFN isn't sure about.

Nothing leaves the machine: images are shrunk with macOS `sips`, PDF text is read with pypdf, and both go to
the local model. Only generic names are renamed; a name you chose yourself is never touched.
"""
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import requests

OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL = os.getenv("SLOTH_MODEL", "gemma4:e4b")
GENERIC = re.compile(
    r"^(img|dsc|dscn|dcim|pxl|photo|image|pic|screenshot|screen ?shot|capture|scan|scanned|document|doc|untitled|"
    r"file|download|unnamed|copy of|new document|whatsapp image|whatsapp video)?[\s_\-]*[\d\s_\-.:()at]*$"
    r"|^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$|^[0-9a-f_\-]{16,}$",
    re.I,
)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tiff", ".bmp"}
DOC_EXT = {".pdf", ".txt", ".md", ".rtf", ".csv", ".json", ".html"}
_NAME = {"type": "object", "properties": {"name": {"type": "string"}, "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
         "required": ["name", "confidence"]}


def is_generic(path):
    """True for names a person didn't really choose: IMG_4821, Screenshot 2026-10-21 at 14.03.22, document (3)."""
    stem = Path(path).stem.strip()
    return bool(stem) and bool(GENERIC.match(stem))


def _jpeg(path, size=768):
    out = Path(tempfile.mkdtemp()) / "preview.jpg"
    subprocess.run(["sips", "-s", "format", "jpeg", "-Z", str(size), str(path), "--out", str(out)],
                   capture_output=True, timeout=60, check=True)
    return out.read_bytes()


def _text(path, limit=1500):
    if Path(path).suffix.lower() == ".pdf":
        from pypdf import PdfReader
        try:
            reader = PdfReader(path)
            return " ".join((reader.pages[i].extract_text() or "") for i in range(min(2, len(reader.pages))))[:limit].strip()
        except Exception:
            return ""
    try:
        return Path(path).read_text(errors="replace")[:limit].strip()
    except OSError:
        return ""


def _ask(prompt, schema, image=None, text=""):
    message = {"role": "user", "content": f"{prompt}\n\n{text}".strip()}
    if image:
        message["images"] = [base64.b64encode(image).decode()]
    r = requests.post(f"{OLLAMA}/api/chat", timeout=300, json={
        "model": MODEL, "stream": False, "think": False, "format": schema, "options": {"temperature": 0.1},
        "messages": [message]})
    r.raise_for_status()
    return json.loads(r.json()["message"]["content"])


def _evidence(path):
    """What Gemma gets to look at: a small JPEG for images and scans, the first page of text for documents."""
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return _jpeg(path), ""
    if ext in DOC_EXT:
        text = _text(path)
        if text:
            return None, f"Document text (start):\n{text}"
        if ext == ".pdf":  # scanned PDF: look at page one
            return _jpeg(path), ""
    return None, ""


def clean_name(name, max_len=80):
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", name).strip(" .")
    return re.sub(r"\s+", " ", name)[:max_len].strip()


def suggest_name(path):
    """A descriptive filename (without extension), or None if Gemma can't tell."""
    image, text = _evidence(path)
    if image is None and not text:
        return None
    answer = _ask(
        "Suggest a short descriptive filename for this file: 3 to 8 words, like '2026-10 Electricity bill EDF' or "
        "'Lisbon tram at sunset'. Put a date first only if one is clearly shown. Never include account numbers, "
        "card numbers, passwords or ID numbers. No file extension. Confidence low if you can't tell what it is.",
        _NAME, image=image, text=text)
    name = clean_name(answer.get("name", ""))
    return name if name and answer.get("confidence") != "low" else None


def route(path, folder_names):
    """For documents TabPFN isn't sure about: which of YOUR folders fits, or None."""
    image, text = _evidence(path)
    if image is None and not text:
        return None
    schema = {"type": "object", "properties": {"folder": {"type": "string", "enum": [*folder_names, "none"]},
                                               "confidence": {"type": "string", "enum": ["high", "medium", "low"]}},
              "required": ["folder", "confidence"]}
    answer = _ask("Which one of these folders does this file belong in? Answer 'none' unless one clearly fits.\n"
                  f"Folders: {', '.join(folder_names)}", schema, image=image, text=text)
    folder = answer.get("folder")
    return folder if folder in folder_names and answer.get("confidence") == "high" else None
