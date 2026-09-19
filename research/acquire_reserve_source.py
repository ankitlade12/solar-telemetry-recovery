"""Acquire the predeclared reserve; source data only, no forecasting."""
from pathlib import Path
import subprocess
import sys


if __name__ == '__main__':
    assert Path('research/RESERVE_SOURCE_10_PLAN.md').exists()
    for year in (2016, 2017):
        subprocess.run([
            sys.executable, '-m', 'solar_recovery.acquire', '--system-id', '10',
            '--year', str(year), '--max-mb', '80', '--root', 'data/raw/extension_v1',
        ], check=True)
