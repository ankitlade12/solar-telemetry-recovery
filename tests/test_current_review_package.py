"""Review-boundary tests; these do not simulate completed scientific results."""
import json
from pathlib import Path

import pytest

from research.package_current_review import anonymous_metadata, validate_claim_declaration, validate_visual_evidence
from solar_recovery.pilot import digest


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_two_anonymous_human_authors_exclude_private_metadata():
    source = {'title': 'Synthetic review', 'abstract': 'Synthetic abstract',
              'anonymous_author_labels': ['Author 1', 'Author 2'],
              'real_author_details': [{'name': 'Private Name', 'email': 'private@example.org'}],
              'author_consent_confirmed': False, 'working_arrangement': 'Private workflow'}
    result = anonymous_metadata(source, 'pdf hash')
    assert result['anonymous_author_labels'] == ['Author 1', 'Author 2']
    assert 'Private' not in json.dumps(result)
    assert 'author_consent_confirmed' not in result
    for labels in [['Author 1'], ['Author 1', 'Author 1'], ['Author 1', 'Private Name']]:
        with pytest.raises(ValueError, match='placeholder'):
            anonymous_metadata({**source, 'anonymous_author_labels': labels}, 'pdf hash')


def test_visual_review_binds_every_image_to_current_pdf(tmp_path):
    folder = tmp_path/'paper/render'; folder.mkdir(parents=True)
    images = []
    for page in (1, 2):
        path = folder/f'page_{page}.png'; path.write_bytes(f'synthetic page {page}'.encode())
        images.append({'page': page, 'file': path.name, 'sha256': digest(path)})
    manifest = folder/'manifest.json'
    write_json(manifest, {'pdf_sha256': 'current pdf', 'pages': images})
    declaration = {'render_manifest': 'paper/render/manifest.json'}
    audit = {'pages': 2, 'pdf_sha256': 'current pdf'}
    visual = {'pages': 2, 'render_manifest_sha256': digest(manifest), 'page_evidence': [
        {'page': row['page'], 'png_sha256': row['sha256'], 'inspection': 'Synthetic fixture'} for row in images]}
    assert validate_visual_evidence(tmp_path, declaration, audit, visual) == {
        'paper/render/manifest.json', 'paper/render/page_1.png', 'paper/render/page_2.png'}
    duplicate = {**visual, 'page_evidence': [visual['page_evidence'][0]] * 2}
    with pytest.raises(ValueError, match='exactly once'):
        validate_visual_evidence(tmp_path, declaration, audit, duplicate)
    with pytest.raises(ValueError, match='current PDF rendering'):
        validate_visual_evidence(tmp_path, declaration, {**audit, 'pdf_sha256': 'new pdf'}, visual)
    (folder/'page_2.png').write_bytes(b'changed after review')
    with pytest.raises(ValueError, match='Changed or unreviewed'):
        validate_visual_evidence(tmp_path, declaration, audit, visual)


def test_claim_declaration_rejects_omitted_or_changed_measured_evidence(tmp_path):
    paths = ['paper/claim_evidence.json', 'paper/claim_evidence_posthoc.json', 'paper/extension/claim_evidence_extension.json']
    for i, name in enumerate(paths):
        csv = ('runs/producing_extension_v1/analysis/result.csv' if i == 2 else f'research/result_{i}.csv')
        source = tmp_path/csv; source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('site,value\nsynthetic,12\n')
        write_json(tmp_path/name, {'status': 'reviewed against cited artifacts', 'claims': [{
            'id': f'fixture-{i}', 'statement': 'Synthetic fixture value', 'source_path': csv,
            'source_sha256': digest(source), 'where': {'site': 'synthetic'}, 'values': {'value': 12}}]})
    metadata = {'review_claim_ledgers_sha256': {name: digest(tmp_path/name) for name in paths}}
    declaration = {'claim_ledgers': paths, 'extension_claim_ledger': paths[2]}
    hashes, counts = validate_claim_declaration(tmp_path, declaration, metadata)
    assert hashes == metadata['review_claim_ledgers_sha256']
    assert list(counts.values()) == [1, 1, 1]
    with pytest.raises(ValueError, match='omitted'):
        validate_claim_declaration(tmp_path, {**declaration, 'claim_ledgers': [paths[0], paths[2]]}, metadata)
    with pytest.raises(ValueError, match='exactly once'):
        validate_claim_declaration(tmp_path, {**declaration, 'claim_ledgers': paths + [paths[0]]}, metadata)
    (tmp_path/'runs/producing_extension_v1/analysis/result.csv').write_text('site,value\nsynthetic,13\n')
    with pytest.raises(ValueError, match='Changed claim source'):
        validate_claim_declaration(tmp_path, declaration, metadata)
