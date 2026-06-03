from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field


@dataclass
class Commit:
    hash: str = ""
    tree_hash: str = ""
    parents: list[str] = field(default_factory=list)
    author: str = ""
    timestamp: float = 0.0
    message: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def short_hash(self) -> str:
        return self.hash[:8] if self.hash else self.tree_hash[:8]

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "tree_hash": self.tree_hash,
            "parents": self.parents,
            "author": self.author,
            "timestamp": self.timestamp,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Commit:
        return cls(
            hash=data.get("hash", ""),
            tree_hash=data["tree_hash"],
            parents=data.get("parents", []),
            author=data.get("author", ""),
            timestamp=data.get("timestamp", 0.0),
            message=data.get("message", ""),
            metadata=data.get("metadata", {}),
        )

    def serialize(self) -> bytes:
        return json.dumps(self.to_dict(), indent=2).encode()

    @classmethod
    def deserialize(cls, data: bytes) -> Commit:
        return cls.from_dict(json.loads(data))


def make_commit(
    tree_hash: str,
    parents: list[str] | None = None,
    message: str = "",
    author: str | None = None,
    timestamp: float | None = None,
    metadata: dict[str, str] | None = None,
) -> Commit:
    if author is None:
        author = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    if timestamp is None:
        timestamp = time.time()
    return Commit(
        hash="",
        tree_hash=tree_hash,
        parents=parents or [],
        author=author,
        timestamp=timestamp,
        message=message,
        metadata=metadata or {},
    )
