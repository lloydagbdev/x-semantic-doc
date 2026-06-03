from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ..ir.store import DocumentStore
from ..ops import HashPolicy, compute_hashes
from .commit import Commit, make_commit
from .store import ObjectStore

SEMANTIC_DIR = ".semantic"
OBJECTS_DIR = "objects"
REFS_DIR = "refs"
HEADS_DIR = "heads"
TAGS_DIR = "tags"
INDEX_FILE = "index"
CONFIG_FILE = "config"
HEAD_FILE = "HEAD"


def _read_ref(refs_path: Path) -> str | None:
    if refs_path.exists():
        return refs_path.read_text().strip()
    return None


def _write_ref(refs_path: Path, value: str) -> None:
    refs_path.parent.mkdir(parents=True, exist_ok=True)
    refs_path.write_text(value)


def _delete_ref(refs_path: Path) -> None:
    if refs_path.exists():
        refs_path.unlink()


class Repository:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or ".")
        self.semantic = self.path / SEMANTIC_DIR
        self.objects_path = self.semantic / OBJECTS_DIR
        self.refs_path = self.semantic / REFS_DIR
        self.heads_path = self.refs_path / HEADS_DIR
        self.tags_path = self.refs_path / TAGS_DIR
        self.index_file = self.semantic / INDEX_FILE
        self.config_file = self.semantic / CONFIG_FILE
        self.head_file = self.semantic / HEAD_FILE
        self.objects = ObjectStore(self.objects_path)

    @classmethod
    def init(cls, path: Path | str | None = None) -> Repository:
        repo = cls(path)
        repo.semantic.mkdir(exist_ok=True)
        repo.objects_path.mkdir(exist_ok=True)
        repo.heads_path.mkdir(parents=True, exist_ok=True)
        repo.tags_path.mkdir(parents=True, exist_ok=True)
        if not repo.head_file.exists():
            repo.head_file.write_text("main")
        if not repo.config_file.exists():
            config = {"version": 1, "privacy_default": "public"}
            repo.config_file.write_text(json.dumps(config, indent=2))
        if not repo.index_file.exists():
            repo.index_file.write_text(json.dumps({"tree_hash": None}))
        return repo

    @classmethod
    def open(cls, path: Path | str | None = None) -> Repository:
        repo = cls(path)
        if not repo.semantic.exists():
            raise ValueError(f"Not a semantic-doc repository: {repo.semantic}")
        return repo

    @property
    def head_ref(self) -> str:
        if self.head_file.exists():
            return self.head_file.read_text().strip()
        return "main"

    @property
    def head_commit_hash(self) -> str | None:
        ref = self.head_ref
        ref_path = self.heads_path / ref
        return _read_ref(ref_path)

    def get_commit(self, commit_hash: str) -> Commit:
        return self.objects.get_commit(commit_hash)

    def get_store(self, tree_hash: str) -> DocumentStore:
        return self.objects.get_store(tree_hash)

    def commit(self, store: DocumentStore, message: str, author: str | None = None) -> Commit:
        tree_hash = self.objects.put_store(store)
        parent_hash = self.head_commit_hash
        parents = [parent_hash] if parent_hash else []
        commit = make_commit(
            tree_hash=tree_hash,
            parents=parents,
            message=message,
            author=author,
        )
        commit_hash = self.objects.put_commit(commit)
        _write_ref(self.heads_path / self.head_ref, commit_hash)
        self.index_file.write_text(json.dumps({"tree_hash": tree_hash, "commit_hash": commit_hash}))
        return commit

    def checkout(self, target: str) -> DocumentStore:
        ref_path = self.heads_path / target
        commit_hash = _read_ref(ref_path)
        if commit_hash is None:
            if len(target) >= 8:
                for d in self.heads_path.iterdir():
                    ref_val = _read_ref(d)
                    if ref_val and ref_val.startswith(target):
                        commit_hash = ref_val
                        break
        if commit_hash is None:
            commit_hash = target
        if not self.objects.has(commit_hash):
            commit_hash = self._resolve_commit(target)
        if commit_hash is None:
            raise ValueError(f"Cannot resolve: {target}")
        commit = self.objects.get_commit(commit_hash)
        store = self.objects.get_store(commit.tree_hash)
        self.index_file.write_text(json.dumps({"tree_hash": commit.tree_hash}))
        return store

    def _resolve_commit(self, target: str) -> str | None:
        for d in self.heads_path.iterdir():
            ref_val = _read_ref(d)
            if ref_val and ref_val.startswith(target):
                return ref_val
        for d in self.tags_path.iterdir():
            ref_val = _read_ref(d)
            if ref_val and ref_val.startswith(target):
                return ref_val
        for d in self.heads_path.iterdir():
            ref_val = _read_ref(d)
            if ref_val:
                result = self._find_commit_in_history(ref_val, target)
                if result:
                    return result
        if self.objects.has(target):
            try:
                self.objects.get_commit(target)
                return target
            except Exception:
                pass
        return None

    def _find_commit_in_history(self, start_hash: str, target: str) -> str | None:
        visited = set()
        queue = [start_hash]
        while queue:
            h = queue.pop(0)
            if h in visited:
                continue
            visited.add(h)
            if h.startswith(target):
                return h
            try:
                commit = self.objects.get_commit(h)
                queue.extend(commit.parents)
            except KeyError:
                pass
        return None

    def switch_branch(self, branch: str) -> None:
        ref_path = self.heads_path / branch
        if not ref_path.exists():
            raise ValueError(f"Branch '{branch}' does not exist")
        self.head_file.write_text(branch)
        ref_val = _read_ref(ref_path)
        if ref_val:
            commit = self.objects.get_commit(ref_val)
            self.index_file.write_text(json.dumps({"tree_hash": commit.tree_hash}))

    def create_branch(self, name: str, start_from: str | None = None) -> None:
        ref_path = self.heads_path / name
        if ref_path.exists():
            raise ValueError(f"Branch '{name}' already exists")
        if start_from:
            commit_hash = self._resolve_commit(start_from)
            if commit_hash is None:
                raise ValueError(f"Cannot resolve: {start_from}")
            _write_ref(ref_path, commit_hash)
        else:
            current = self.head_commit_hash
            if current:
                _write_ref(ref_path, current)
            else:
                _write_ref(ref_path, "")

    def delete_branch(self, name: str) -> None:
        if name == self.head_ref:
            raise ValueError("Cannot delete the current branch")
        ref_path = self.heads_path / name
        if not ref_path.exists():
            raise ValueError(f"Branch '{name}' does not exist")
        _delete_ref(ref_path)

    def list_branches(self) -> list[str]:
        branches = []
        if self.heads_path.exists():
            for d in sorted(self.heads_path.iterdir()):
                if d.is_file():
                    branches.append(d.name)
        return branches

    def list_tags(self) -> list[str]:
        tags = []
        if self.tags_path.exists():
            for d in sorted(self.tags_path.iterdir()):
                if d.is_file():
                    tags.append(d.name)
        return tags

    def create_tag(self, name: str, commit_hash: str | None = None) -> None:
        ref_path = self.tags_path / name
        if ref_path.exists():
            raise ValueError(f"Tag '{name}' already exists")
        if commit_hash is None:
            commit_hash = self.head_commit_hash
            if commit_hash is None:
                raise ValueError("No commit to tag")
        _write_ref(ref_path, commit_hash)

    def log(self, branch: str | None = None, limit: int | None = None) -> list[Commit]:
        if branch is None:
            branch = self.head_ref
        ref_path = self.heads_path / branch
        commit_hash = _read_ref(ref_path)
        if commit_hash is None:
            return []
        commits = []
        seen = set()
        while commit_hash and commit_hash not in seen:
            seen.add(commit_hash)
            commit = self.objects.get_commit(commit_hash)
            commits.append(commit)
            if limit and len(commits) >= limit:
                break
            commit_hash = commit.parents[0] if commit.parents else None
        return commits

    def get_current_tree_hash(self) -> str | None:
        if self.index_file.exists():
            data = json.loads(self.index_file.read_text())
            return data.get("tree_hash")
        return None

    def get_current_commit_hash(self) -> str | None:
        if self.index_file.exists():
            data = json.loads(self.index_file.read_text())
            return data.get("commit_hash")
        return None

    def gc(self) -> int:
        reachable = set()
        for d in self.heads_path.iterdir():
            ref_val = _read_ref(d)
            if ref_val:
                self._collect_reachable(ref_val, reachable)
        for d in self.tags_path.iterdir():
            ref_val = _read_ref(d)
            if ref_val:
                self._collect_reachable(ref_val, reachable)
        removed = 0
        if self.objects_path.exists():
            for prefix_dir in self.objects_path.iterdir():
                if prefix_dir.is_dir() and len(prefix_dir.name) == 2:
                    for obj_file in prefix_dir.iterdir():
                        obj_hash = prefix_dir.name + obj_file.name
                        if obj_hash not in reachable:
                            obj_file.unlink()
                            removed += 1
        empty_dirs = [d for d in self.objects_path.iterdir() if d.is_dir() and not any(d.iterdir())]
        for d in empty_dirs:
            d.rmdir()
        return removed

    def _collect_reachable(self, commit_hash: str, reachable: set) -> None:
        if commit_hash in reachable:
            return
        reachable.add(commit_hash)
        try:
            commit = self.objects.get_commit(commit_hash)
            reachable.add(commit.tree_hash)
            for parent in commit.parents:
                self._collect_reachable(parent, reachable)
        except KeyError:
            pass
