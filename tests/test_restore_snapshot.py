import hashlib
import json

import pytest

from research.restore_snapshot import restore, restore_object


class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def raise_for_status(self):
        pass
    def iter_content(self, size):
        yield self.payload


def test_manifest_restore_preserves_exact_bytes_and_reuses_valid_cache(tmp_path, monkeypatch):
    payload = b"explicit synthetic source object\n"
    item = {"key": "pvdaq/test/example.bin", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = tmp_path/"original.json"
    content = json.dumps({"dataset": "PVDAQ", "files": [item]}, indent=3).encode()+b"\n"
    manifest.write_bytes(content)
    monkeypatch.setattr("research.restore_snapshot.requests.get", lambda *args, **kwargs: Response(payload))
    out = tmp_path/"restored"
    first = restore(manifest, out, max_mb=1, workers=1)
    assert (out/"manifest.json").read_bytes() == content
    assert (out/"example.bin").read_bytes() == payload
    assert first["downloaded_bytes"] == len(payload)
    monkeypatch.setattr("research.restore_snapshot.requests.get", lambda *a, **k: pytest.fail("Valid cache must not download"))
    assert restore(manifest, out, max_mb=1, workers=1)["downloaded_bytes"] == 0


def test_changed_public_bytes_are_rejected_before_publication(tmp_path, monkeypatch):
    item = {"key": "pvdaq/test/example.bin", "bytes": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
    monkeypatch.setattr("research.restore_snapshot.requests.get", lambda *args, **kwargs: Response(b"evil"))
    with pytest.raises(ValueError, match="no longer matches"):
        restore_object(item, tmp_path)
    assert not (tmp_path/"example.bin").exists()


def test_restore_budget_fails_before_network(tmp_path, monkeypatch):
    manifest = tmp_path/"manifest.json"
    manifest.write_text(json.dumps({"dataset": "PVDAQ", "files": [{"key": "pvdaq/test/big.bin", "bytes": 2000000, "sha256": "unused"}]}))
    monkeypatch.setattr("research.restore_snapshot.requests.get", lambda *a, **k: pytest.fail("Budget must be checked first"))
    with pytest.raises(ValueError, match="above the explicit budget"):
        restore(manifest, max_mb=1)
