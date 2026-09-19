"""Wait for the frozen run, then verify and analyze it with retained stage logs."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from solar_recovery.pilot import digest


def finish(root, producer_pid):
    root = Path(root)
    workflow = root/"completion_workflow"
    if workflow.exists():
        raise FileExistsError("Completion workflow already exists")
    workflow.mkdir()
    status = {"stage": "waiting for frozen forecasts", "producer_pid": producer_pid,
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "stages": [],
        "workflow_code_sha256": digest(Path(__file__))}
    def save():
        status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        temporary = workflow/"status.tmp"
        temporary.write_text(json.dumps(status, indent=2)+"\n")
        temporary.replace(workflow/"status.json")
    save()
    while True:
        try:
            manifest = json.loads((root/"manifest.json").read_text())
        except json.JSONDecodeError:
            time.sleep(2)
            continue
        status["completed_cases"] = len(manifest.get("cases", {}))
        status["forecast_records"] = manifest.get("total_forecasts", 0)
        if manifest["status"] == "complete frozen evaluation":
            break
        try:
            os.kill(producer_pid, 0)
        except ProcessLookupError:
            status.update(stage="failed", reason="Producer exited before a complete forecast manifest")
            save()
            raise RuntimeError(status["reason"])
        except PermissionError:
            pass  # A sandbox can deny the existence probe; manifest remains authoritative.
        save()
        time.sleep(20)
    for module in ("research.verify_final_evaluation", "research.analyze_final_evaluation"):
        status["stage"] = module
        save()
        source = Path(module.replace(".", "/")+".py")
        record = {"module": module, "source_sha256": digest(source), "began_at_utc": datetime.now(timezone.utc).isoformat()}
        log = workflow/(module.rsplit(".", 1)[-1]+".log")
        with log.open("w") as handle:
            result = subprocess.run([sys.executable, "-u", "-m", module, str(root)], stdout=handle,
                stderr=subprocess.STDOUT, env={**os.environ, "MPLCONFIGDIR": "/private/tmp/solar-recovery-final-mpl"})
        record.update(returncode=result.returncode, log_sha256=digest(log), ended_at_utc=datetime.now(timezone.utc).isoformat())
        status["stages"].append(record)
        if result.returncode:
            status.update(stage="failed", reason=f"{module} failed; inspect the retained stage log")
            save()
            raise RuntimeError(status["reason"])
    status["stage"] = "complete verified analysis; manuscript synthesis remains"
    save()
    print(status["stage"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--producer-pid", type=int, required=True)
    args = parser.parse_args()
    finish(args.run, args.producer_pid)
