"""Public staging must use the exact reviewed, nonprivate artifact selection."""
import json

import pytest

from research.package_current_public import reviewed_selection
from research.release_protocol import PRIVATE_PRD
from solar_recovery.pilot import digest


def fixture(tmp_path):
    artifact = tmp_path/'evidence.csv'; artifact.write_text('synthetic,12\n')
    archive = tmp_path/'review.zip'; archive.write_bytes(b'synthetic archive identity fixture')
    review = {'status': 'current local review bundles built and reopened',
              'archives': [{'file': archive.name, 'sha256': digest(archive)}],
              'public_candidate_paths': [artifact.name],
              'source_snapshot_sha256': {artifact.name: digest(artifact)}}
    path = tmp_path/'review.json'; path.write_text(json.dumps(review))
    return review, path, artifact, archive


def test_reject_changed_review_archive_or_evidence(tmp_path):
    review, path, artifact, archive = fixture(tmp_path)
    assert reviewed_selection(tmp_path, path)[1] == ['evidence.csv']
    artifact.write_text('synthetic,13\n')
    with pytest.raises(ValueError, match='Changed or unreviewed'):
        reviewed_selection(tmp_path, path)
    artifact.write_text('synthetic,12\n')
    archive.write_bytes(b'changed archive')
    with pytest.raises(ValueError, match='Changed review archive'):
        reviewed_selection(tmp_path, path)


@pytest.mark.parametrize('private_name', [PRIVATE_PRD, 'research/sources/copied_paper.pdf'])
def test_private_material_cannot_be_added_even_with_valid_hash(tmp_path, private_name):
    review, path, _, _ = fixture(tmp_path)
    private = tmp_path/private_name; private.parent.mkdir(parents=True, exist_ok=True)
    private.write_bytes(b'synthetic private bytes')
    review['public_candidate_paths'].append(private_name)
    review['source_snapshot_sha256'][private_name] = digest(private)
    path.write_text(json.dumps(review))
    with pytest.raises(ValueError, match='Private material'):
        reviewed_selection(tmp_path, path)
