"""Trusted publisher for the frozen TW trade-ledger experiment (stdlib only)."""
import argparse
import csv
from datetime import date
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

if __package__:
    from .research_evidence import END, HOLDOUT, HORIZON, ROOT, START, sessions
else:
    from research_evidence import END, HOLDOUT, HORIZON, ROOT, START, sessions

BASE = "9ba6856acb9203a0127c6686721e918c14f5b2b1"
LEDGERS = {"v2": "tw_rev_momentum_v2", "A-track": "tw_a_track", "v3": "tw_reversal_v3"}
FINAL_TAG = "refs/tags/research-tw-holdout-2025-11-29-consumed"


def registration(table, experiment, digest):
    rows = [[s.strip() for s in line.strip().strip("|").split("|")]
            for line in table.splitlines() if line.startswith("|")]
    matches = [row for row in rows if row[0] == experiment]
    if len(matches) != 1:
        raise ValueError("expected one registration for this ID")
    row = matches[0]
    if len(row) != 6 or not all(row) or row[4:] != ["REGISTERED", digest]:
        raise ValueError("register hypothesis, threshold and exact program hash before running")
    date.fromisoformat(row[1])
    return True


def budget(table, experiment):
    ids = re.findall(r"^\| (new-[0-9]+) \|", table, re.MULTILINE)
    if ids != [f"new-{i}" for i in range(1, len(ids) + 1)] or experiment not in ids:
        raise ValueError("append consecutive, unique experiment IDs")
    k = ids.index(experiment) + 1
    for earlier in ids[:k - 1]:
        prior = next(line for line in table.splitlines() if line.startswith(f"| {earlier} |"))
        if prior.split("|")[5].strip() == "REGISTERED":
            raise ValueError("record the previous result or withdrawal before the next run")
    return .025 / (k * (k + 1))


def decision(result, alpha):
    p, gates = result["p"], result["gates_passed"]
    if type(gates) is not bool or (p is not None and
            (type(p) not in (float, int) or not 0 <= p <= 1)):
        raise ValueError("invalid primary result")
    if p is None:
        return "INSUFFICIENT_DATA"
    return "PASS" if p <= alpha and gates else "FAIL"


def include_trade(row, name, days, idx, final):
    signal = date.fromisoformat(row["signal"])
    i = idx[signal]
    if date.fromisoformat(row["entry"]) != days[i + 1]:
        raise ValueError("entry differs from frozen signal calendar")
    if row["exit"] and not (days[i + 1] <= date.fromisoformat(row["exit"]) <= END):
        raise ValueError("unexpected exit date")
    if final:
        return HOLDOUT <= signal <= END
    maturity = i + 1 + HORIZON[name]
    return (START <= signal < HOLDOUT and maturity < len(days) and days[maturity] < HOLDOUT
            and (not row["exit"] or date.fromisoformat(row["exit"]) < HOLDOUT))


def publish(folder, final):
    days = sessions()
    idx = {d: i for i, d in enumerate(days)}
    folder.mkdir()  # A new directory cannot contain stale files or symlinks.
    for name, stem in LEDGERS.items():
        ref = f"{BASE}:results/{stem}_trades.csv"
        raw = subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}",
                                       "show", ref], cwd=ROOT)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        with (folder / f"{name}.csv").open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
            writer.writeheader()
            writer.writerows(row for row in reader if include_trade(row, name, days, idx, final))


def docker_command(bundle):
    return ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user=65534:65534", "--tmpfs=/tmp",
            "--mount", f"type=bind,src={bundle.resolve()},dst=/research,readonly",
            "--workdir=/research", "python:3.12-slim", "python", "-I", "strategy.py"]


def claim_run(ref, sha, token):
    request = Request("https://api.github.com/repos/JC0303/jc-investing-data/git/refs",
                      data=json.dumps({"ref": ref, "sha": sha}).encode(),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urlopen(request, timeout=30) as response:
        if response.status != 201:
            raise RuntimeError("experiment reference was not created")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["export-train", "dev", "final"])
    parser.add_argument("path", type=Path, help="new export directory or registered Python program")
    parser.add_argument("--id")
    args = parser.parse_args()
    if args.mode == "export-train":
        publish(args.path, False)
        return
    if not re.fullmatch(r"new-[1-9][0-9]*", args.id or ""):
        raise ValueError("expected a registered new-K ID")
    program = args.path.read_bytes()
    digest = hashlib.sha256(program).hexdigest()
    table = (ROOT / "results/experiments.md").read_text(encoding="utf-8")
    registration(table, args.id, digest)
    alpha = budget(table, args.id)
    registered_row = next(line for line in table.splitlines() if line.startswith(f"| {args.id} |"))
    if not registered_row.split("|")[4].strip().startswith(args.mode + " "):
        raise ValueError("threshold column must start with registered mode: dev or final")
    final = args.mode == "final"
    if os.environ.get("GITHUB_REPOSITORY") != "JC0303/jc-investing-data":
        raise ValueError("registered runs require the repository workflow")
    if final and os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise ValueError("final requires the reviewed main workflow")
    sha = os.environ["GITHUB_SHA"]
    if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != sha:
        raise ValueError("checkout differs from approved commit")
    claim_run(f"refs/tags/research-tw-{args.id}-consumed", sha, os.environ["GITHUB_TOKEN"])
    if final:
        claim_run(FINAL_TAG, sha, os.environ["GITHUB_TOKEN"])
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "bundle"
        publish(bundle, final)
        (bundle / "strategy.py").write_bytes(program)
        completed = subprocess.run(docker_command(bundle), check=True, capture_output=True, text=True)
        result = json.loads(completed.stdout)
        print(json.dumps(dict(id=args.id, sha256=digest, alpha=alpha, result=result,
                              verdict=decision(result, alpha)), allow_nan=False))


if __name__ == "__main__":
    main()
