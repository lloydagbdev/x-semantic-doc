from __future__ import annotations

import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

from ..ir.store import DocumentStore
from ..serializers import from_dict, to_dict
from .commit import Commit


def _hash_object(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ObjectStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)

    def _obj_path(self, obj_hash: str) -> Path:
        return self.path / obj_hash[:2] / obj_hash[2:]

    def put(self, data: bytes) -> str:
        obj_hash = _hash_object(data)
        p = self._obj_path(obj_hash)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(zlib.compress(data))
        return obj_hash

    def get(self, obj_hash: str) -> bytes:
        p = self._obj_path(obj_hash)
        if not p.exists():
            raise KeyError(f"Object {obj_hash[:8]} not found")
        return zlib.decompress(p.read_bytes())

    def has(self, obj_hash: str) -> bool:
        return self._obj_path(obj_hash).exists()

    def put_store(self, store: DocumentStore) -> str:
        data = json.dumps(to_dict(store)).encode()
        return self.put(data)

    def get_store(self, obj_hash: str) -> DocumentStore:
        data = self.get(obj_hash)
        return from_dict(json.loads(data))

    def put_commit(self, commit: Commit) -> str:
        obj_hash = self.put(commit.serialize())
        commit.hash = obj_hash
        return obj_hash

    def get_commit(self, obj_hash: str) -> Commit:
        commit = Commit.deserialize(self.get(obj_hash))
        commit.hash = obj_hash
        return commit
