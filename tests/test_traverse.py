import pytest

from semantic_doc.ir import (
    BlockType,
    Builder,
    InlineType,
    Visitor,
    bfs,
    depth,
    leaves,
    path,
    postorder,
    preorder,
)


def _simple_store():
    b = Builder()
    b.paragraph("P1")
    s = b.section(1, "S1")
    s.paragraph("P2")
    s.paragraph("P3")
    return b.build()


def test_preorder():
    store = _simple_store()
    order = list(preorder(store))
    assert len(order) == store.entity_count
    assert store.node_type[order[0]] == BlockType.PARAGRAPH


def test_postorder():
    store = _simple_store()
    order = list(postorder(store))
    assert len(order) == store.entity_count
    assert store.node_type[order[-1]] == BlockType.PARAGRAPH


def test_bfs():
    store = _simple_store()
    order = list(bfs(store))
    assert len(order) == store.entity_count


def test_path():
    store = _simple_store()
    p2_eid = None
    for eid in preorder(store):
        if store.node_type[eid] == BlockType.PARAGRAPH and store.node_parent[eid] != -1:
            if store.node_parent[eid] >= 0 and store.node_type[store.node_parent[eid]] == BlockType.SECTION:
                p2_eid = eid
                break
    if p2_eid is not None:
        p = path(store, p2_eid)
        assert len(p) >= 2


def test_depth():
    store = _simple_store()
    root_eid = list(preorder(store))[0]
    assert depth(store, root_eid) == 0


def test_leaves():
    store = _simple_store()
    leaf_ids = list(leaves(store))
    assert len(leaf_ids) > 0
    for eid in leaf_ids:
        assert store.node_first_child[eid] == -1


class CountingVisitor(Visitor):
    def __init__(self):
        self.block_count = 0
        self.inline_count = 0

    def visit_block(self, store, eid, btype):
        self.block_count += 1

    def visit_inline(self, store, eid, itype):
        self.inline_count += 1


def test_visitor():
    store = _simple_store()
    v = CountingVisitor()
    v.walk(store)
    assert v.block_count > 0
    assert v.inline_count > 0
