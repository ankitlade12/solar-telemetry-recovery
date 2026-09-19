"""Acquire the four declared public source snapshots into a separate directory."""
from pathlib import Path
import subprocess
import sys


if __name__=='__main__':
    assert Path('research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md').exists()
    for site in (1367,1239):
        for year in (2016,2017):
            subprocess.run([sys.executable,'-m','solar_recovery.acquire','--system-id',str(site),
                '--year',str(year),'--max-mb','30','--root','data/raw/extension_v1'],check=True)
