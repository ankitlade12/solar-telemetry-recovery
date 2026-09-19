"""Public analysis context wiring, with an explicitly synthetic protocol stub."""
import json

import pytest

from research import verify_public_extension as module


def test_public_context_requires_finished_run_and_records_protocol_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path/'run';root.mkdir()
    manifest = root/'manifest.json'
    manifest.write_text(json.dumps({'status': 'running frozen evaluation'}))
    with pytest.raises(ValueError, match='completed public reproduction'):
        module.prepare_public_context(root, 'synthetic-view.json')
    manifest.write_text(json.dumps({'status': 'complete frozen evaluation'}))
    (tmp_path/'research').mkdir()
    for name in ['verify_public_extension.py', 'extension_release_protocol.py',
                 'reproduce_public_extension.py', 'analyze_producing_extension.py']:
        (tmp_path/'research'/name).write_text('# synthetic source fixture\n')
    calls = []
    def protocol(*args):
        calls.append(args)
        return {}, {'scientific_dependencies_verified': 138, 'fixture_only': True}
    monkeypatch.setattr(module, 'verification_protocol', protocol)
    module.prepare_public_context(root, 'synthetic-view.json')
    assert calls == [(root/'config.json', root/'protocol_lock.json', 'synthetic-view.json')]
    context = json.loads((root/'extension_context.json').read_text())
    assert context['extension_dependencies_verified'] == 138
    assert context['public_protocol_provenance']['fixture_only']
    assert len(context['source_sha256']) == 4
    assert len(list((root/'extension_source/research').glob('*.py'))) == 4
    with pytest.raises(FileExistsError):
        module.prepare_public_context(root, 'synthetic-view.json')
