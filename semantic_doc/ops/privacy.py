from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import path, preorder
from ..ir.types import BlockType, InlineType, NodeType, PrivacyLevel, RedactionAction


@dataclass
class TextRule:
    pattern: re.Pattern[str]
    action: RedactionAction = RedactionAction.REPLACE
    replacement: str = "[REDACTED]"


@dataclass
class StructuralRule:
    node_types: set[NodeType] = field(default_factory=set)
    min_privacy: PrivacyLevel | None = None
    action: RedactionAction = RedactionAction.REMOVE
    replacement: str = "[REDACTED]"


@dataclass(frozen=True)
class PrivacyMask:
    affected: frozenset[int] = frozenset()
    replacements: dict[int, str] = field(default_factory=dict)


def apply_rules(
    store: DocumentStore,
    rules: list[TextRule | StructuralRule],
) -> PrivacyMask:
    affected: set[int] = set()
    replacements: dict[int, str] = {}

    for eid in preorder(store):
        for rule in rules:
            if isinstance(rule, StructuralRule):
                if _matches_structural(store, eid, rule):
                    _apply_action(store, eid, rule.action, rule.replacement, affected, replacements)
                    break
            elif isinstance(rule, TextRule):
                if _matches_text(store, eid, rule):
                    _apply_action(store, eid, rule.action, rule.replacement, affected, replacements)

    return PrivacyMask(
        affected=frozenset(affected),
        replacements=replacements,
    )


def _matches_structural(store: DocumentStore, eid: int, rule: StructuralRule) -> bool:
    ntype = store.node_type[eid]
    if rule.node_types and ntype not in rule.node_types:
        return False
    if rule.min_privacy is not None:
        priv = store.block_privacy.get(eid, PrivacyLevel.PUBLIC)
        if _privacy_rank(priv) < _privacy_rank(rule.min_privacy):
            return False
    return True


def _matches_text(store: DocumentStore, eid: int, rule: TextRule) -> bool:
    if store.node_type[eid] != InlineType.TEXT:
        return False
    t = store.inline_text.get(eid, _NONE)
    if t < 0:
        return False
    return bool(rule.pattern.search(store.text(t)))


def _apply_action(
    store: DocumentStore,
    eid: int,
    action: RedactionAction,
    replacement: str,
    affected: set[int],
    replacements: dict[int, str],
) -> None:
    affected.add(eid)

    if action == RedactionAction.REMOVE:
        return

    if action == RedactionAction.REPLACE:
        replacements[eid] = replacement

    elif action == RedactionAction.MASK:
        t = store.inline_text.get(eid, _NONE)
        if t >= 0:
            replacements[eid] = "\u2588" * len(store.text(t))

    elif action == RedactionAction.HASH:
        t = store.inline_text.get(eid, _NONE)
        if t >= 0:
            h = hashlib.sha256(store.text(t).encode()).hexdigest()[:8]
            replacements[eid] = f"[HASH:{h}]"

    elif action == RedactionAction.ANONYMIZE:
        replacements[eid] = f"[ANON:{eid}]"


def redact(store: DocumentStore, mask: PrivacyMask) -> DocumentStore:
    result = store.clone()

    to_remove = []
    for eid in mask.affected:
        action_for_eid = mask.replacements.get(eid)
        if action_for_eid is None:
            to_remove.append(eid)

    for eid in sorted(to_remove, reverse=True):
        _remove_node(result, eid)

    for eid, replacement in mask.replacements.items():
        if eid < result.entity_count:
            result.inline_text[eid] = result.intern(replacement)

    return result


def _remove_node(store: DocumentStore, eid: int) -> None:
    parent = store.node_parent[eid]
    prev = store.node_prev[eid]
    next_ = store.node_next[eid]

    if prev != _NONE:
        store.node_next[prev] = next_
    if next_ != _NONE:
        store.node_prev[next_] = prev

    if parent == _NONE:
        if store.root_first == eid:
            store.root_first = next_ if next_ != _NONE else _NONE
    else:
        if store.node_first_child[parent] == eid:
            store.node_first_child[parent] = next_ if next_ != _NONE else _NONE


def _privacy_rank(level: PrivacyLevel) -> int:
    return {
        PrivacyLevel.PUBLIC: 0,
        PrivacyLevel.INTERNAL: 1,
        PrivacyLevel.CONFIDENTIAL: 2,
        PrivacyLevel.SECRET: 3,
    }[level]
