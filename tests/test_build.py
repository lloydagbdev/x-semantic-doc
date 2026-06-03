import pytest

from semantic_doc.ir import (
    AdmonType,
    BlockType,
    Builder,
    InlineType,
    ListType,
    PrivacyLevel,
)
from semantic_doc.ir.store import _NONE


def test_builder_paragraph():
    b = Builder()
    b.paragraph("Hello", "world")
    store = b.build()
    assert store.entity_count == 2
    assert store.node_type[0] == BlockType.PARAGRAPH
    assert store.node_type[1] == InlineType.TEXT
    assert store.text(store.inline_text[1]) == "Hello"


def test_builder_with_inline_handles():
    b = Builder()
    b.paragraph(b.text("Hello"), b.strong("world"))
    store = b.build()
    assert store.node_type[0] == BlockType.PARAGRAPH
    assert store.node_type[1] == InlineType.TEXT
    assert store.node_type[2] == InlineType.STRONG


def test_builder_code_block():
    b = Builder()
    b.code_block("python", "print('hi')")
    store = b.build()
    assert store.node_type[0] == BlockType.CODE_BLOCK
    assert store.text(store.block_language[0]) == "python"
    assert store.text(store.block_content[0]) == "print('hi')"


def test_builder_section():
    b = Builder()
    s = b.section(1, "Introduction")
    s.paragraph("First paragraph")
    store = b.build()
    assert store.node_type[0] == BlockType.SECTION
    assert store.block_level[0] == 1
    assert store.node_type[1] == InlineType.TEXT
    assert store.node_type[2] == BlockType.PARAGRAPH


def test_builder_nested_section():
    b = Builder()
    s1 = b.section(1, "Main")
    s2 = s1.section(2, "Sub")
    s2.paragraph("Content")
    store = b.build()
    assert store.node_type[0] == BlockType.SECTION
    assert store.node_type[3] == BlockType.SECTION
    assert store.block_level[3] == 2


def test_builder_list():
    b = Builder()
    lst = b.list_block(ListType.ORDERED)
    lst.item("First")
    lst.item("Second")
    store = b.build()
    assert store.node_type[0] == BlockType.LIST
    assert store.block_list_type[0] == ListType.ORDERED
    assert store.node_type[1] == BlockType.LIST_ITEM
    assert store.node_type[2] == BlockType.LIST_ITEM


def test_builder_checklist():
    b = Builder()
    lst = b.list_block(ListType.CHECKLIST)
    lst.item("Done", checked=True)
    lst.item("Not done", checked=False)
    store = b.build()
    assert store.block_checked[1] is True
    assert store.block_checked[2] is False


def test_builder_table():
    b = Builder()
    t = b.table()
    t.row("A", "B")
    t.row("C", "D")
    store = b.build()
    assert store.node_type[0] == BlockType.TABLE
    assert store.node_type[1] == BlockType.TABLE_ROW
    assert store.node_type[3] == BlockType.TABLE_ROW


def test_builder_thematic_break():
    b = Builder()
    b.thematic_break()
    store = b.build()
    assert store.node_type[0] == BlockType.THEMATIC_BREAK


def test_builder_admonition():
    b = Builder()
    b.admonition(AdmonType.WARNING).paragraph("Watch out")
    store = b.build()
    assert store.node_type[0] == BlockType.ADMONITION
    assert store.block_admon_type[0] == AdmonType.WARNING


def test_builder_metadata():
    b = Builder()
    b.title("My Doc").attr("author", "Test")
    store = b.build()
    assert store.text(store.meta_title) == "My Doc"
    assert store.meta_attrs["author"] == "Test"


def test_builder_complex_document():
    b = Builder()
    b.title("Test Doc")
    b.paragraph("Intro")
    s = b.section(1, "Chapter 1")
    s.paragraph("Content")
    s.code_block("python", "x = 1")
    lst = s.list_block()
    lst.item("A")
    lst.item("B")
    b.thematic_break()

    store = b.build()
    assert store.entity_count > 0
    assert store.text(store.meta_title) == "Test Doc"
