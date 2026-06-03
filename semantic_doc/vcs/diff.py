from __future__ import annotations

from dataclasses import dataclass, field

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import path as get_path, preorder
from ..ir.types import BlockType, InlineType, NodeType
from ..ops import HashPolicy, compute_hashes


def _collect_text(store: DocumentStore, eid: int) -> str:
    parts = []
    for cid in preorder(store, eid):
        if store.node_type[cid] == InlineType.TEXT:
            t = store.inline_text.get(cid, _NONE)
            if t >= 0:
                parts.append(store.text(t))
    return " ".join(parts)


@dataclass
class NodeAdded:
    path: list[int]
    node_type: NodeType
    content: str = ""

    def __str__(self):
        loc = " → ".join(str(p) for p in self.path[-2:]) if len(self.path) > 1 else str(self.path[0])
        return f"+ {self.node_type.value} added at [{loc}]: {self.content[:60]}"


@dataclass
class NodeRemoved:
    path: list[int]
    node_type: NodeType
    content: str = ""

    def __str__(self):
        loc = " → ".join(str(p) for p in self.path[-2:]) if len(self.path) > 1 else str(self.path[0])
        return f"- {self.node_type.value} removed at [{loc}]: {self.content[:60]}"


@dataclass
class NodeModified:
    path: list[int]
    node_type: NodeType
    old_content: str = ""
    new_content: str = ""

    def __str__(self):
        loc = " → ".join(str(p) for p in self.path[-2:]) if len(self.path) > 1 else str(self.path[0])
        return f"~ {self.node_type.value} modified at [{loc}]:\n  - {self.old_content[:60]}\n  + {self.new_content[:60]}"


@dataclass
class NodeMoved:
    old_path: list[int]
    new_path: list[int]
    node_type: NodeType
    content: str = ""

    def __str__(self):
        old = " → ".join(str(p) for p in self.old_path[-2:]) if len(self.old_path) > 1 else str(self.old_path[0])
        new = " → ".join(str(p) for p in self.new_path[-2:]) if len(self.new_path) > 1 else str(self.new_path[0])
        return f"↔ {self.node_type.value} moved [{old}] → [{new}]: {self.content[:60]}"


@dataclass
class NodeRenamed:
    path: list[int]
    node_type: NodeType
    old_title: str = ""
    new_title: str = ""

    def __str__(self):
        loc = " → ".join(str(p) for p in self.path[-2:]) if len(self.path) > 1 else str(self.path[0])
        return f"✎ {self.node_type.value} renamed at [{loc}]: {self.old_title!r} → {self.new_title!r}"


@dataclass
class DiffStats:
    added: int = 0
    removed: int = 0
    modified: int = 0
    moved: int = 0
    renamed: int = 0

    @property
    def total(self):
        return self.added + self.removed + self.modified + self.moved + self.renamed


@dataclass
class DiffResult:
    ops: list = field(default_factory=list)
    stats: DiffStats = field(default_factory=DiffStats)

    @property
    def is_clean(self):
        return len(self.ops) == 0

    def summary(self) -> str:
        if self.is_clean:
            return "No changes."
        lines = []
        for op in self.ops:
            lines.append(str(op))
        lines.append("")
        lines.append(f"{self.stats.added} added, {self.stats.removed} removed, {self.stats.modified} modified, {self.stats.moved} moved, {self.stats.renamed} renamed")
        return "\n".join(lines)


def _build_node_map(store: DocumentStore, hashes: dict[int, bytes]) -> dict[bytes, list[int]]:
    result = {}
    for eid in preorder(store):
        h = hashes.get(eid)
        if h:
            result.setdefault(h, []).append(eid)
    return result


def _match_nodes(old_store: DocumentStore, new_store: DocumentStore, old_hashes: dict[int, bytes], new_hashes: dict[int, bytes]) -> dict[int, int | None]:
    old_map = _build_node_map(old_store, old_hashes)
    new_map = _build_node_map(new_store, new_hashes)
    matched_old = set()
    matched_new = set()
    mapping = {}

    for h, old_eids in old_map.items():
        if h in new_map:
            new_eids = new_map[h]
            for i, old_eid in enumerate(old_eids):
                if i < len(new_eids):
                    mapping[old_eid] = new_eids[i]
                    matched_old.add(old_eid)
                    matched_new.add(new_eids[i])
                else:
                    mapping[old_eid] = None
                    matched_old.add(old_eid)

    for eid in preorder(old_store):
        if eid not in matched_old:
            mapping[eid] = None

    return mapping


