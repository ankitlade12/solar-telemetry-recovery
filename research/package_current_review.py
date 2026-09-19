"""Build the revised local review bundles only from a complete declaration."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from research.export_extension_evidence import checked_evidence
from research.extension_release_protocol import PUBLIC, verification_protocol
from research.package_submission import checked_path, verify_claim_ledger, write_archive
from research.release_protocol import PRIVATE_PRD, PRIVATE_PRD_SHA256
from research.revision_package_selection import revised_candidate_files
from solar_recovery.pilot import digest


def anonymous_metadata(metadata, pdf_hash):
    labels = metadata.get('anonymous_author_labels', [])
    if labels != ['Author 1', 'Author 2']:
        raise ValueError('Anonymous metadata requires placeholder author labels')
    if not metadata.get('title') or not metadata.get('abstract'):
        raise ValueError('Title and abstract are required')
    return {**{key: metadata[key] for key in ('title', 'abstract', 'keywords', 'venue', 'paper_type', 'anonymous_author_labels') if key in metadata},
        'pdf_sha256': pdf_hash, 'status': 'local anonymous review metadata; not submitted',
        'limits': 'Human anonymity/scientific review and final submission approval remain required'}


def validate_visual_evidence(workspace, declaration, audit, visual):
    render_path = checked_path(workspace, declaration['render_manifest'])
    render = json.loads(render_path.read_text())
    if visual.get('render_manifest_sha256') != digest(render_path) or render.get('pdf_sha256') != audit['pdf_sha256']:
        raise ValueError('Visual review is not bound to the current PDF rendering')
    expected_pages = list(range(1, audit['pages'] + 1))
    images, reviews = render.get('pages', []), visual.get('page_evidence', [])
    if ([row['page'] for row in images] != expected_pages or
            [row['page'] for row in reviews] != expected_pages or
            visual.get('pages') != audit['pages']):
        raise ValueError('Visual evidence must cover each current page exactly once')
    paths = {str(render_path.relative_to(workspace))}
    for image, review in zip(images, reviews):
        path = checked_path(workspace, str(render_path.parent / image['file']))
        if digest(path) != image['sha256'] or review['png_sha256'] != image['sha256'] or not review.get('inspection'):
            raise ValueError('Changed or unreviewed rendered page')
        paths.add(str(path.relative_to(workspace)))
    return paths


def validate_claim_declaration(workspace, declaration, metadata):
    paths = declaration['claim_ledgers']
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Declare every current claim ledger exactly once')
    required = {str(p.relative_to(workspace)) for p in (workspace/'paper').glob('claim_evidence*.json')}
    if not required.issubset(paths):
        raise ValueError('A current manuscript claim ledger was omitted')
    extension = declaration['extension_claim_ledger']
    if extension not in paths:
        raise ValueError('The integrated extension ledger must be included')
    hashes = {name: digest(checked_path(workspace, name)) for name in paths}
    if metadata.get('review_claim_ledgers_sha256') != hashes:
        raise ValueError('Metadata does not bind all current claim ledgers')
    counts = {}
    for name in paths:
        ledger = json.loads(checked_path(workspace, name).read_text())
        verify_claim_ledger(workspace, ledger)
        counts[name] = len(ledger['claims'])
        if name == extension and not any(c['source_path'].startswith('runs/producing_extension_v1/analysis/') for c in ledger['claims']):
            raise ValueError('Extension ledger lacks extension result sources')
    return hashes, counts


def preflight(workspace, declaration):
    workspace = Path(workspace).resolve()
    if declaration.get('purpose') != 'local author review; not submitted':
        raise ValueError('Only local author-review bundle assembly is supported')
    expected_runs = ['runs/final_2017_v4', 'runs/producing_extension_v1']
    if [row['run'] for row in declaration['runs']] != expected_runs:
        raise ValueError('Both original and extension experiments are required')
    for row in declaration['runs']:
        checked_evidence(workspace/row['run'], workspace/row['reproduced'])
    pdf = checked_path(workspace, declaration['pdf']); pdf_hash = digest(pdf)
    audit = json.loads(checked_path(workspace, declaration['mechanical_audit']).read_text())
    visual = json.loads(checked_path(workspace, declaration['visual_audit']).read_text())
    if audit['pdf_sha256'] != pdf_hash or visual['pdf_sha256'] != pdf_hash:
        raise ValueError('PDF audit/visual evidence describes another build')
    if audit['pages'] > 7 or not audit['all_fonts_embedded'] or audit['draft_marker_count'] or audit['identity_pattern_hits'] or audit['metadata'].get('/Author'):
        raise ValueError('Current PDF fails the declared seven-page anonymous mechanical checks')
    if not visual.get('page_evidence') or len(visual['page_evidence']) != audit['pages'] or 'visually inspected' not in visual.get('status', ''):
        raise ValueError('Every current PDF page needs visual-review evidence')
    visual_paths = validate_visual_evidence(workspace, declaration, audit, visual)
    metadata = json.loads(checked_path(workspace, declaration['metadata']).read_text())
    if metadata.get('pdf_sha256') != pdf_hash:
        raise ValueError('Submission metadata describes another PDF')
    for name, expected in metadata['source_files_sha256'].items():
        if digest(checked_path(workspace, name)) != expected:
            raise ValueError('Manuscript source changed after review: '+name)
    integration = metadata.get('extension_evidence', {})
    if integration.get('status') != 'incorporated from verified and reproduced results' or integration.get('run_manifest_sha256') != digest(workspace/expected_runs[1]/'manifest.json'):
        raise ValueError('Extension manuscript integration has not been recorded against completed evidence')
    claim_hashes, claim_counts = validate_claim_declaration(workspace, declaration, metadata)
    anon = anonymous_metadata(metadata, pdf_hash)
    return {'pdf_sha256': pdf_hash, 'pages': audit['pages'], 'claim_ledgers_sha256': claim_hashes,
        'claim_counts': claim_counts, 'anonymous_metadata': anon, 'visual_evidence_paths': sorted(visual_paths)}


def package(declaration_path, output):
    workspace = Path.cwd().resolve(); declaration_path = checked_path(workspace, declaration_path)
    output = Path(output).resolve()
    if not output.is_relative_to(workspace) or output.exists():
        raise ValueError('Use a fresh local package directory inside the workspace')
    declaration = json.loads(declaration_path.read_text())
    result = preflight(workspace, declaration)
    # Explicitly verify the public extension view before claiming public closure.
    verification_protocol('configs/producing_extension_v1.json', 'research/PRODUCING_EXTENSION_LOCK_V1.json', PUBLIC)
    public = set(revised_candidate_files(workspace, 'runs/final_2017_v4', 'runs/producing_extension_v1'))
    for row in declaration['runs']:
        folder = workspace/row['reproduced']
        public.update(str(p.relative_to(workspace)) for p in folder.rglob('*') if p.is_file() and p.suffix != '.log')
    public.update(declaration['claim_ledgers'])
    for path in declaration['claim_ledgers']:
        public.update(c['source_path'] for c in json.loads((workspace/path).read_text())['claims'])
    public.update({str(declaration_path.relative_to(workspace)), declaration['metadata'], declaration['mechanical_audit'], declaration['visual_audit']})
    public.update(result['visual_evidence_paths'])
    private = public | {PRIVATE_PRD, 'research/CCWC_Research_Assessment.md'}
    if digest(workspace/PRIVATE_PRD) != PRIVATE_PRD_SHA256:
        raise ValueError('Original PRD changed')
    snapshot = {p: digest(checked_path(workspace, p)) for p in sorted(private)}
    output.mkdir(parents=True)
    staging = output/'anonymous_candidate'; staging.mkdir()
    shutil.copyfile(workspace/declaration['pdf'], staging/'manuscript.pdf')
    (staging/'metadata.json').write_text(json.dumps(result['anonymous_metadata'], indent=2)+'\n')
    shutil.copyfile(workspace/'paper/REVIEW_BUNDLE_README.md', staging/'README.md')
    archives = [write_archive(output/'ccwc_anonymous_manuscript.zip', staging,
        ['manuscript.pdf', 'metadata.json', 'README.md'], 'Current anonymous local review bundle; human approval pending'),
        write_archive(output/'ccwc_private_research.zip', workspace, private,
        'Current private research review bundle; original PRD retained; not an anonymous upload')]
    for name, expected in snapshot.items():
        if digest(workspace/name) != expected:
            raise ValueError('Source changed during archive assembly: '+name)
    record = {**result, 'status': 'current local review bundles built and reopened',
        'assembled_at_utc': datetime.now(timezone.utc).isoformat(), 'declaration_sha256': digest(declaration_path),
        'packer_sha256': digest(Path(__file__)), 'archives': archives, 'public_candidate_paths': sorted(public),
        'source_snapshot_sha256': snapshot, 'public_archive_status': 'not assembled or tested by this command',
        'external_actions': 'None; no upload, contact, payment, publication or submission',
        'human_gates': 'Scientific review, authorship/order/consent, originality, second-contributor reproduction, disclosure placement and code-license decisions remain separate'}
    (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    print('Current local manuscript/private bundles built and reopened; public candidate remains a separate check')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declaration', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); package(args.declaration, args.output)
