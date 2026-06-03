import pytest

from semantic_doc.ir import (
    AdmonType,
    BlockType,
    Builder,
    DocumentStore,
    InlineType,
    ListType,
    PrivacyLevel,
    new_store,
)
from semantic_doc.ir.store import _NONE


def test_new_store_is_empty():
    store = new_store()
    assert store.entity_count == 0
    assert store.root_first == _NONE


def test_alloc_node():
    store = new_store()
    eid = store.alloc_node(BlockType.PARAGRAPH)
    assert eid == 0
    assert store.entity_count == 1
    assert store.node_type[0] == BlockType.PARAGRAPH
    assert store.node_parent[0] == _NONE


def test_alloc_node_with_parent():
    store = new_store()
    parent = store.alloc_node(BlockType.SECTION)
    store.block_level[parent] = 1
    child = store.alloc_node(BlockType.PARAGRAPH, parent=parent)
    assert child == 1
    assert store.node_parent[child] == parent
    assert store.node_first_child[parent] == child


def test_alloc_multiple_siblings():
    store = new_store()
    parent = store.alloc_node(BlockType.SECTION)
    store.block_level[parent] = 1
    c1 = store.alloc_node(BlockType.PARAGRAPH, parent=parent)
    c2 = store.alloc_node(BlockType.PARAGRAPH, parent=parent)
    assert store.node_next[c1] == c2
    assert store.node_prev[c2] == c1
    assert store.node_first_child[parent] == c1


def test_children():
    store = new_store()
    parent = store.alloc_node(BlockType.SECTION)
    store.block_level[parent] = 1
    c1 = store.alloc_node(BlockType.PARAGRAPH, parent=parent)
    c2 = store.alloc_node(BlockType.PARAGRAPH, parent=parent)
    c3 = store.alloc_node(BlockType.CODE_BLOCK, parent=parent)
    assert store.children(parent) == [c1, c2, c3]


def test_root_children():
    store = new_store()
    r1 = store._alloc_root_node(BlockType.PARAGRAPH)
    r2 = store._alloc_root_node(BlockType.SECTION)
    assert store._root_children() == [r1, r2]


def test_intern_deduplicates():
    store = new_store()
    i1 = store.intern("hello")
    i2 = store.intern("hello")
    i3 = store.intern("world")
    assert i1 == i2
    assert i1 != i3
    assert store.strings.count("hello") == 1


def test_clone_is_independent():
    store = new_store()
    eid = store.alloc_node(BlockType.PARAGRAPH)
    store.inline_text[eid] = store.intern("test")

    cloned = store.clone()
    cloned.node_type[0] = BlockType.CODE_BLOCK
    cloned.inline_text[0] = cloned.intern("changed")

    assert store.node_type[0] == BlockType.PARAGRAPH
    assert store.text(store.inline_text[0]) == "test"


def test_set_get_component():
    store = new_store()
    eid = store.alloc_node(BlockType.SECTION)
    store.set_component(eid, "block_level", 2)
    assert store.get_component(eid, "block_level") == 2
    assert store.get_component(eid, "nonexistent", 99) == 99
