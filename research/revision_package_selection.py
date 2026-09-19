"""Current-revision public evidence selection; no archive or publication."""
import json
from pathlib import Path

from research.package_public_release import candidate_files
from research.package_submission import checked_path, verify_claim_ledger
from research.release_protocol import PRIVATE_PRD
from solar_recovery.pilot import digest


def add_claim_and_lock_dependencies(workspace, files, ledger_paths, lock_paths):
    workspace = Path(workspace).resolve(); files = set(files)
    for name in ledger_paths:
        path = checked_path(workspace, name)
        ledger = json.loads(path.read_text())
        verify_claim_ledger(workspace, ledger)
        files.add(name)
        files.update(c['source_path'] for c in ledger['claims'])
    for name in lock_paths:
        path = checked_path(workspace, name)
        lock = json.loads(path.read_text()); files.add(name)
        for dependency, expected in lock['files_sha256'].items():
            if dependency == PRIVATE_PRD:
                continue  # Public absence is deliberate; release-view validation is a separate required gate.
            if digest(checked_path(workspace, dependency)) != expected:
                raise ValueError('Changed locked dependency: '+dependency)
            files.add(dependency)
    canonical = {checked_path(workspace, p).relative_to(workspace).as_posix() for p in files}
    if PRIVATE_PRD in canonical or any(p.startswith('research/sources/') for p in canonical):
        raise ValueError('Private planning or copied external papers entered the public selection')
    return canonical


def verified_extension_files(workspace, extension_run):
    workspace = Path(workspace).resolve()
    folder = (workspace/extension_run).resolve()
    if not folder.is_relative_to(workspace) or not folder.is_dir():
        raise ValueError('Missing or out-of-workspace extension directory')
    manifest = json.loads((folder/'manifest.json').read_text())
    if manifest['status'] != 'complete frozen evaluation':
        raise ValueError('Extension must finish before packaging')
    verification = json.loads((folder/'verification.json').read_text())
    analysis = json.loads((folder/'analysis/manifest.json').read_text())
    if not verification['status'].startswith('passed') or analysis['status'] != 'complete analysis':
        raise ValueError('Completed extension verification and analysis required')
    if verification['manifest_sha256'] != digest(folder/'manifest.json') or analysis['source_manifest_sha256'] != digest(folder/'manifest.json'):
        raise ValueError('Extension changed since verification/analysis')
    for base, record in [(folder, verification), (folder/'analysis', analysis)]:
        for name, expected in record['files_sha256'].items():
            if digest(checked_path(base, name)) != expected:
                raise ValueError('Verified extension artifact changed: '+name)
    return {p.relative_to(workspace).as_posix() for p in folder.rglob('*')
            if p.is_file() and 'completion_workflow' not in p.parts and p.suffix != '.log'}


def revised_candidate_files(workspace, original_run, extension_run=None):
    workspace = Path(workspace).resolve()
    selected = candidate_files(workspace, Path(original_run))
    ledgers = [p.relative_to(workspace).as_posix() for p in sorted((workspace/'paper').glob('claim_evidence*.json'))]
    locks = ['research/FINAL_PROTOCOL_LOCK.json', 'research/PRODUCING_EXTENSION_LOCK_V1.json']
    selected = add_claim_and_lock_dependencies(workspace, selected, ledgers, locks)
    # Retain both admitted and unadmitted source-screen outcomes. Do not copy
    # local article downloads or historical manuscript backups into this view.
    trees = ['research/staff_review_v2', 'research/colorado_channel_investigation_v2',
             'research/extension_source_screen_v1', 'research/maine_qualification_v1',
             'research/reserve_10_qualification_v1', 'runs/public_extension_dependency_check_v3']
    for directory in trees:
        for path in (workspace/directory).rglob('*'):
            relative = path.relative_to(workspace)
            if path.is_file() and not any(p in {'before', '__pycache__'} for p in relative.parts) and path.suffix != '.pyc':
                selected.add(relative.as_posix())
    for path in (workspace/'data/raw/extension_v1').glob('*/manifest.json'):
        selected.add(path.relative_to(workspace).as_posix())
    selected.update(['ARTIFACT_GUIDE.md', 'research/README.md',
        'research/PRODUCING_EXTENSION_EXECUTION.md', 'research/producing_extension_analysis_test_record.json',
        'research/producing_extension_analysis_derivation.json', 'research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md',
        'research/RESERVE_SOURCE_10_PLAN.md', 'research/extension_source_availability_v1.json',
        'research/bibliography_name_fix_v1/manifest.json', 'research/current_package_dependency_audit.json',
        'research/public_extension_verifier_derivation.json', 'research/public_extension_release_test_record.json',
        'research/current_review_package_test_record.json', 'research/current_public_package_test_record.json',
        'research/PRODUCING_EXTENSION_PERFORMANCE_EXPOSURE.json', 'research/PRODUCING_EXTENSION_FINDINGS.md',
        'research/extension_manuscript_revision_v1/manifest.json',
        'research/extension_manuscript_revision_v1/integrate_evidence_executed_v2.py',
        'research/integrated_presentation_reproduction_check.json'])
    if extension_run is not None:
        selected.update(verified_extension_files(workspace, extension_run))
    return sorted(checked_path(workspace, p).relative_to(workspace).as_posix() for p in selected)
