from __future__ import annotations

from dataclasses import dataclass, field

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import preorder
from ..ir.types import BlockType, InlineType, NodeType


@dataclass
class IndexSet:
    section_index: dict[str, list[int]] = field(default_factory=dict)
    link_index: dict[str, list[int]] = field(default_factory=dict)
    term_index: dict[str, set[int]] = field(default_factory=dict)
    type_index: dict[NodeType, list[int]] = field(default_factory=dict)
    level_index: dict[int, list[int]] = field(default_factory=dict)


def build_index(store: DocumentStore) -> IndexSet:
    idx = IndexSet()

    for eid in preorder(store):
        ntype = store.node_type[eid]

        idx.type_index.setdefault(ntype, []).append(eid)

        if ntype == BlockType.SECTION:
            level = store.block_level.get(eid, 0)
            idx.level_index.setdefault(level, []).append(eid)
            text = _collect_text(store, eid)
            if text:
                idx.section_index.setdefault(text, []).append(eid)

        if ntype == InlineType.LINK:
            url = store.inline_url.get(eid, _NONE)
            if url >= 0:
                idx.link_index.setdefault(store.text(url), []).append(eid)

        if ntype == InlineType.TEXT:
            t = store.inline_text.get(eid, _NONE)
            if t >= 0:
                _add_terms(idx.term_index, store.text(t), eid)

    return idx


def _collect_text(store: DocumentStore, eid: int) -> str:
    parts = []
    for cid in preorder(store, eid):
        if store.node_type[cid] == InlineType.TEXT:
            t = store.inline_text.get(cid, _NONE)
            if t >= 0:
                parts.append(store.text(t))
    return " ".join(parts)


def _add_terms(index: dict[str, set[int]], text: str, eid: int) -> None:
    for word in text.split():
        word = word.strip(".,;:!?\"'()[]{}")
        if word:
            index.setdefault(word, set()).add(eid)
