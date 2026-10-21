"""tidy-sloth: learn how you file things, propose a tidy for Downloads and Desktop, apply it with one click.

  tidy-sloth              open the review screen (uses last night's plan if there is one, else looks now)
  tidy-sloth --overnight  build the plan slowly and quietly, review it in the morning
  tidy-sloth --eval       how well it re-files files you already filed (held-out test)
  tidy-sloth --undo       put the last tidy back
  tidy-sloth --setup      download the models and make the Tidy Sloth app (the installer runs this)
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import learn, plan, scan

PLAN_FILE = Path.home() / ".tidy-sloth" / "plan.real.json"
FRESH = 24 * 3600  # an overnight plan is good for a day


def build_plan(use_gemma=True, progress=print):
    t0 = time.time()
    progress("macOS may ask if I can look in your folders…")
    scan.check_access()
    folders = scan.filing_folders(skip=[Path.cwd()])
    progress(f"Learning how you file things from {len(folders)} of your folders…")
    paths, labels = learn.training_set(folders)
    todo, skipped = scan.loose_files()
    progress(f"Reading the labels on {len(todo)} loose files…")
    meta = scan.metadata(paths + todo)
    model = learn.FolderModel().fit(paths, labels, meta) if len(set(labels)) >= 2 else None
    progress(f"Working out where {len(todo)} files go…")
    the_plan = plan.build(todo, skipped, model, meta, use_gemma=use_gemma, progress=progress)
    the_plan["summary"]["seconds"] = round(time.time() - t0)
    plan.save(the_plan, PLAN_FILE)
    return the_plan


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tidy-sloth", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--overnight", action="store_true", help="build the plan only; review it later by opening Tidy Sloth")
    ap.add_argument("--review", action="store_true", help="open the last saved plan, however old")
    ap.add_argument("--rescan", action="store_true", help="ignore last night's plan and look again now")
    ap.add_argument("--eval", action="store_true", help="held-out accuracy on your own folders")
    ap.add_argument("--undo", action="store_true", help="undo the last tidy")
    ap.add_argument("--no-gemma", action="store_true", help="skip naming and document routing (faster)")
    ap.add_argument("--setup", action="store_true", help="download Gemma 4 and TabPFN, make the Tidy Sloth app")
    ap.add_argument("--overnight-on", action="store_true", help="with --setup: build a plan every night at 3 am")
    ap.add_argument("--skip-models", action="store_true", help="with --setup: only make the app")
    ap.add_argument("--uninstall", action="store_true", help="remove the app and the nightly run")
    args = ap.parse_args(argv)
    use_gemma = not args.no_gemma

    if args.setup or args.uninstall:
        from . import install
        return install.uninstall() if args.uninstall else install.setup(models=not args.skip_models, overnight=args.overnight_on)
    if args.undo:
        journal = plan.latest_journal()
        restored, problems = plan.undo(journal) if journal else (0, ["Nothing to undo."])
        print(f"Restored {restored} files.", *problems, sep="\n")
        return
    if args.eval:
        print(json.dumps(learn.evaluate(scan.filing_folders(skip=[Path.cwd()])), indent=1))
        return
    if args.overnight:
        try:
            s = build_plan(use_gemma=use_gemma)["summary"]
        except PermissionError as exc:  # keep yesterday's good plan; say why in the log
            sys.exit(str(exc))
        print(f"Plan: {s['moves']} moves, {s['renames']} renames, {s['left']} left alone. Open Tidy Sloth to review it.")
        return

    from .server import serve
    saved = None if args.rescan else plan.load_fresh(PLAN_FILE, max_age=None if args.review else FRESH)
    serve(saved, build=lambda progress: build_plan(use_gemma=use_gemma, progress=progress), plan_file=PLAN_FILE)
