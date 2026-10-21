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


def test_server_refuses_other_hosts_and_origins():
    import threading, urllib.request, urllib.error
    from http.server import ThreadingHTTPServer
    from tidy_sloth import server
    server.Handler.state["plan"] = {"items": [], "skipped": [], "summary": {}}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url, port = f"http://127.0.0.1:{httpd.server_port}/api/plan", httpd.server_port

    def status(headers, method="GET"):
        req = urllib.request.Request(url, headers=headers, method=method, data=b"{}" if method == "POST" else None)
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as e:
            return e.code
    try:
        assert status({}) == 200
        assert status({"Host": f"evil.example:{port}"}) == 403  # DNS rebinding
        assert status({"Origin": "https://evil.example"}, "POST") == 403
    finally:
        httpd.shutdown()
