"""Offline safety checks: what Tidy Sloth refuses to touch, and that undo really puts things back."""
import os
import time
from pathlib import Path

from tidy_sloth import features, plan, rename, scan


def test_secrets_are_never_planned(tmp_path):
    for name in ["server.pem", "id_ed25519", "wallet backup.txt", "my passwords.txt", ".env", "invoice.pdf"]:
        (tmp_path / name).write_text("x")
    old = time.time() - 3600
    for f in tmp_path.iterdir():
        os.utime(f, (old, old))
    todo, skipped = scan.loose_files([tmp_path])
    assert [Path(p).name for p in todo] == ["invoice.pdf"]
    assert {Path(p).name for p, _ in skipped} == {"server.pem", "id_ed25519", "wallet backup.txt", "my passwords.txt"}


def test_recent_files_are_left_alone(tmp_path):
    (tmp_path / "still-downloading.pdf").write_text("x")
    todo, skipped = scan.loose_files([tmp_path])
    assert todo == [] and "10 minutes" in skipped[0][1]


def test_code_projects_are_not_filing_folders(tmp_path):
    (tmp_path / "trip").mkdir()
    (tmp_path / "trip" / "beach.jpg").write_text("x")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "package.json").write_text("{}")
    (tmp_path / "scripts").mkdir()
    for i in range(5):
        (tmp_path / "scripts" / f"run{i}.py").write_text("print()")
    assert [f.name for f in scan.filing_folders([tmp_path])] == ["trip"]


def test_generic_names():
    for junk in ["IMG_4821.HEIC", "Screenshot 2026-10-21 at 14.03.22.png", "document (3).pdf", "Untitled.txt",
                 "3f2a9c1e-8b7d-4e2a-9c1f-2b3a4c5d6e7f.jpg", "WhatsApp Image 2026-01-02 at 10.11.12.jpeg", "20240512_140322.jpg"]:
        assert rename.is_generic(junk), junk
    for real in ["Lisbon trip budget.xlsx", "CV Mohamed 2026.pdf", "logo-final.png", "notes.txt"]:
        assert not rename.is_generic(real), real


def test_clean_name_strips_path_tricks():
    assert rename.clean_name("../../etc/passwd: bill\n") == "etc passwd bill"  # no slashes, no leading dots
    assert "/" not in rename.clean_name("a/b\\c")


def test_apply_and_undo_roundtrip(tmp_path):
    loose, home = tmp_path / "Downloads", tmp_path / "Desktop" / "taxes"
    loose.mkdir(parents=True)
    home.mkdir(parents=True)
    (loose / "scan.pdf").write_text("a")
    (loose / "photo.jpg").write_text("b")
    (home / "scan.pdf").write_text("already here")  # collision: must not overwrite
    the_plan = {"items": [
        {"id": 0, "path": str(loose / "scan.pdf"), "folder": str(home), "new_name": None, "action": "move"},
        {"id": 1, "path": str(loose / "photo.jpg"), "folder": None, "new_name": "Beach at sunset.jpg", "action": "rename"},
    ]}
    journal = plan.apply(the_plan, journal_dir=tmp_path / "journals")
    assert (home / "scan.pdf").read_text() == "already here"
    assert (home / "scan (2).pdf").read_text() == "a"
    assert (loose / "Beach at sunset.jpg").read_text() == "b"
    restored, problems = plan.undo(journal)
    assert restored == 2 and not problems
    assert (loose / "scan.pdf").read_text() == "a" and (loose / "photo.jpg").read_text() == "b"
    assert not (home / "scan (2).pdf").exists()


def test_feature_table_shape(tmp_path):
    paths = [str(tmp_path / n) for n in ["IMG_1.jpg", "bill.pdf", "talk.mp4"]]
    meta = {p: {"source": "drive.google.com" if i else "", "created_days": 20000.0 + i, "lat": float("nan"),
                "lon": float("nan"), "size": 1000 * (i + 1)} for i, p in enumerate(paths)}
    X = features.Featurizer().fit(paths, meta).transform(paths, meta)
    assert X.shape == (3, len(features.COLUMNS))


def test_leftovers_of_one_kind_get_a_new_folder(tmp_path):
    items = [{"id": i, "path": f"/dl/book{i}.epub", "folder": None, "folder_name": None, "new_name": None, "action": "leave"} for i in range(3)]
    items.append({"id": 9, "path": "/dl/lonely.mp4", "folder": None, "folder_name": None, "new_name": None, "action": "leave"})
    plan.suggest_new_folders(items, tmp_path)
    assert {i["folder_name"] for i in items[:3]} == {"Books"} and all(i["by"] == "new_folder" for i in items[:3])
    assert items[3]["action"] == "leave"  # one video isn't a pattern


