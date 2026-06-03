from __future__ import annotations

import re
from typing import Callable

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import preorder
from ..ir.types import BlockType, InlineType, NodeType
from ..ops import build_index
from .commit import Commit
from .repo import Repository


class LogQuery:
    def __init__(self, repo: Repository):
        self.repo = repo

    def all(self, branch: str | None = None, limit: int | None = None) -> list[Commit]:
        return self.repo.log(branch=branch, limit=limit)

    def since(self, timestamp: float, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        return [c for c in commits if c.timestamp >= timestamp]

    def by_author(self, author: str, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        return [c for c in commits if c.author == author]

    def by_message(self, pattern: str, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        regex = re.compile(pattern, re.IGNORECASE)
        return [c for c in commits if regex.search(c.message)]

    def affecting_type(self, node_type: NodeType, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        result = []
        for commit in commits:
            try:
                store = self.repo.get_store(commit.tree_hash)
                for eid in preorder(store):
                    if store.node_type[eid] == node_type:
                        result.append(commit)
                        break
            except KeyError:
                pass
        return result

    def affecting_section(self, section_title: str, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        result = []
        for commit in commits:
            try:
                store = self.repo.get_store(commit.tree_hash)
                for eid in preorder(store):
                    if store.node_type[eid] == BlockType.SECTION:
                        text = _collect_text(store, eid)
                        if section_title.lower() in text.lower():
                            result.append(commit)
                            break
            except KeyError:
                pass
        return result

    def affecting_link(self, url_pattern: str, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        regex = re.compile(url_pattern, re.IGNORECASE)
        result = []
        for commit in commits:
            try:
                store = self.repo.get_store(commit.tree_hash)
                for eid in preorder(store):
                    if store.node_type[eid] == InlineType.LINK:
                        url_idx = store.inline_url.get(eid, _NONE)
                        if url_idx >= 0:
                            url = store.text(url_idx)
                            if regex.search(url):
                                result.append(commit)
                                break
            except KeyError:
                pass
        return result

    def affecting_code(self, language: str | None = None, branch: str | None = None) -> list[Commit]:
        commits = self.repo.log(branch=branch)
        result = []
        for commit in commits:
            try:
                store = self.repo.get_store(commit.tree_hash)
                for eid in preorder(store):
                    if store.node_type[eid] == BlockType.CODE_BLOCK:
                        if language is None:
                            result.append(commit)
                            break
                        lang_idx = store.block_language.get(eid, _NONE)
                        if lang_idx >= 0:
                            lang = store.text(lang_idx)
                            if lang.lower() == language.lower():
                                result.append(commit)
                                break
            except KeyError:
                pass
        return result


def _collect_text(store: DocumentStore, eid: int) -> str:
    parts = []
    for cid in preorder(store, eid):
        if store.node_type[cid] == InlineType.TEXT:
            t = store.inline_text.get(cid, _NONE)
            if t >= 0:
                parts.append(store.text(t))
    return " ".join(parts)
