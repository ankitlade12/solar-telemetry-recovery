"""Reproduce the fixed extension with its exact public dependency view."""
import argparse
import json
from pathlib import Path

from research.extension_release_protocol import PUBLIC, verification_protocol
from research.final_evaluation import run
from research.producing_extension import CONFIG, validate_config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    verification_protocol(CONFIG, PUBLIC, PUBLIC)
    validate_config(json.loads(CONFIG.read_text()), json.loads(Path('configs/final_evaluation_v4.json').read_text()))
    print('Reproducing an already declared extension; no new prospective evaluation claim', flush=True)
    run(CONFIG, PUBLIC, args.output)
