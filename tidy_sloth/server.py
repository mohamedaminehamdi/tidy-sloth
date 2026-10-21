"""The review screen, served only to this machine (127.0.0.1). Approve applies the plan; Undo reverts the last run."""
import json
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import plan as planner

WEB = Path(__file__).parent.parent / "web"


class Handler(SimpleHTTPRequestHandler):
    state = {"plan": None, "journal": None}

    def log_message(self, *args):  # keep the terminal calm
        pass

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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
            return self._json(self.state["plan"])
        return super().do_GET()

    def do_POST(self):
        if not self._local():  # only the review page on this machine may change files
            return self._json({"error": "forbidden"}, 403)
        length = min(int(self.headers.get("Content-Length") or 0), 1_000_000)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/apply":
            chosen = {i["id"]: i for i in body.get("items", [])}
            for item in self.state["plan"]["items"]:  # the page may edit names and untick items, nothing else
                edit = chosen.get(item["id"])
                if edit and edit.get("new_name") and item["action"] != "leave":
                    from .rename import clean_name
                    item["new_name"] = clean_name(Path(edit["new_name"]).stem) + Path(item["path"]).suffix.lower()
            journal = planner.apply(self.state["plan"], ids=set(chosen))
            self.state["journal"] = journal
            return self._json({"moved": len(json.loads(journal.read_text())), "journal": journal.name})
        if self.path == "/api/undo":
            journal = self.state["journal"] or planner.latest_journal()
            if not journal:
                return self._json({"restored": 0, "problems": ["Nothing to undo."]})
            restored, problems = planner.undo(journal)
            return self._json({"restored": restored, "problems": problems})
        return self._json({"error": "not found"}, 404)


def serve(the_plan, port=8765, open_browser=True):
    Handler.state["plan"] = the_plan
    httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=str(WEB)))
    url = f"http://127.0.0.1:{port}/?local=1"
    print(f"Review your tidy plan at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
