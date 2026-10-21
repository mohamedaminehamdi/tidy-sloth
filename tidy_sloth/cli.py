"""tidy-sloth: learn how you file things, propose a tidy for Downloads and Desktop, apply it with one click.

  tidy-sloth              scan, build the plan, open the review screen
  tidy-sloth --overnight  build the plan slowly and quietly, review it in the morning
  tidy-sloth --eval       how well it re-files files you already filed (held-out test)
  tidy-sloth --undo       put the last tidy back
"""
import argparse
import json
import time
from pathlib import Path

from . import learn, plan, scan

PLAN_FILE = Path.home() / ".tidy-sloth" / "plan.real.json"


def build_plan(use_gemma=True):
    t0 = time.time()
    folders = scan.filing_folders(skip=[Path.cwd()])
    print(f"Learning from {len(folders)} of your folders...")
    paths, labels = learn.training_set(folders)
    todo, skipped = scan.loose_files()
    meta = scan.metadata(paths + todo)
    model = learn.FolderModel().fit(paths, labels, meta) if len(set(labels)) >= 2 else None
    print(f"{len(todo)} loose files to look at, {len(skipped)} left alone on purpose.")
    the_plan = plan.build(todo, skipped, model, meta, use_gemma=use_gemma)
    the_plan["summary"]["seconds"] = round(time.time() - t0)
    PLAN_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAN_FILE.write_text(json.dumps(the_plan, indent=1))
    s = the_plan["summary"]
    print(f"Plan: {s['moves']} moves, {s['renames']} renames, {s['left']} left alone, about {s['minutes_saved']} min of your time.")
    return the_plan


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tidy-sloth", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--overnight", action="store_true", help="build the plan only; review it later with tidy-sloth --review")
    ap.add_argument("--review", action="store_true", help="open the last saved plan without rescanning")
    ap.add_argument("--eval", action="store_true", help="held-out accuracy on your own folders")
    ap.add_argument("--undo", action="store_true", help="undo the last tidy")
    ap.add_argument("--no-gemma", action="store_true", help="skip naming and document routing (faster)")
    args = ap.parse_args(argv)

    if args.undo:
        journal = plan.latest_journal()
        restored, problems = plan.undo(journal) if journal else (0, ["Nothing to undo."])
        print(f"Restored {restored} files.", *problems, sep="\n")
        return
    if args.eval:
        print(json.dumps(learn.evaluate(scan.filing_folders(skip=[Path.cwd()])), indent=1))
        return
    if args.review and PLAN_FILE.exists():
        the_plan = json.loads(PLAN_FILE.read_text())
    else:
        the_plan = build_plan(use_gemma=not args.no_gemma)
    if args.overnight:
        print("Plan saved. In the morning: tidy-sloth --review")
        return
    from .server import serve
    serve(the_plan)
