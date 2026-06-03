from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import postorder
from ..ir.types import BlockType, InlineType


@dataclass
class HashPolicy:
    normalize_whitespace: bool = False
    case_sensitive: bool = True
    include_metadata: bool = True
    include_privacy_tags: bool = False
    algorithm: str = "sha256"


@dataclass
class HashResult:
    content_hash: dict[int, bytes] = field(default_factory=dict)
    node_hash: dict[int, bytes] = field(default_factory=dict)
    doc_hash: bytes = b""


def _normalize(s: str, policy: HashPolicy) -> str:
    if policy.normalize_whitespace:
        s = " ".join(s.split())
    if not policy.case_sensitive:
        s = s.lower()
    return s


def _content_bytes(store: DocumentStore, eid: int, policy: HashPolicy) -> bytes:
    parts: list[bytes] = []
    ntype = store.node_type[eid]
    parts.append(ntype.value.encode())

    if ntype in (InlineType.TEXT, InlineType.INLINE_CODE):
        t = store.inline_text.get(eid, _NONE)
        if t >= 0:
            parts.append(_normalize(store.text(t), policy).encode())

    if ntype == BlockType.CODE_BLOCK:
        lang = store.block_language.get(eid, _NONE)
        if lang >= 0:
            parts.append(store.text(lang).encode())
        content = store.block_content.get(eid, _NONE)
        if content >= 0:
            parts.append(_normalize(store.text(content), policy).encode())

    if ntype == BlockType.SECTION:
        level = store.block_level.get(eid, 0)
        parts.append(str(level).encode())

    if ntype == BlockType.LIST:
        lt = store.block_list_type.get(eid)
        if lt:
            parts.append(lt.value.encode())

    if ntype == BlockType.ADMONITION:
        at = store.block_admon_type.get(eid)
        if at:
            parts.append(at.value.encode())

    if ntype in (InlineType.LINK, InlineType.IMAGE):
        url = store.inline_url.get(eid, _NONE)
        if url >= 0:
            parts.append(store.text(url).encode())
        title = store.inline_title.get(eid, _NONE)
        if title >= 0:
            parts.append(store.text(title).encode())

    if ntype == BlockType.LIST_ITEM:
        checked = store.block_checked.get(eid)
        if checked is not None:
            parts.append(b"checked" if checked else b"unchecked")

    if policy.include_privacy_tags:
        priv = store.block_privacy.get(eid)
        if priv:
            parts.append(priv.value.encode())

    return b"|".join(parts)


def _hash(data: bytes, algorithm: str) -> bytes:
    h = hashlib.new(algorithm)
    h.update(data)
    return h.digest()


def compute_hashes(store: DocumentStore, policy: HashPolicy | None = None) -> HashResult:
    if policy is None:
        policy = HashPolicy()

    result = HashResult()

    for eid in postorder(store):
        content_data = _content_bytes(store, eid, policy)
        result.content_hash[eid] = _hash(content_data, policy.algorithm)

        child_hashes = []
        for cid in store.children(eid):
            child_hashes.append(result.node_hash[cid])
        child_hashes.sort()

        node_data = content_data + b"".join(child_hashes)
        result.node_hash[eid] = _hash(node_data, policy.algorithm)

    root_children = store._root_children()
    root_hashes = sorted(result.node_hash[c] for c in root_children) if root_children else []

    meta_data = b""
    if policy.include_metadata:
        if store.meta_title >= 0:
            meta_data += store.text(store.meta_title).encode()
        for k, v in sorted(store.meta_attrs.items()):
            meta_data += f"{k}={v}".encode()

    doc_data = meta_data + b"".join(root_hashes)
    result.doc_hash = _hash(doc_data, policy.algorithm)

    return result
