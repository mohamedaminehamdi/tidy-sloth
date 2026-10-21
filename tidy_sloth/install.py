"""Set up Tidy Sloth on this Mac: the two models, a real app in ~/Applications and, if you want it, a plan every night.

install.sh runs `tidy-sloth --setup`. Nothing here needs an admin password, and nothing touches your files.
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

from . import rename

APP = Path.home() / "Applications" / "Tidy Sloth.app"
BUNDLE_ID = "io.github.mohamedaminehamdi.tidysloth"
AGENT = Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.overnight.plist"
ICON = Path(__file__).parent / "sloth.icns"
WHY = "Tidy Sloth looks at your files to suggest where they belong. Nothing moves until you approve."

# Opening the app starts the review screen in the background; the nightly run waits until the plan is built.
APPLET = """set mode to system attribute "SLOTH_MODE"
if mode is "overnight" then
\tdo shell script quoted form of "{exe}" & " --overnight > /dev/null 2>&1"
else
\tdo shell script quoted form of "{exe}" & " > /dev/null 2>&1 &"
end if
"""


def ollama_up(seconds=60):
    for _ in range(seconds):
        try:
            requests.get(f"{rename.OLLAMA}/api/version", timeout=2).raise_for_status()
            return True
        except requests.RequestException:
            time.sleep(1)
    return False


def pull_gemma():
    print(f"Downloading {rename.MODEL} for naming files (about 6.6 GB, only once)…")
    with requests.post(f"{rename.OLLAMA}/api/pull", json={"model": rename.MODEL}, stream=True, timeout=(10, None)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            msg = json.loads(line) if line else {}
            if "error" in msg:  # Ollama reports failures inside a 200 stream
                raise RuntimeError(msg["error"])
            if msg.get("total"):
                print(f"\r  {msg.get('status', '')[:30]:<30} {100 * msg.get('completed', 0) // msg['total']:3d}%", end="", flush=True)
    print("\r  Gemma 4 is ready." + " " * 40)


def warm_tabpfn():
    """Downloads the open TabPFN v2 weights (~70 MB) by fitting a tiny made-up table. None of your files are read."""
    os.environ.setdefault("TABPFN_DISABLE_TELEMETRY", "1")
    import numpy as np
    from tabpfn import TabPFNClassifier
    from tabpfn.constants import ModelVersion

    print("Downloading TabPFN, the model that learns your folders…")
    X, y = np.arange(20, dtype=float).reshape(10, 2), np.array([0, 1] * 5)
    TabPFNClassifier.create_default_for_version(ModelVersion.V2).fit(X, y).predict(X)
    print("  TabPFN is ready.")


def _ours(app):
    try:
        return plistlib.loads((app / "Contents" / "Info.plist").read_bytes()).get("CFBundleIdentifier") == BUNDLE_ID
    except OSError:
        return False


def make_app(exe, app=APP):
    """A double-clickable Tidy Sloth.app. Built on this Mac (not downloaded), so Gatekeeper has nothing to block."""
    if app.exists():
        if not _ours(app):
            raise SystemExit(f"{app} exists and isn't ours; leaving it alone.")
        shutil.rmtree(app)
    app.parent.mkdir(parents=True, exist_ok=True)
    exe = str(exe).replace("\\", "\\\\").replace('"', '\\"')
    with tempfile.NamedTemporaryFile("w", suffix=".applescript", delete=False) as f:
        f.write(APPLET.format(exe=exe))
    subprocess.run(["osacompile", "-o", str(app), f.name], check=True, capture_output=True)
    os.unlink(f.name)

    res = app / "Contents" / "Resources"
    shutil.copy(ICON, res / "applet.icns")
    (res / "Assets.car").unlink(missing_ok=True)  # it would override our icon
    info_path = app / "Contents" / "Info.plist"
    info = plistlib.loads(info_path.read_bytes())
    info.pop("CFBundleIconName", None)
    info.update(CFBundleIdentifier=BUNDLE_ID, CFBundleName="Tidy Sloth", CFBundleDisplayName="Tidy Sloth",
                NSDesktopFolderUsageDescription=WHY, NSDocumentsFolderUsageDescription=WHY, NSDownloadsFolderUsageDescription=WHY)
    info_path.write_bytes(plistlib.dumps(info))
    # Editing the bundle breaks osacompile's ad-hoc signature; macOS ties folder permissions to a valid one.
    subprocess.run(["codesign", "--force", "--deep", "-s", "-", str(app)], check=True, capture_output=True)
    subprocess.run(["touch", str(app)])  # nudge Finder to show the new icon
    return app


def _launchctl(*args):
    return subprocess.run(["launchctl", *args], capture_output=True)


def enable_overnight(app=APP):
    """At 3 am, open the app in overnight mode: it builds a plan and quits. It never moves anything on its own."""
    AGENT.parent.mkdir(parents=True, exist_ok=True)
    AGENT.write_bytes(plistlib.dumps({
        "Label": f"{BUNDLE_ID}.overnight",
        "ProgramArguments": ["/usr/bin/open", "-g", "--env", "SLOTH_MODE=overnight", "-a", str(app)],
        "StartCalendarInterval": {"Hour": 3, "Minute": 0},
    }))
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(AGENT))
    if _launchctl("bootstrap", domain, str(AGENT)).returncode:
        print("  Couldn't schedule the nightly plan; you can still open Tidy Sloth any time.")
    else:
        print("  A fresh plan will be waiting every morning (built at 3 am, or when your Mac next wakes).")


def setup(models=True, overnight=False):
    exe = Path(sys.argv[0]).absolute() if Path(sys.argv[0]).name == "tidy-sloth" else shutil.which("tidy-sloth")
    if not exe:
        raise SystemExit("Can't find the tidy-sloth command to point the app at.")
    if models:
        if ollama_up():
            pull_gemma()
        else:
            print("Ollama isn't running, so no Gemma 4 for now. Tidy Sloth still sorts; it just won't rename files.")
        warm_tabpfn()
    app = make_app(exe)
    print(f"Made {app.name} in your Applications folder.")
    if overnight:
        enable_overnight(app)


def uninstall():
    if AGENT.exists():
        _launchctl("bootout", f"gui/{os.getuid()}", str(AGENT))
        AGENT.unlink()
    if _ours(APP):
        shutil.rmtree(APP)
    print("Removed the Tidy Sloth app and the nightly run. Your files, and the undo journals in ~/.tidy-sloth, are untouched.")
    print("To remove the program too:  uv tool uninstall tidy-sloth")