def semantic_diff(old_store: DocumentStore, new_store: DocumentStore, policy: HashPolicy | None = None) -> DiffResult:
    if policy is None:
        policy = HashPolicy()

    old_hashes = compute_hashes(old_store, policy)
    new_hashes = compute_hashes(new_store, policy)

    old_content = old_hashes.content_hash
    new_content = new_hashes.content_hash

    old_map = _build_node_map(old_store, old_content)
    new_map = _build_node_map(new_store, new_content)

    matched_old = set()
    matched_new = set()
    mapping = {}

    for h, old_eids in old_map.items():
        if h in new_map:
            new_eids = new_map[h]
            for i, old_eid in enumerate(old_eids):
                if i < len(new_eids):
                    mapping[old_eid] = new_eids[i]
                    matched_old.add(old_eid)
                    matched_new.add(new_eids[i])
                else:
                    mapping[old_eid] = None
                    matched_old.add(old_eid)
        else:
            for old_eid in old_eids:
                mapping[old_eid] = None
                matched_old.add(old_eid)

    for eid in preorder(old_store):
        if eid not in matched_old:
            mapping[eid] = None

    for eid in preorder(new_store):
        found = False
        for old_eid, new_eid in mapping.items():
            if new_eid == eid:
                found = True
                break
        if not found:
            pass

    result = DiffResult()

    old_root_children = old_store._root_children()
    new_root_children = new_store._root_children()

    _diff_children(old_store, new_store, old_root_children, new_root_children, [], mapping, old_content, new_content, result)

    for op in result.ops:
        if isinstance(op, NodeAdded):
            result.stats.added += 1
        elif isinstance(op, NodeRemoved):
            result.stats.removed += 1
        elif isinstance(op, NodeModified):
            result.stats.modified += 1
        elif isinstance(op, NodeMoved):
            result.stats.moved += 1
        elif isinstance(op, NodeRenamed):
            result.stats.renamed += 1

    return result


def _diff_children(
    old_store: DocumentStore,
    new_store: DocumentStore,
    old_children: list[int],
    new_children: list[int],
    current_path: list[int],
    mapping: dict[int, int | None],
    old_content: dict[int, bytes],
    new_content: dict[int, bytes],
    result: DiffResult,
) -> None:
    old_set = set(old_children)
    new_set = set(new_children)

    for new_eid in new_children:
        if new_eid not in set(mapping.values()):
            path = current_path + [new_eid]
            content = _collect_text(new_store, new_eid)
            if new_store.node_type[new_eid] == BlockType.SECTION:
                old_title = ""
                for old_eid, new_eid_mapped in mapping.items():
                    if new_eid_mapped == new_eid:
                        old_title = _collect_text(old_store, old_eid)
                        break
                if old_title and old_title != content:
                    result.ops.append(NodeRenamed(path=path, node_type=new_store.node_type[new_eid], old_title=old_title, new_title=content))
                else:
                    result.ops.append(NodeAdded(path=path, node_type=new_store.node_type[new_eid], content=content))
            else:
                result.ops.append(NodeAdded(path=path, node_type=new_store.node_type[new_eid], content=content))

    for old_eid in old_children:
        new_eid = mapping.get(old_eid)
        path = current_path + [old_eid]
        if new_eid is None:
            content = _collect_text(old_store, old_eid)
            result.ops.append(NodeRemoved(path=path, node_type=old_store.node_type[old_eid], content=content))
        elif new_eid not in new_set:
            new_path = get_path(new_store, new_eid)
            content = _collect_text(new_store, new_eid)
            result.ops.append(NodeMoved(old_path=path, new_path=new_path, node_type=old_store.node_type[old_eid], content=content))
        else:
            old_text = _collect_text(old_store, old_eid)
            new_text = _collect_text(new_store, new_eid)
            if old_text != new_text:
                result.ops.append(NodeModified(path=path, node_type=old_store.node_type[old_eid], old_content=old_text, new_content=new_text))

            old_grandchildren = old_store.children(old_eid)
            new_grandchildren = new_store.children(new_eid)
            if old_grandchildren or new_grandchildren:
                _diff_children(old_store, new_store, old_grandchildren, new_grandchildren, path, mapping, old_content, new_content, result)
