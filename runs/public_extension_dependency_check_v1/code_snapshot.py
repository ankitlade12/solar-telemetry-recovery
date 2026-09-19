"""Exercise public extension dependency verification without private PRD bytes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from research.extension_release_protocol import PUBLIC
from research.release_protocol import PRIVATE_PRD
from solar_recovery.pilot import digest


def main():
    root = Path.cwd()
    stage = Path('/private/tmp/solar-extension-public-closure-v1')
    output = root/'runs/public_extension_dependency_check_v1'
    if stage.exists() or output.exists():
        raise FileExistsError('Choose a fresh isolated dependency-check version')
    view = json.loads(PUBLIC.read_text())
    extra = [str(PUBLIC), 'research/extension_release_protocol.py', 'research/reproduce_public_extension.py',
        'research/verify_public_extension.py', 'research/public_extension_verifier_derivation.json']
    paths = sorted(set(view['files_sha256']) | set(extra))
    if PRIVATE_PRD in paths:
        raise ValueError('Private PRD must not be copied')
    stage.mkdir(); output.mkdir(parents=True)
    for name in paths:
        path = stage/name;path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/name, path)
        if digest(path) != digest(root/name):
            raise ValueError('Copy changed source bytes: '+name)
    code = '''from pathlib import Path
import json,sys
from research.extension_release_protocol import verification_protocol
from research.verify_public_extension import verify
import research.reproduce_public_extension
root=Path.cwd().resolve()
assert not (root/'Solar_Forecasting_Research_PRD.docx').exists()
f,p=verification_protocol('configs/producing_extension_v1.json','research/PRODUCING_EXTENSION_LOCK_V1.json','release/PRODUCING_EXTENSION_DEPENDENCY_LOCK.json')
assert p['scientific_dependencies_verified']==138 and not p['private_prd_bytes_verified']
imports={}
for name,module in sorted(sys.modules.items()):
    if name.startswith(('research.', 'solar_recovery.')) and getattr(module,'__file__',None):
        path=Path(module.__file__).resolve()
        assert path.is_relative_to(root), (name,str(path))
        imports[name]=str(path.relative_to(root))
print(json.dumps({'protocol':p,'imports_from_isolated_directory':imports,'private_prd_absent':True},indent=2))
'''
    env = {**os.environ, 'PYTHONPATH': str(stage), 'MPLCONFIGDIR': str(stage/'cache/matplotlib')}
    result = subprocess.run([sys.executable, '-c', code], cwd=stage, env=env, capture_output=True, text=True)
    (output/'stdout.log').write_text(result.stdout);(output/'stderr.log').write_text(result.stderr)
    record = {'status': 'passed isolated public extension dependency verification' if result.returncode == 0 else 'failed dependency verification',
        'returncode': result.returncode, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': str(stage), 'private_prd_absent': not (stage/PRIVATE_PRD).exists(),
        'copied_files': len(paths), 'copied_bytes': sum((stage/p).stat().st_size for p in paths),
        'code_sha256': digest(Path(__file__)), 'view_sha256': digest(PUBLIC),
        'source_files_sha256': {p: digest(stage/p) for p in paths},
        'logs_sha256': {p.name: digest(p) for p in output.glob('*.log')},
        'scope': 'Actual isolated copied source/data dependency verification and import-origin checks, same installed environment; no full-data refit, final-result reproduction, fresh package installation, human reproduction or public release'}
    (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    if result.returncode:
        raise RuntimeError('Public dependency check failed; inspect retained logs')
    print('Verified all 138 dependencies without private PRD; imports resolved inside isolated directory')


if __name__ == '__main__':
    main()
