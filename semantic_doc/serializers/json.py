from __future__ import annotations

import json
from typing import Any

from ..ir.store import DocumentStore, _NONE, new_store
from ..ir.types import (
    AdmonType,
    BlockType,
    InlineType,
    ListType,
    NodeType,
    PrivacyLevel,
)


def to_dict(store: DocumentStore) -> dict[str, Any]:
    return {
        "version": 1,
        "strings": store.strings,
        "nodes": _serialize_nodes(store),
        "root_first": store.root_first,
        "meta_title": store.meta_title,
        "meta_attrs": store.meta_attrs,
        "components": _serialize_components(store),
    }


def _serialize_nodes(store: DocumentStore) -> list[dict[str, Any]]:
    nodes = []
    for i in range(store.entity_count):
        nodes.append({
            "eid": i,
            "type": store.node_type[i],
            "parent": store.node_parent[i],
            "prev": store.node_prev[i],
            "next": store.node_next[i],
            "first_child": store.node_first_child[i],
        })
    return nodes


def _serialize_components(store: DocumentStore) -> dict[str, Any]:
    return {
        "block_level": {str(k): v for k, v in store.block_level.items()},
        "block_language": {str(k): v for k, v in store.block_language.items()},
        "block_content": {str(k): v for k, v in store.block_content.items()},
        "block_list_type": {str(k): v.value for k, v in store.block_list_type.items()},
        "block_admon_type": {str(k): v.value for k, v in store.block_admon_type.items()},
        "block_checked": {str(k): v for k, v in store.block_checked.items()},
        "block_privacy": {str(k): v.value for k, v in store.block_privacy.items()},
        "inline_text": {str(k): v for k, v in store.inline_text.items()},
        "inline_url": {str(k): v for k, v in store.inline_url.items()},
        "inline_title": {str(k): v for k, v in store.inline_title.items()},
    }


def to_json(store: DocumentStore, indent: int | None = 2) -> str:
    return json.dumps(to_dict(store), indent=indent)


def from_dict(data: dict[str, Any]) -> DocumentStore:
    store = new_store()
    store.strings = list(data["strings"])

    for node_data in data["nodes"]:
        store.node_type.append(_parse_node_type(node_data["type"]))
        store.node_parent.append(node_data["parent"])
        store.node_prev.append(node_data["prev"])
        store.node_next.append(node_data["next"])
        store.node_first_child.append(node_data["first_child"])

    comp = data.get("components", {})
    store.block_level = {int(k): v for k, v in comp.get("block_level", {}).items()}
    store.block_language = {int(k): v for k, v in comp.get("block_language", {}).items()}
    store.block_content = {int(k): v for k, v in comp.get("block_content", {}).items()}
    store.block_list_type = {int(k): ListType(v) for k, v in comp.get("block_list_type", {}).items()}
    store.block_admon_type = {int(k): AdmonType(v) for k, v in comp.get("block_admon_type", {}).items()}
    store.block_checked = {int(k): v for k, v in comp.get("block_checked", {}).items()}
    store.block_privacy = {int(k): PrivacyLevel(v) for k, v in comp.get("block_privacy", {}).items()}
    store.inline_text = {int(k): v for k, v in comp.get("inline_text", {}).items()}
    store.inline_url = {int(k): v for k, v in comp.get("inline_url", {}).items()}
    store.inline_title = {int(k): v for k, v in comp.get("inline_title", {}).items()}

    store.root_first = data.get("root_first", _NONE)
    store.meta_title = data.get("meta_title", _NONE)
    store.meta_attrs = dict(data.get("meta_attrs", {}))

    return store


def _parse_node_type(value: str) -> NodeType:
    try:
        return BlockType(value)
    except ValueError:
        return InlineType(value)


def from_json(text: str) -> DocumentStore:
    return from_dict(json.loads(text))