class _Server:
    """A real review server on a free port, for poking at it like the page (or an attacker) would."""

    def __init__(self, state):
        import threading
        from http.server import ThreadingHTTPServer
        from tidy_sloth import server
        server.Handler.state.update({"plan": None, "step": "", "error": None, "building": False, "journal": None, **state})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_port
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def call(self, path, body=None, headers=None):
        import json, urllib.request, urllib.error
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", headers=headers or {},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_server_refuses_other_hosts_and_origins():
    with _Server({"plan": {"items": [], "skipped": [], "summary": {}}}) as srv:
        assert srv.call("/api/plan")[0] == 200
        assert srv.call("/api/plan", headers={"Host": f"evil.example:{srv.port}"})[0] == 403  # DNS rebinding
        assert srv.call("/api/apply", {}, headers={"Origin": "https://evil.example"})[0] == 403


def test_server_while_building_and_with_a_stale_page(tmp_path, monkeypatch):
    with _Server({"building": True, "step": "Learning…"}) as srv:
        assert srv.call("/api/plan") == (200, {"building": True, "step": "Learning…"})
        assert srv.call("/api/apply", {"token": "x", "items": []})[0] == 409  # nothing to apply yet
    (tmp_path / "a.pdf").write_text("a")
    monkeypatch.setattr(plan, "JOURNALS", tmp_path / "journals")
    the_plan = {"token": "t1", "items": [{"id": 0, "path": str(tmp_path / "a.pdf"), "folder": str(tmp_path / "Taxes"),
                                          "new_name": None, "action": "move"}], "skipped": [], "summary": {}}
    with _Server({"plan": the_plan}) as srv:
        assert srv.call("/api/apply", {"token": "old", "items": [{"id": 0}]})[0] == 409  # page from another plan
        assert srv.call("/api/apply", {"token": "t1", "items": [{"id": 0}]})[1]["moved"] == [0]
        assert srv.call("/api/apply", {"token": "t1", "items": [{"id": 0}]})[0] == 409  # double click
        assert (tmp_path / "Taxes" / "a.pdf").exists()


def test_repeat_apply_keeps_the_undo(tmp_path):
    (tmp_path / "a.pdf").write_text("a")
    (tmp_path / "b.pdf").write_text("b")
    item = lambda i, n: {"id": i, "path": str(tmp_path / n), "folder": str(tmp_path / "Taxes"), "new_name": None, "action": "move"}
    first = plan.apply({"items": [item(0, "a.pdf")]}, journal_dir=tmp_path / "j")
    assert plan.apply({"items": [item(0, "a.pdf")]}, journal_dir=tmp_path / "j") is None  # nothing left to move
    second = plan.apply({"items": [item(1, "b.pdf")]}, journal_dir=tmp_path / "j")
    assert first != second and first.exists() and second.exists()  # same second, two journals


def test_saved_plan_drops_files_that_changed(tmp_path):
    for n in ["kept.pdf", "edited.pdf", "gone.pdf"]:
        (tmp_path / n).write_text(n)
    items = []
    for i, n in enumerate(["kept.pdf", "edited.pdf", "gone.pdf"]):
        st = os.stat(tmp_path / n)
        items.append({"id": i, "path": str(tmp_path / n), "action": "move", "size": st.st_size, "mtime": st.st_mtime})
    plan.save({"built": time.time(), "items": items, "skipped": [], "summary": {}}, tmp_path / "plan.json")
    (tmp_path / "edited.pdf").write_text("edited, now longer")
    (tmp_path / "gone.pdf").unlink()
    fresh = plan.load_fresh(tmp_path / "plan.json", max_age=3600)
    assert [i["path"] for i in fresh["items"]] == [str(tmp_path / "kept.pdf")] and fresh["summary"]["moves"] == 1
    plan.save({**fresh, "applied": "journal.json"}, tmp_path / "plan.json")
    assert plan.load_fresh(tmp_path / "plan.json") is None  # already applied: look again instead


def test_mac_app_is_ours_signed_and_never_replaces_someone_elses(tmp_path):
    import plistlib, subprocess, pytest
    from tidy_sloth import install
    app = install.make_app("/opt/tidy sloth/bin/tidy-sloth", app=tmp_path / "Tidy Sloth.app")
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleIdentifier"] == install.BUNDLE_ID and "CFBundleIconName" not in info
    assert (app / "Contents" / "Resources" / "applet.icns").read_bytes() == install.ICON.read_bytes()
    assert subprocess.run(["codesign", "--verify", "--deep", str(app)]).returncode == 0
    install.make_app("/opt/tidy sloth/bin/tidy-sloth", app=app)  # reinstalling over our own app is fine
    other = tmp_path / "Other.app" / "Contents"
    other.mkdir(parents=True)
    (other / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "com.example.other"}))
    with pytest.raises(SystemExit):
        install.make_app("/x", app=other.parent)
    assert (other / "Info.plist").exists()
