import pytest

from semantic_doc.ir import AdmonType, BlockType, Builder, InlineType, ListType
from semantic_doc.serializers import from_dict, from_json, to_dict, to_json


def test_roundtrip_simple():
    b = Builder()
    b.paragraph("Hello", "world")
    store = b.build()

    data = to_dict(store)
    restored = from_dict(data)

    assert restored.entity_count == store.entity_count
    assert restored.node_type[0] == store.node_type[0]
    assert restored.strings == store.strings


def test_roundtrip_complex():
    b = Builder()
    b.title("Test Doc")
    b.attr("author", "Test")
    b.paragraph("Intro")
    s = b.section(1, "Chapter")
    s.paragraph("Content")
    s.code_block("python", "x = 1")
    lst = s.list_block(ListType.ORDERED)
    lst.item("First")
    lst.item("Second")
    b.thematic_break()
    b.admonition(AdmonType.WARNING).paragraph("Watch out")

    store = b.build()
    json_str = to_json(store)
    restored = from_json(json_str)

    assert restored.entity_count == store.entity_count
    assert restored.text(restored.meta_title) == "Test Doc"
    assert restored.meta_attrs["author"] == "Test"


def test_json_is_deterministic():
    b1 = Builder()
    b1.paragraph("Test")
    store1 = b1.build()

    b2 = Builder()
    b2.paragraph("Test")
    store2 = b2.build()

    assert to_json(store1) == to_json(store2)


def test_roundtrip_preserves_structure():
    b = Builder()
    s1 = b.section(1, "A")
    s1.paragraph("P1")
    s2 = s1.section(2, "B")
    s2.paragraph("P2")

    store = b.build()
    restored = from_dict(to_dict(store))

    assert restored.node_type[0] == BlockType.SECTION
    assert restored.block_level[0] == 1
