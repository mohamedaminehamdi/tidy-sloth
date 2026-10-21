"""Plan, apply, undo. Moves and renames only: Tidy Sloth never deletes anything.

Every applied change is written to a journal *before* it happens, so a crash mid-way can still be undone.
"""
import json
import os
import time
from pathlib import Path

from . import rename as gemma
from .features import FAMILIES, FAMILY_OF

JOURNALS = Path.home() / ".tidy-sloth"
THRESHOLD = 0.7          # below this TabPFN confidence a file stays put (or Gemma gets a say, for documents)
SECONDS_SAVED = 20       # assumption shown in the app: a person spends ~20 s finding a home for one file
NEW_FOLDER_MIN = 3       # this many leftovers of one kind (and no home for them) -> suggest a new folder
NEW_FOLDER_NAMES = {"ebook": "Books", "video": "Videos", "image": "Images", "pdf": "PDFs", "text": "Notes", "audio": "Audio",
                    "archive": "Archives", "doc": "Documents", "sheet": "Spreadsheets", "slides": "Slides"}
FAMILY_NAMES = list(FAMILIES)


def free_path(dest):
    """dest, or 'name (2).ext', 'name (3).ext'... if it's taken. Never overwrite."""
    dest = Path(dest)
    if not dest.exists():
        return dest
    for n in range(2, 1000):
        alt = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        if not alt.exists():
            return alt
    raise FileExistsError(dest)


def build(todo, skipped, model, meta, use_gemma=True, threshold=THRESHOLD, progress=print,
          new_folder_root=Path.home() / "Desktop"):
    """The plan the review screen shows. Nothing on disk changes here."""
    predictions = model.predict(todo, meta) if model else [(None, 0.0)] * len(todo)
    folder_names = {Path(c).name: c for c in (model.classes if model else [])}
    items = []
    for i, (path, (folder, conf)) in enumerate(zip(todo, predictions)):
        p, item = Path(path), {"id": i, "path": path, "name": Path(path).name, "folder": None, "folder_name": None,
                               "confidence": round(conf, 3), "by": None, "new_name": None}
        if folder and conf >= threshold:
            item.update(folder=folder, folder_name=Path(folder).name, by="tabpfn")
        elif use_gemma and folder_names and p.suffix.lower() in gemma.DOC_EXT:
            progress(f"asking Gemma where {p.suffix} file {i + 1} goes")
            picked = _safe(gemma.route, path, list(folder_names))
            if picked:
                item.update(folder=folder_names[picked], folder_name=picked, by="gemma")
        if use_gemma and gemma.is_generic(path):
            progress(f"asking Gemma to name file {i + 1}")
            name = _safe(gemma.suggest_name, path)
            if name:
                item["new_name"] = name + p.suffix.lower()
        item["action"] = ("move+rename" if item["folder"] and item["new_name"] else "move" if item["folder"]
                          else "rename" if item["new_name"] else "leave")
        items.append(item)
    suggest_new_folders(items, new_folder_root)
    handled = sum(i["action"] != "leave" for i in items)
    return {"created": time.strftime("%Y-%m-%d %H:%M"), "items": items,
            "skipped": [{"path": p, "name": Path(p).name, "why": why} for p, why in skipped],
            "summary": {"files": len(items), "moves": sum("move" in i["action"] for i in items),
                        "renames": sum("rename" in i["action"] for i in items), "left": len(items) - handled,
                        "minutes_saved": round(handled * SECONDS_SAVED / 60, 1)}}


def suggest_new_folders(items, root):
    """Files none of your folders fit, but that belong together: '4 ebooks -> a new Books folder'. A rule, not AI."""
    groups = {}
    for item in items:
        if item["folder"] is None:
            family = FAMILY_OF.get(Path(item["path"]).suffix.lower())
            if family is not None and FAMILY_NAMES[family] in NEW_FOLDER_NAMES:
                groups.setdefault(FAMILY_NAMES[family], []).append(item)
    for family, group in groups.items():
        if len(group) >= NEW_FOLDER_MIN:
            folder = Path(root) / NEW_FOLDER_NAMES[family]
            for item in group:
                item.update(folder=str(folder), folder_name=folder.name, by="new_folder",
                            action="move+rename" if item["new_name"] else "move")


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # a model hiccup must never break the plan; the file just stays put
        print(f"  (skipped: {exc.__class__.__name__})")
        return None


def apply(plan, ids=None, journal_dir=JOURNALS):
    """Carry out the chosen items. Returns the journal path (needed for undo)."""
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal = journal_dir / f"journal-{time.strftime('%Y%m%d-%H%M%S')}.json"
    done = []
    for item in plan["items"]:
        if item["action"] == "leave" or (ids is not None and item["id"] not in ids):
            continue
        src = Path(item["path"])
        if not src.is_file():
            continue
        folder = Path(item["folder"]) if item["folder"] else src.parent
        dest = free_path(folder / (item["new_name"] or src.name))
        done.append({"from": str(src), "to": str(dest)})
        journal.write_text(json.dumps(done, indent=1))  # written before the move: undo works even after a crash
        folder.mkdir(parents=True, exist_ok=True)
        os.rename(src, dest)
    journal.write_text(json.dumps(done, indent=1))
    return journal


def undo(journal):
    """Put everything back where it was. Returns (restored, problems)."""
    restored, problems = 0, []
    for step in reversed(json.loads(Path(journal).read_text())):
        src, back = Path(step["to"]), Path(step["from"])
        if not src.exists():
            problems.append(f"{src.name} is no longer where Tidy Sloth put it")
        elif back.exists():
            problems.append(f"something new is at {back.name}'s old place; left it in {src.parent.name}")
        else:
            back.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, back)
            restored += 1
    return restored, problems


def latest_journal(journal_dir=JOURNALS):
    journals = sorted(journal_dir.glob("journal-*.json"))
    return journals[-1] if journals else None
