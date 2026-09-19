"""Queue deterministic paper exports, table reproduction and latency measurement."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from solar_recovery.pilot import digest


def finish(root, output):
    root, output = Path(root), Path(output)
    if output.exists():
        raise FileExistsError("Preserve earlier workflow records; choose a new directory")
    output.mkdir(parents=True)
    status = {"stage": "waiting for verified analysis", "stages": [],
        "workflow_sha256": digest(Path(__file__)), "run": str(root)}

    def save():
        status["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        temporary = output/"status.tmp"
        temporary.write_text(json.dumps(status, indent=2)+"\n")
        temporary.replace(output/"status.json")

    save()
    while True:
        upstream = json.loads((root/"completion_workflow/status.json").read_text())
        if upstream["stage"] == "failed":
            status.update(stage="failed", reason="Upstream verification/analysis failed; inspect its retained logs")
            save()
            raise RuntimeError(status["reason"])
        if upstream["stage"] == "complete verified analysis; manuscript synthesis remains":
            break
        time.sleep(20)
    commands = [
        ("research.export_paper_tables", [str(root), "--output", "paper/generated"]),
        ("research.analyze_final_evaluation", [str(root), "--output", str(output/"reproduced_tables")]),
        ("research.benchmark_inference", [str(root), "--output", "runs/inference_benchmark_v1"]),
    ]
    for module, arguments in commands:
        command = [sys.executable, "-u", "-m", module, *arguments]
        status["stage"] = module
        save()
        source = Path(module.replace(".", "/")+".py")
        entry = {"command": command, "source_sha256": digest(source),
            "began_at_utc": datetime.now(timezone.utc).isoformat()}
        log = output/(module.rsplit(".", 1)[-1]+".log")
        with log.open("w") as handle:
            result = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT,
                env={**os.environ, "MPLCONFIGDIR": "/private/tmp/solar-recovery-export-mpl"})
        entry.update(returncode=result.returncode, log_sha256=digest(log),
            ended_at_utc=datetime.now(timezone.utc).isoformat())
        status["stages"].append(entry)
        if result.returncode:
            status.update(stage="failed", reason=f"{module} failed; inspect its retained log")
            save()
            raise RuntimeError(status["reason"])
    status["stage"] = "complete exports, table reproduction and latency; manuscript synthesis remains"
    save()
    print(status["stage"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    finish(args.run, args.output)
