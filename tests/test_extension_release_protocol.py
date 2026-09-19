import copy
import json
from pathlib import Path

import pytest

from research.extension_release_protocol import (
    EXTENSION_LOCK_SHA256, NATURE, PARENT, validate_public_view,
)
from research.release_protocol import ORIGINAL_LOCK_SHA256, PRIVATE_PRD, PRIVATE_PRD_SHA256


def public_fixture():
    parent = json.loads(PARENT.read_text())
    view = copy.deepcopy(parent)
    view['files_sha256'].pop(PRIVATE_PRD)
    view['nature'] = NATURE
    view['performance_exposure'] = 'Derived reproduction view, not a new freeze'
    view['public_extension_derivation'] = {'parent_path': str(PARENT), 'parent_sha256': EXTENSION_LOCK_SHA256,
        'original_parent_sha256': ORIGINAL_LOCK_SHA256, 'omitted_private_files': {PRIVATE_PRD: PRIVATE_PRD_SHA256}}
    return parent, view


def test_exact_public_view_preserves_all_scientific_dependencies():
    parent, view = public_fixture()
    validate_public_view(view, parent)
    assert len(parent['files_sha256']) == 139 and len(view['files_sha256']) == 138


@pytest.mark.parametrize('change', ['drop', 'hash', 'environment', 'config', 'parent', 'claim', 'extra'])
def test_public_view_cannot_relax_frozen_contract(change):
    parent, view = public_fixture()
    if change == 'drop': view['files_sha256'].pop(next(iter(view['files_sha256'])))
    if change == 'hash': view['files_sha256'][next(iter(view['files_sha256']))] = 'changed'
    if change == 'environment': view['environment']['numpy'] = 'changed'
    if change == 'config': view['config_sha256'] = 'changed'
    if change == 'parent': view['public_extension_derivation']['parent_sha256'] = 'changed'
    if change == 'claim': view['nature'] = 'prospective untouched evaluation'
    if change == 'extra': view['ignore_missing_inputs'] = True
    with pytest.raises(ValueError):
        validate_public_view(view, parent)
