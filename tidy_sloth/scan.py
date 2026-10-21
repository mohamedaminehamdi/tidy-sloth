"""Find what to learn from (files you already filed) and what to tidy (loose files), safely.

Read-only. Never descends into code projects, never touches hidden files, and flags secrets instead of planning them.
Metadata comes from macOS Spotlight (`mdls`): download source, capture date and photo GPS, no extra dependencies.
"""
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

HOME = Path.home()
TIDY_ROOTS = [HOME / "Downloads", HOME / "Desktop"]
FILING_ROOTS = [HOME / "Desktop", HOME / "Documents", HOME / "Pictures"]

CODE_MARKERS = {".git", "package.json", "pyproject.toml", "requirements.txt", "setup.py", "go.mod", "Cargo.toml",
                "pom.xml", "build.gradle", "composer.json", "Gemfile", "node_modules", "Makefile", "Dockerfile"}
CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".php", ".c", ".cpp", ".h",
            ".cs", ".swift", ".yaml", ".yml", ".toml", ".lock", ".sh", ".mjs", ".cjs", ".vue", ".scss", ".css", ".map"}
SENSITIVE_EXT = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".keychain", ".ovpn", ".gpg", ".asc", ".jks", ".keystore"}
SENSITIVE_NAME = re.compile(r"^(id_(rsa|dsa|ecdsa|ed25519)|\.env)|wallet|secret|password|passwd|credential|recovery[-_ ]?code|seed[-_ ]?phrase", re.I)
RECENT_SECONDS = 10 * 60
# `mdls -raw` prints attributes in alphabetical order, whatever order they are requested in.
MDLS_ATTRS = sorted(["kMDItemWhereFroms", "kMDItemContentCreationDate", "kMDItemLatitude", "kMDItemLongitude"])


def is_sensitive(path):
    p = Path(path)
    return p.suffix.lower() in SENSITIVE_EXT or bool(SENSITIVE_NAME.search(p.name))


def is_code_project(folder, sample=400):
    """A folder is code if it has a project marker near the top, or mostly code files."""
    folder = Path(folder)
    try:
        children = [c for c in folder.iterdir() if c.is_dir() and not c.name.startswith(".")][:30]
    except OSError:  # macOS-protected (e.g. Photo Booth Library): not ours to touch
        return True
    for d in [folder, *children]:
        try:
            if CODE_MARKERS & {c.name for c in d.iterdir()}:
                return True
        except OSError:
            continue
    exts = [Path(f).suffix.lower() for f in walk_files(folder, limit=sample)]
    return bool(exts) and sum(e in CODE_EXT for e in exts) / len(exts) > 0.5


def walk_files(folder, limit=None):
    """Visible regular files under folder (no hidden dirs, no node_modules), up to limit."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "node_modules" and not d.endswith(".app")]
        for f in filenames:
            if not f.startswith("."):
                out.append(os.path.join(dirpath, f))
                if limit and len(out) >= limit:
                    return out
    return out


def filing_folders(roots=FILING_ROOTS, skip=()):
    """Top-level folders that look like a person's filing (not code, not empty, not ours)."""
    found = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for d in entries:
            if (d.is_dir() and not d.name.startswith(".") and not d.name.endswith(".app")
                    and d.resolve() not in {Path(s).resolve() for s in skip} and not is_code_project(d)):
                if walk_files(d, limit=1):
                    found.append(d)
    return found


def check_access(roots=(*TIDY_ROOTS, *FILING_ROOTS)):
    """macOS asks the first time an app looks in Desktop, Documents or Downloads. A 'no' must not become an empty plan."""
    denied = []
    for root in dict.fromkeys(roots):
        try:
            os.listdir(root)
        except FileNotFoundError:
            pass
        except PermissionError:
            denied.append(root.name)
    if denied:
        raise PermissionError(f"macOS hasn't let Tidy Sloth look in {' and '.join(denied)}. Allow it in System Settings → "
                              "Privacy & Security → Files & Folders, then open Tidy Sloth again.")


def loose_files(roots=TIDY_ROOTS, now=None):
    """Top-level files to tidy, plus the ones we deliberately leave alone (with the reason)."""
    now, todo, skipped = now or time.time(), [], []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.name.startswith(".") or not p.is_file():
                continue
            if is_sensitive(p):
                skipped.append((str(p), "looks like a key or secret, never touched"))
            elif now - p.stat().st_mtime < RECENT_SECONDS:
                skipped.append((str(p), "changed in the last 10 minutes, maybe still in use"))
            else:
                todo.append(str(p))
    return todo, skipped


def _domain(raw):
    m = re.search(r'"(https?://[^"]+)"', raw or "")
    host = urlparse(m.group(1)).hostname if m else ""
    return host.removeprefix("www.") if host else ""


def _float(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("nan")


def _date(raw):
    try:  # "2024-05-12 14:03:22 +0000"
        return time.mktime(time.strptime(raw[:19], "%Y-%m-%d %H:%M:%S")) / 86400
    except (TypeError, ValueError):
        return float("nan")


def metadata(paths, batch=200):
    """Spotlight metadata for many files at once: {path: {source, created_days, lat, lon, size, mtime_days}}."""
    out = {}
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        cmd = ["mdls", "-raw", "-nullMarker", "", *sum((["-name", a] for a in MDLS_ATTRS), [])] + chunk
        try:
            values = subprocess.run(cmd, capture_output=True, timeout=120).stdout.decode("utf-8", "replace").split("\0")
        except (OSError, subprocess.TimeoutExpired):
            values = []
        for j, path in enumerate(chunk):
            row = values[j * len(MDLS_ATTRS):(j + 1) * len(MDLS_ATTRS)]
            v = dict(zip(MDLS_ATTRS, row)) if len(row) == len(MDLS_ATTRS) else {}
            try:
                st = os.stat(path)
                size, mtime = st.st_size, st.st_mtime / 86400
            except OSError:
                size, mtime = 0, float("nan")
            created = _date(v.get("kMDItemContentCreationDate"))
            out[path] = {"source": _domain(v.get("kMDItemWhereFroms")), "created_days": created if created == created else mtime,
                         "lat": _float(v.get("kMDItemLatitude")), "lon": _float(v.get("kMDItemLongitude")), "size": size}
    return out
