import pytest

from semantic_doc.ir import BlockType, Builder, InlineType, ListType
from semantic_doc.ops import build_index


def test_section_index():
    b = Builder()
    b.section(1, "Introduction")
    b.section(2, "Details")
    b.section(1, "Introduction")
    store = b.build()
    idx = build_index(store)
    assert "Introduction" in idx.section_index
    assert len(idx.section_index["Introduction"]) == 2


def test_link_index():
    b = Builder()
    b.paragraph(b.link("https://example.com", "Click here"))
    b.paragraph(b.link("https://example.com", "Also here"))
    b.paragraph(b.link("https://other.com", "Other"))
    store = b.build()
    idx = build_index(store)
    assert "https://example.com" in idx.link_index
    assert len(idx.link_index["https://example.com"]) == 2


def test_term_index():
    b = Builder()
    b.paragraph("The quick brown fox")
    b.paragraph("jumps over the lazy dog")
    store = b.build()
    idx = build_index(store)
    assert "quick" in idx.term_index
    assert "the" in idx.term_index
    assert "fox" in idx.term_index


def test_type_index():
    b = Builder()
    b.paragraph("P1")
    b.section(1, "S1")
    b.code_block("python", "x = 1")
    store = b.build()
    idx = build_index(store)
    assert BlockType.PARAGRAPH in idx.type_index
    assert BlockType.SECTION in idx.type_index
    assert BlockType.CODE_BLOCK in idx.type_index


def test_level_index():
    b = Builder()
    b.section(1, "H1")
    b.section(2, "H2")
    b.section(1, "H1 again")
    store = b.build()
    idx = build_index(store)
    assert 1 in idx.level_index
    assert 2 in idx.level_index
    assert len(idx.level_index[1]) == 2
