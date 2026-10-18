import argparse, re, sys
from typing import cast
from .config import load_job
from .planner import make_plan, format_plan, save_plan, load_plan
from .runner import run

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lsv2", description="Waymo lidar range images -> MAE-ST video clips (see DESIGN.md)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="resolve a job.json against its source and write plan.json; downloads nothing")
    _ = p.add_argument("job"); _ = p.add_argument("-o", "--output", default="plan.json")
    r = sub.add_parser("run", help="execute a plan.json; resumable")
    _ = r.add_argument("plan"); _ = r.add_argument("--yes", action="store_true", help="skip the confirmation (tmux runs)")
    a = ap.parse_args(argv)
    if cast(str, a.cmd) == "plan":
        output = cast(str, a.output)
        plan = make_plan(load_job(cast(str, a.job))); save_plan(plan, output)
        print(format_plan(plan)); print(f"\nplan written to {output}")
        return 0
    plan = load_plan(cast(str, a.plan)); print(format_plan(plan))
    if not cast(bool, a.yes) and not confirm(): return 1
    _ = run(plan)
    return 0

def confirm() -> bool:
    # read the answer without readline: it would emit bracketed-paste escape sequences that leak into the answer on some terminals
    print("\nproceed? [y/N] ", end="", flush=True)
    line = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", sys.stdin.readline())   # CSI sequences (bracketed paste markers etc.)
    answer = "".join(ch for ch in line if ch.isalpha()).lower()
    if answer in ("y", "yes"): return True
    print(f"aborted: answer was {answer!r}, nothing was done (use --yes to skip the question)")
    return False

if __name__ == "__main__": sys.exit(main())
