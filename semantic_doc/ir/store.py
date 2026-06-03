from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .types import (
    AdmonType,
    BlockType,
    InlineType,
    ListType,
    NodeType,
    PrivacyLevel,
)

_NONE = -1


@dataclass(slots=True)
class DocumentStore:
    # String pool
    strings: list[str] = field(default_factory=list)

    # Common node arrays (indexed by entity ID)
    node_type: list[NodeType] = field(default_factory=list)
    node_parent: list[int] = field(default_factory=list)
    node_prev: list[int] = field(default_factory=list)
    node_next: list[int] = field(default_factory=list)
    node_first_child: list[int] = field(default_factory=list)

    # Block component stores (sparse, keyed by entity ID)
    block_level: dict[int, int] = field(default_factory=dict)
    block_language: dict[int, int] = field(default_factory=dict)
    block_content: dict[int, int] = field(default_factory=dict)
    block_list_type: dict[int, ListType] = field(default_factory=dict)
    block_admon_type: dict[int, AdmonType] = field(default_factory=dict)
    block_checked: dict[int, bool] = field(default_factory=dict)
    block_privacy: dict[int, PrivacyLevel] = field(default_factory=dict)

    # Inline component stores (sparse)
    inline_text: dict[int, int] = field(default_factory=dict)
    inline_url: dict[int, int] = field(default_factory=dict)
    inline_title: dict[int, int] = field(default_factory=dict)

    # Root
    root_first: int = _NONE

    # Metadata
    meta_title: int = _NONE
    meta_attrs: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        assert len(self.node_type) == len(self.node_parent)
        assert len(self.node_type) == len(self.node_prev)
        assert len(self.node_type) == len(self.node_next)
        assert len(self.node_type) == len(self.node_first_child)

    @property
    def entity_count(self) -> int:
        return len(self.node_type)

    def intern(self, s: str) -> int:
        if s not in self.strings:
            self.strings.append(s)
        return self.strings.index(s)

    def text(self, idx: int) -> str:
        return self.strings[idx] if idx >= 0 else ""

    def alloc_node(self, node_type: NodeType, parent: int | None = None) -> int:
        eid = self.entity_count
        self.node_type.append(node_type)
        self.node_parent.append(parent if parent is not None else _NONE)
        self.node_prev.append(_NONE)
        self.node_next.append(_NONE)
        self.node_first_child.append(_NONE)

        if parent is not None:
            last = self._last_child_of(parent)
            if last == _NONE:
                self.node_first_child[parent] = eid
            else:
                self.node_next[last] = eid
                self.node_prev[eid] = last

        return eid

    def insert_after(self, node_type: NodeType, after_eid: int) -> int:
        """Insert a new node after the specified node."""
        eid = self.entity_count
        self.node_type.append(node_type)
        self.node_parent.append(self.node_parent[after_eid])
        self.node_prev.append(after_eid)
        self.node_next.append(self.node_next[after_eid])
        self.node_first_child.append(_NONE)

        # Update the next pointer of the after node
        self.node_next[after_eid] = eid

        # Update the prev pointer of the old next node (if any)
        old_next = self.node_next[eid]
        if old_next != _NONE:
            self.node_prev[old_next] = eid

        return eid

    def _last_child_of(self, parent: int) -> int:
        first = self.node_first_child[parent]
        if first == _NONE:
            return _NONE
        cur = first
        while self.node_next[cur] != _NONE:
            cur = self.node_next[cur]
        return cur

    def children(self, parent: int) -> list[int]:
        result = []
        cur = self.node_first_child[parent]
        while cur != _NONE:
            result.append(cur)
            cur = self.node_next[cur]
        return result

    def siblings(self, eid: int) -> list[int]:
        result = []
        cur = self._first_sibling(eid)
        while cur != _NONE:
            result.append(cur)
            cur = self.node_next[cur]
        return result

    def _first_sibling(self, eid: int) -> int:
        cur = eid
        while self.node_prev[cur] != _NONE:
            cur = self.node_prev[cur]
        return cur

    def root_children(self) -> list[int]:
        return self.children_of(_NONE) if False else self._root_children()

    def _root_children(self) -> list[int]:
        result = []
        cur = self.root_first
        while cur != _NONE:
            result.append(cur)
            cur = self.node_next[cur]
        return result

    def children_of(self, parent: int | None) -> list[int]:
        if parent is None:
            return self._root_children()
        return self.children(parent)

    def set_component(self, eid: int, name: str, value: Any) -> None:
        store = getattr(self, name)
        if isinstance(store, dict):
            store[eid] = value

    def get_component(self, eid: int, name: str, default: Any = None) -> Any:
        if not hasattr(self, name):
            return default
        store = getattr(self, name)
        if isinstance(store, dict):
            return store.get(eid, default)
        return default

    def clone(self) -> DocumentStore:
        return DocumentStore(
            strings=list(self.strings),
            node_type=list(self.node_type),
            node_parent=list(self.node_parent),
            node_prev=list(self.node_prev),
            node_next=list(self.node_next),
            node_first_child=list(self.node_first_child),
            block_level=dict(self.block_level),
            block_language=dict(self.block_language),
            block_content=dict(self.block_content),
            block_list_type=dict(self.block_list_type),
            block_admon_type=dict(self.block_admon_type),
            block_checked=dict(self.block_checked),
            block_privacy=dict(self.block_privacy),
            inline_text=dict(self.inline_text),
            inline_url=dict(self.inline_url),
            inline_title=dict(self.inline_title),
            root_first=self.root_first,
            meta_title=self.meta_title,
            meta_attrs=dict(self.meta_attrs),
        )

    def _alloc_root_node(self, node_type: NodeType) -> int:
        eid = self.entity_count
        self.node_type.append(node_type)
        self.node_parent.append(_NONE)
        self.node_prev.append(_NONE)
        self.node_next.append(_NONE)
        self.node_first_child.append(_NONE)

        if self.root_first == _NONE:
            self.root_first = eid
        else:
            last = self._last_root_child()
            self.node_next[last] = eid
            self.node_prev[eid] = last

        return eid

    def _last_root_child(self) -> int:
        cur = self.root_first
        if cur == _NONE:
            return _NONE
        while self.node_next[cur] != _NONE:
            cur = self.node_next[cur]
        return cur


def new_store() -> DocumentStore:
    return DocumentStore()
