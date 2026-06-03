from __future__ import annotations

from dataclasses import dataclass, field

from ..ir.build import Builder
from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import preorder
from ..ir.types import BlockType, InlineType, NodeType
from .diff import DiffResult, NodeAdded, NodeModified, NodeRemoved, semantic_diff


@dataclass
class MergeConflict:
    path: list[int]
    node_type: NodeType
    ours: str = ""
    theirs: str = ""
    base: str = ""
    resolution: str | None = None

    def __str__(self):
        return f"Conflict at {self.node_type.value} [{self.path}]:\n  base: {self.base[:40]}\n  ours: {self.ours[:40]}\n  theirs: {theirs[:40]}"


@dataclass
class MergeResult:
    store: DocumentStore | None = None
    conflicts: list[MergeConflict] = field(default_factory=list)

    @property
    def is_clean(self):
        return len(self.conflicts) == 0


def semantic_merge(
    base: DocumentStore,
    ours: DocumentStore,
    theirs: DocumentStore,
    strategy: str = "auto",
) -> MergeResult:
    ours_diff = semantic_diff(base, ours)
    theirs_diff = semantic_diff(base, theirs)

    result = MergeResult()

    ours_ops = {(type(op), tuple(op.path)): op for op in ours_diff.ops}
    theirs_ops = {(type(op), tuple(op.path)): op for op in theirs_diff.ops}

    all_keys = set(ours_ops.keys()) | set(theirs_ops.keys())
    conflicting_keys = set()
    compatible_keys = []

    for key in all_keys:
        in_ours = key in ours_ops
        in_theirs = key in theirs_ops
        if in_ours and in_theirs:
            ours_op = ours_ops[key]
            theirs_op = theirs_ops[key]
            if _ops_compatible(ours_op, theirs_op):
                compatible_keys.append(key)
            else:
                conflicting_keys.add(key)
        else:
            compatible_keys.append(key)

    merged = base.clone()

    for key in compatible_keys:
        if key in ours_ops:
            _apply_op(merged, ours_ops[key], ours)
        if key in theirs_ops:
            _apply_op(merged, theirs_ops[key], theirs)

    for key in conflicting_keys:
        ours_op = ours_ops.get(key)
        theirs_op = theirs_ops.get(key)
        if ours_op and theirs_op:
            path = list(ours_op.path) if hasattr(ours_op, "path") else []
            ntype = ours_op.node_type if hasattr(ours_op, "node_type") else theirs_op.node_type
            ours_content = ours_op.new_content if hasattr(ours_op, "new_content") else ""
            theirs_content = theirs_op.new_content if hasattr(theirs_op, "new_content") else ""
            base_content = ours_op.old_content if hasattr(ours_op, "old_content") else ""
            conflict = MergeConflict(
                path=path,
                node_type=ntype,
                ours=ours_content,
                theirs=theirs_content,
                base=base_content,
            )
            if strategy == "ours":
                conflict.resolution = ours_content
            elif strategy == "theirs":
                conflict.resolution = theirs_content
            result.conflicts.append(conflict)

    if result.is_clean:
        result.store = merged
    else:
        result.store = merged

    return result


def _ops_compatible(op1, op2) -> bool:
    if type(op1) != type(op2):
        return False
    if isinstance(op1, NodeModified):
        if op1.new_content == op2.new_content:
            return True
        return False
    if isinstance(op1, NodeAdded):
        return op1.content == op2.content
    if isinstance(op1, NodeRemoved):
        return True
    return False


def _apply_op(store: DocumentStore, op, source_store: DocumentStore) -> None:
    pass
