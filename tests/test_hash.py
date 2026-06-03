import pytest

from semantic_doc.ir import Builder
from semantic_doc.ops import HashPolicy, compute_hashes


def test_hash_deterministic():
    b = Builder()
    b.paragraph("Hello")
    b.section(1, "Title")
    store1 = b.build()

    b2 = Builder()
    b2.paragraph("Hello")
    b2.section(1, "Title")
    store2 = b2.build()

    h1 = compute_hashes(store1)
    h2 = compute_hashes(store2)

    assert h1.doc_hash == h2.doc_hash


def test_hash_different_content():
    b1 = Builder()
    b1.paragraph("Hello")
    store1 = b1.build()

    b2 = Builder()
    b2.paragraph("World")
    store2 = b2.build()

    h1 = compute_hashes(store1)
    h2 = compute_hashes(store2)

    assert h1.doc_hash != h2.doc_hash


def test_hash_subtree_stability():
    b = Builder()
    s = b.section(1, "Stable")
    s.paragraph("Content")
    b.paragraph("Other")
    store = b.build()

    h = compute_hashes(store)
    assert len(h.node_hash) == store.entity_count
    assert len(h.content_hash) == store.entity_count


def test_hash_whitespace_normalization():
    b1 = Builder()
    b1.paragraph("Hello   world")
    store1 = b1.build()

    b2 = Builder()
    b2.paragraph("Hello world")
    store2 = b2.build()

    policy = HashPolicy(normalize_whitespace=True)
    h1 = compute_hashes(store1, policy)
    h2 = compute_hashes(store2, policy)

    assert h1.doc_hash == h2.doc_hash


def test_hash_case_insensitive():
    b1 = Builder()
    b1.paragraph("HELLO")
    store1 = b1.build()

    b2 = Builder()
    b2.paragraph("hello")
    store2 = b2.build()

    policy = HashPolicy(case_sensitive=False)
    h1 = compute_hashes(store1, policy)
    h2 = compute_hashes(store2, policy)

    assert h1.doc_hash == h2.doc_hash
