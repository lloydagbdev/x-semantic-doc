from __future__ import annotations

from dataclasses import dataclass

from ..ir.store import DocumentStore
from ..ir.types import PrivacyLevel
from ..ops import PrivacyMask, StructuralRule, RedactionAction, apply_rules, redact
from .commit import Commit
from .diff import DiffResult, semantic_diff
from .merge import MergeResult, semantic_merge
from .repo import Repository


@dataclass
class PrivacyContext:
    clearance: PrivacyLevel = PrivacyLevel.PUBLIC
    show_redacted: bool = True
    hash_redacted: bool = False


class PrivacyAwareRepo:
    def __init__(self, repo: Repository):
        self.repo = repo

    def commit(self, store: DocumentStore, message: str, ctx: PrivacyContext | None = None, author: str | None = None) -> Commit:
        return self.repo.commit(store, message, author=author)

    def checkout(self, target: str, ctx: PrivacyContext | None = None) -> DocumentStore:
        store = self.repo.checkout(target)
        if ctx is None:
            ctx = PrivacyContext()
        return self._apply_privacy(store, ctx)

    def diff(self, a: str, b: str, ctx: PrivacyContext | None = None) -> DiffResult:
        store_a = self.repo.checkout(a) if a else self.repo.get_store(self.repo.get_current_tree_hash() or "")
        store_b = self.repo.checkout(b) if b else self.repo.get_store(self.repo.get_current_tree_hash() or "")
        if ctx is None:
            ctx = PrivacyContext()
        store_a = self._apply_privacy(store_a, ctx)
        store_b = self._apply_privacy(store_b, ctx)
        return semantic_diff(store_a, store_b)

    def merge(self, branch: str, ctx: PrivacyContext | None = None, strategy: str = "auto") -> MergeResult:
        current_hash = self.repo.head_commit_hash
        if current_hash is None:
            raise ValueError("No commits on current branch")
        branch_hash = self._resolve_branch(branch)
        if branch_hash is None:
            raise ValueError(f"Cannot resolve branch: {branch}")
        base_hash = self._find_common_ancestor(current_hash, branch_hash)
        if base_hash is None:
            raise ValueError("No common ancestor found")
        base = self.repo.get_store(self.repo.get_commit(base_hash).tree_hash)
        ours = self.repo.get_store(self.repo.get_commit(current_hash).tree_hash)
        theirs = self.repo.get_store(self.repo.get_commit(branch_hash).tree_hash)
        if ctx is None:
            ctx = PrivacyContext()
        base = self._apply_privacy(base, ctx)
        ours = self._apply_privacy(ours, ctx)
        theirs = self._apply_privacy(theirs, ctx)
        return semantic_merge(base, ours, theirs, strategy=strategy)

    def log(self, ctx: PrivacyContext | None = None, branch: str | None = None, limit: int | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch, limit=limit)
        if ctx is None:
            ctx = PrivacyContext()
        if ctx.clearance == PrivacyLevel.PUBLIC:
            return [c for c in commits if self._commit_is_public(c)]
        return commits

    def _apply_privacy(self, store: DocumentStore, ctx: PrivacyContext) -> DocumentStore:
        if ctx.clearance == PrivacyLevel.PUBLIC:
            rules = [
                StructuralRule(
                    min_privacy=PrivacyLevel.INTERNAL,
                    action=RedactionAction.REMOVE,
                )
            ]
            mask = apply_rules(store, rules)
            return redact(store, mask)
        elif ctx.clearance == PrivacyLevel.INTERNAL:
            rules = [
                StructuralRule(
                    min_privacy=PrivacyLevel.CONFIDENTIAL,
                    action=RedactionAction.REMOVE,
                )
            ]
            mask = apply_rules(store, rules)
            return redact(store, mask)
        elif ctx.clearance == PrivacyLevel.CONFIDENTIAL:
            rules = [
                StructuralRule(
                    min_privacy=PrivacyLevel.SECRET,
                    action=RedactionAction.REMOVE,
                )
            ]
            mask = apply_rules(store, rules)
            return redact(store, mask)
        return store

    def _resolve_branch(self, branch: str) -> str | None:
        ref_path = self.repo.heads_path / branch
        if ref_path.exists():
            return ref_path.read_text().strip()
        return self.repo._resolve_commit(branch)

    def _find_common_ancestor(self, hash1: str, hash2: str) -> str | None:
        ancestors1 = self._get_ancestors(hash1)
        ancestors2 = self._get_ancestors(hash2)
        for h in ancestors1:
            if h in ancestors2:
                return h
        return None

    def _get_ancestors(self, commit_hash: str) -> set[str]:
        ancestors = set()
        queue = [commit_hash]
        while queue:
            h = queue.pop(0)
            if h in ancestors:
                continue
            ancestors.add(h)
            try:
                commit = self.repo.get_commit(h)
                queue.extend(commit.parents)
            except KeyError:
                pass
        return ancestors

    def _commit_is_public(self, commit: Commit) -> bool:
        try:
            store = self.repo.get_store(commit.tree_hash)
            for eid in store._root_children():
                priv = store.block_privacy.get(eid, PrivacyLevel.PUBLIC)
                if priv != PrivacyLevel.PUBLIC:
                    return False
            return True
        except KeyError:
            return True
