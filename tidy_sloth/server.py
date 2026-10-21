"""The review screen, served only to this machine (127.0.0.1). Approve applies the plan; Undo reverts the last run.

The page opens at once; the plan is built in a background thread while the sloth looks through your files.
"""
import json
import threading
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import plan as planner
from .rename import clean_name

WEB = Path(__file__).parent / "web"
IDLE_SECONDS = 1800  # nobody has looked for 30 minutes: the sloth goes back to sleep


class Handler(SimpleHTTPRequestHandler):
    state = {"plan": None, "step": "Waking up…", "error": None, "building": False, "journal": None}
    lock = threading.Lock()   # one change at a time: apply, undo, rescan
    build = None              # callable(progress) -> plan
    plan_file = None

    def log_message(self, *args):  # keep the terminal calm
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _local(self):
        """Host must be this machine (blocks DNS rebinding); Origin, when sent, must be the review page itself."""
        port = self.server.server_port
        ours = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in ours and (origin is None or origin in {f"http://{h}" for h in ours})

    def do_GET(self):
        if not self._local():
            return self._json({"error": "forbidden"}, 403)
        if self.path == "/api/plan":
            s = self.state
            if s["plan"] is not None:
                return self._json(s["plan"])
            return self._json({"error": s["error"]} if s["error"] else {"building": True, "step": s["step"]})
        return super().do_GET()

    def do_POST(self):
        if not self._local():  # only the review page on this machine may change files
            return self._json({"error": "forbidden"}, 403)
        length = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not self.lock.acquire(blocking=False):
            return self._json({"error": "busy"}, 409)
        try:
            if self.path == "/api/apply":
                return self._apply(body)
            if self.path == "/api/undo":
                return self._undo()
            if self.path == "/api/rescan":
                if self.state["building"]:
                    return self._json({"error": "already looking"}, 409)
                start_build(self.build)
                return self._json({"building": True})
            return self._json({"error": "not found"}, 404)
        finally:
            self.lock.release()

    def _apply(self, body):
        plan = self.state["plan"]
        if plan is None or plan.get("applied") or body.get("token") != plan.get("token"):
            return self._json({"error": "This plan is out of date. Look again."}, 409)
        chosen = {i["id"]: i for i in body.get("items", [])}
        for item in plan["items"]:  # the page may edit names and untick items, nothing else
            edit = chosen.get(item["id"])
            if edit and edit.get("new_name") and item["action"] != "leave":
                item["new_name"] = clean_name(Path(edit["new_name"]).stem) + Path(item["path"]).suffix.lower()
        journal = planner.apply(plan, ids=set(chosen))
        if journal is None:
            return self._json({"error": "Nothing left to move."}, 409)
        plan["applied"] = journal.name
        self.state["journal"] = journal
        if self.plan_file:
            planner.save(plan, self.plan_file)
        return self._json({"moved": [step["id"] for step in json.loads(journal.read_text())], "journal": journal.name})

    def _undo(self):
        plan = self.state["plan"]
        # Only the tidy this plan made: never fall back to an older journal from another day.
        journal = self.state["journal"] or (planner.JOURNALS / plan["applied"] if plan and plan.get("applied") else None)
        if not journal or not Path(journal).exists():
            return self._json({"restored": 0, "problems": ["Nothing to undo."]})
        restored, problems = planner.undo(journal)
        self.state["journal"] = None
        if self.state["plan"] is not None:
            self.state["plan"].pop("applied", None)
            if self.plan_file:
                planner.save(self.state["plan"], self.plan_file)
        return self._json({"restored": restored, "problems": problems})


def start_build(build):
    state = Handler.state

    def run():
        try:
            result, error = build(progress=lambda step: state.update(step=step)), None
        except PermissionError as exc:
            result, error = None, str(exc)
        except Exception as exc:  # shown on the page instead of a spinner that never ends
            result, error = None, f"Something went wrong while looking ({exc.__class__.__name__}). Nothing was moved."
        state.update(plan=result, error=error, building=False)

    state.update(plan=None, error=None, building=True, step="Waking up…")
    threading.Thread(target=run, daemon=True).start()


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/plan", timeout=3) as r:
            return isinstance(json.load(r), dict)
    except Exception:
        return False


def serve(the_plan, build=None, plan_file=None, port=8765, open_browser=True, idle=IDLE_SECONDS):
    url = f"http://127.0.0.1:{port}/?local=1"
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(WEB)))
    except OSError:
        if already_running(port):  # a second click on the app: show the one that's already open
            print(f"Tidy Sloth is already open at {url}")
            if open_browser:
                webbrowser.open(url)
            return
        raise
    Handler.build, Handler.plan_file = build, plan_file
    Handler.state.update(plan=the_plan, error=None, building=False, journal=None)
    if the_plan is None:
        start_build(build)
    print(f"Review your tidy plan at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()

    stop = threading.Event()
    httpd.timeout = idle
    httpd.handle_timeout = lambda: None if Handler.state["building"] or Handler.lock.locked() else stop.set()
    try:
        while not stop.is_set():
            httpd.handle_request()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
