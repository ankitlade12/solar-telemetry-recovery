"""Monitor one confirmed run process, then verify/analyze/reproduce; never refit."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from solar_recovery.pilot import digest


def process_identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True)
    if result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip():
        return None
    if result.returncode:
        raise RuntimeError('Cannot inspect confirmed run process: '+result.stderr.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-pid', required=True, type=int)
    parser.add_argument('--run', default='runs/producing_extension_v1')
    parser.add_argument('--reproduced', default='runs/producing_extension_reproduced_v1')
    args = parser.parse_args()
    root = Path(args.run)
    if args.run != 'runs/producing_extension_v1' or args.reproduced != 'runs/producing_extension_reproduced_v1':
        raise ValueError('Only this declared existing run is authorized by the completion queue')
    identity = process_identity(args.run_pid)
    if identity is not None and '-m research.producing_extension --output '+args.run not in identity:
        raise ValueError('PID is not the confirmed replication command')
    if not root.is_dir():
        raise ValueError('Existing run required; this queue never starts training')
    folder = root/'completion_workflow'
    folder.mkdir(exist_ok=False)
    state_path = folder/'extension_completion.json'
    source_names = ['research/complete_producing_extension.py', 'research/verify_producing_extension.py',
        'research/verify_final_evaluation.py', 'research/analyze_producing_extension.py',
        'research/analyze_final_evaluation.py', 'research/producing_extension_analysis_derivation.json',
        'research/producing_extension_analysis_test_record.json', 'tests/test_producing_extension_analysis.py']
    sources = {name: digest(name) for name in source_names}
    state = {'status': 'waiting for confirmed existing replication process', 'run_pid': args.run_pid,
        'process_identity_at_start': identity, 'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'code_sha256': sources, 'stages': [], 'forecast_performance_inspected_by_assistant': False,
        'policy': 'No retraining/restart; PID identity changes or failed run stop the queue'}
    def save():
        state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(state, indent=2)+'\n')
    save()
    try:
        began = time.monotonic()
        while identity is not None:
            if time.monotonic()-began > 24*3600:
                raise TimeoutError('Monitor expired after 24 h; no restart attempted')
            time.sleep(15)
            current = process_identity(args.run_pid)
            if current is not None and current != identity:
                raise RuntimeError('PID identity changed; do not confuse a reused PID with this run')
            if current is None:
                break
        manifest = json.loads((root/'manifest.json').read_text())
        if manifest['status'] != 'complete frozen evaluation':
            raise RuntimeError('Confirmed run process ended without a complete manifest; preserve failure')
        for name, expected in sources.items():
            if digest(name) != expected:
                raise ValueError('Completion dependency changed while waiting: '+name)
        for name in source_names:
            target = root/'extension_analysis_source'/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(name, target)
        commands = [
            [sys.executable, '-m', 'research.verify_producing_extension', args.run],
            [sys.executable, '-m', 'research.analyze_producing_extension', args.run],
            [sys.executable, '-m', 'research.analyze_producing_extension', args.run, '--output', args.reproduced],
        ]
        for number, command in enumerate(commands, 1):
            state['status'] = f'running completion stage {number}'
            log = folder/f'stage_{number}.log'
            with log.open('x') as handle:
                child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT)
                row = {'stage': number, 'command': command, 'pid': child.pid, 'started_at_utc': datetime.now(timezone.utc).isoformat()}
                state['stages'].append(row); save()
                print('Started completion stage', number, 'PID', child.pid, flush=True)
                row['returncode'] = child.wait()
            row['log_sha256'] = digest(log); save()
            if row['returncode']:
                raise RuntimeError(f'Completion stage {number} failed; see {log}')
        state['status'] = 'verification, analysis and table reproduction complete; interpretation pending'
        state['evidence_sha256'] = {str(p): digest(p) for p in [root/'verification.json', root/'analysis/manifest.json',
            Path(args.reproduced)/'reproduction_comparison.json']}
        save()
        print(state['status'], flush=True)
    except Exception as error:
        state['status'] = 'failed; no restart attempted'
        state['error'] = repr(error); save()
        raise


if __name__ == '__main__':
    main()
