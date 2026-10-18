import argparse, re, sys
from .config import load_job
from .planner import make_plan, format_plan, save_plan, load_plan
from .runner import run

def main(argv=None):
    ap = argparse.ArgumentParser(prog="lsv2", description="Waymo lidar range images -> MAE-ST video clips (see DESIGN.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="resolve a job.json against its source and write plan.json; downloads nothing")
    p.add_argument("job"); p.add_argument("-o", "--output", default="plan.json")
    r = sub.add_parser("run", help="execute a plan.json; resumable")
    r.add_argument("plan"); r.add_argument("--yes", action="store_true", help="skip the confirmation (tmux runs)")
    a = ap.parse_args(argv)
    if a.cmd == "plan":
        plan = make_plan(load_job(a.job)); save_plan(plan, a.output)
        print(format_plan(plan)); print(f"\nplan written to {a.output}")
        return 0
    plan = load_plan(a.plan); print(format_plan(plan))
    if not a.yes and not confirm(): return 1
    run(plan)
    return 0

def confirm():
    # read the answer without readline: it would emit bracketed-paste escape sequences that leak into the answer on some terminals
    print("\nproceed? [y/N] ", end="", flush=True)
    line = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", sys.stdin.readline())   # CSI sequences (bracketed paste markers etc.)
    answer = "".join(ch for ch in line if ch.isalpha()).lower()
    if answer in ("y", "yes"): return True
    print(f"aborted: answer was {answer!r}, nothing was done (use --yes to skip the question)")
    return False

if __name__ == "__main__": sys.exit(main())
