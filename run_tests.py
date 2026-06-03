import sys
import traceback

test_results = []


def run_test(module_name, test_func):
    try:
        test_func()
        test_results.append((module_name, test_func.__name__, True, None))
        print(f"  PASS: {test_func.__name__}")
    except Exception as e:
        test_results.append((module_name, test_func.__name__, False, traceback.format_exc()))
        print(f"  FAIL: {test_func.__name__}: {e}")


def run_module(module_name, test_funcs):
    print(f"\n{module_name}:")
    for func in test_funcs:
        run_test(module_name, func)


# ===== STORE TESTS =====
from semantic_doc.ir import BlockType, InlineType, ListType, new_store
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

run_module("store", [
    test_new_store_is_empty,
    test_alloc_node,
    test_alloc_node_with_parent,
    test_alloc_multiple_siblings,
    test_children,
    test_root_children,
    test_intern_deduplicates,
    test_clone_is_independent,
    test_set_get_component,
])


# ===== BUILD TESTS =====
from semantic_doc.ir import Builder, AdmonType, PrivacyLevel

def test_builder_paragraph():
    b = Builder()
    b.paragraph("Hello", "world")
    store = b.build()
    assert store.entity_count == 3
    assert store.node_type[0] == BlockType.PARAGRAPH
    assert store.node_type[1] == InlineType.TEXT
    assert store.text(store.inline_text[1]) == "Hello"

def test_builder_with_inline_handles():
    b = Builder()
    b.paragraph(b.text("Hello"), b.strong("world"))
    store = b.build()
    para_eid = 3
    assert store.node_type[para_eid] == BlockType.PARAGRAPH
    assert store.node_type[0] == InlineType.TEXT
    assert store.node_type[1] == InlineType.STRONG

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

def test_builder_list():
    b = Builder()
    lst = b.list_block(ListType.ORDERED)
    lst.item("First")
    lst.item("Second")
    store = b.build()
    assert store.node_type[0] == BlockType.LIST
    assert store.block_list_type[0] == ListType.ORDERED
    assert store.node_type[1] == BlockType.LIST_ITEM
    assert store.node_type[3] == BlockType.LIST_ITEM

def test_builder_checklist():
    b = Builder()
    lst = b.list_block(ListType.CHECKLIST)
    lst.item("Done", checked=True)
    lst.item("Not done", checked=False)
    store = b.build()
    assert store.block_checked[1] is True
    assert store.block_checked[3] is False

def test_builder_table():
    b = Builder()
    t = b.table()
    t.row("A", "B")
    t.row("C", "D")
    store = b.build()
    assert store.node_type[0] == BlockType.TABLE
    assert store.node_type[1] == BlockType.TABLE_ROW
    assert store.node_type[6] == BlockType.TABLE_ROW

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

run_module("build", [
    test_builder_paragraph,
    test_builder_with_inline_handles,
    test_builder_code_block,
    test_builder_section,
    test_builder_list,
    test_builder_checklist,
    test_builder_table,
    test_builder_thematic_break,
    test_builder_admonition,
    test_builder_metadata,
])


# ===== TRAVERSE TESTS =====
from semantic_doc.ir import Visitor, bfs, depth, leaves, path, postorder, preorder

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

run_module("traverse", [
    test_preorder,
    test_postorder,
    test_bfs,
    test_path,
    test_depth,
    test_leaves,
    test_visitor,
])


# ===== HASH TESTS =====
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

run_module("hash", [
    test_hash_deterministic,
    test_hash_different_content,
    test_hash_subtree_stability,
    test_hash_whitespace_normalization,
    test_hash_case_insensitive,
])


# ===== INDEX TESTS =====
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

run_module("index", [
    test_section_index,
    test_link_index,
    test_term_index,
    test_type_index,
    test_level_index,
])


# ===== PRIVACY TESTS =====
import re
from semantic_doc.ops import PrivacyMask, RedactionAction, StructuralRule, TextRule, apply_rules, redact

def test_text_rule_replace():
    b = Builder()
    b.paragraph("Contact: john@example.com for info")
    b.paragraph("No email here")
    store = b.build()
    rule = TextRule(pattern=re.compile(r"\w+@\w+\.\w+"), action=RedactionAction.REPLACE, replacement="[EMAIL]")
    mask = apply_rules(store, [rule])
    assert len(mask.affected) > 0
    redacted = redact(store, mask)
    for eid in mask.replacements:
        assert redacted.text(redacted.inline_text[eid]) == "[EMAIL]"

def test_text_rule_mask():
    b = Builder()
    b.paragraph("SSN: 123-45-6789")
    store = b.build()
    rule = TextRule(pattern=re.compile(r"\d{3}-\d{2}-\d{4}"), action=RedactionAction.MASK)
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    for eid in mask.replacements:
        replaced = redacted.text(redacted.inline_text[eid])
        assert all(c == "\u2588" for c in replaced)

def test_text_rule_hash():
    b = Builder()
    b.paragraph("Secret: password123")
    store = b.build()
    rule = TextRule(pattern=re.compile(r"password123"), action=RedactionAction.HASH)
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    for eid in mask.replacements:
        replaced = redacted.text(redacted.inline_text[eid])
        assert replaced.startswith("[HASH:")
        assert replaced.endswith("]")

def test_structural_rule_remove():
    b = Builder()
    b.paragraph("Keep this")
    b.code_block("python", "secret = 'key'")
    b.paragraph("Also keep")
    store = b.build()
    rule = StructuralRule(node_types={BlockType.CODE_BLOCK}, action=RedactionAction.REMOVE)
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    from semantic_doc.ir import preorder
    reachable = list(preorder(redacted))
    code_blocks = [eid for eid in reachable if redacted.node_type[eid] == BlockType.CODE_BLOCK]
    assert len(code_blocks) == 0

def test_structural_rule_privacy_level():
    b = Builder()
    p1 = b.paragraph("Public text")
    p2 = b.paragraph("Confidential text")
    p2.privacy(PrivacyLevel.CONFIDENTIAL)
    store = b.build()
    rule = StructuralRule(min_privacy=PrivacyLevel.CONFIDENTIAL, action=RedactionAction.REPLACE, replacement="[REDACTED]")
    mask = apply_rules(store, [rule])
    assert len(mask.affected) == 1

def test_redact_does_not_mutate_original():
    b = Builder()
    b.paragraph("Sensitive data")
    store = b.build()
    rule = TextRule(pattern=re.compile(r"Sensitive"), action=RedactionAction.REPLACE, replacement="[REDACTED]")
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    original_text = store.text(store.inline_text[1])
    assert "Sensitive" in original_text

run_module("privacy", [
    test_text_rule_replace,
    test_text_rule_mask,
    test_text_rule_hash,
    test_structural_rule_remove,
    test_structural_rule_privacy_level,
    test_redact_does_not_mutate_original,
])


# ===== JSON TESTS =====
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

run_module("json", [
    test_roundtrip_simple,
    test_roundtrip_complex,
    test_json_is_deterministic,
    test_roundtrip_preserves_structure,
])


# ===== ADAPTER TESTS =====
from semantic_doc.adapters import (
    AsciiDocReader,
    AsciiDocWriter,
    HTMLWriter,
    MarkdownReader,
    MarkdownWriter,
)
from semantic_doc.adapters.base import AdapterRegistry

def test_markdown_reader_paragraph():
    md = "# Title\n\nHello world\n\nSecond paragraph\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.entity_count > 0
    assert store.node_type[0] == BlockType.SECTION

def test_markdown_reader_code_block():
    md = "```python\nprint('hello')\n```\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.node_type[0] == BlockType.CODE_BLOCK

def test_markdown_reader_list():
    md = "- Item 1\n- Item 2\n- Item 3\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.node_type[0] == BlockType.LIST

def test_markdown_reader_blockquote():
    md = "> This is a quote\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.node_type[0] == BlockType.BLOCKQUOTE

def test_markdown_reader_thematic_break():
    md = "---\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.node_type[0] == BlockType.THEMATIC_BREAK

def test_markdown_writer_paragraph():
    b = Builder()
    b.paragraph("Hello world")
    store = b.build()
    writer = MarkdownWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    assert "Hello world" in "".join(output)

def test_markdown_writer_code_block():
    b = Builder()
    b.code_block("python", "print('hi')")
    store = b.build()
    writer = MarkdownWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "```python" in result
    assert "print('hi')" in result

def test_markdown_writer_section():
    b = Builder()
    b.section(1, "Introduction")
    store = b.build()
    writer = MarkdownWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    assert "# Introduction" in "".join(output)

def test_markdown_roundtrip():
    md = "# Title\n\nHello world\n\n```python\nprint('hi')\n```\n\n- Item 1\n- Item 2\n\n---\n"
    reader = MarkdownReader()
    store = reader.read(md)
    writer = MarkdownWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "# Title" in result
    assert "Hello world" in result
    assert "```" in result

def test_asciidoc_reader_heading():
    adoc = "= My Document\n\n== Introduction\n\nSome text\n"
    reader = AsciiDocReader()
    store = reader.read(adoc)
    assert store.meta_title >= 0

def test_asciidoc_reader_code_block():
    adoc = "----\nprint('hello')\n----\n"
    reader = AsciiDocReader()
    store = reader.read(adoc)
    assert store.node_type[0] == BlockType.CODE_BLOCK

def test_asciidoc_writer_section():
    b = Builder()
    b.section(1, "Introduction")
    store = b.build()
    writer = AsciiDocWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    assert "= Introduction" in "".join(output)

def test_html_writer_paragraph():
    b = Builder()
    b.paragraph("Hello world")
    store = b.build()
    writer = HTMLWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "<p>Hello world</p>" in result

def test_html_writer_escapes():
    b = Builder()
    b.paragraph("<script>alert('xss')</script>")
    store = b.build()
    writer = HTMLWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result

def test_registry_auto_detect():
    registry = AdapterRegistry()
    from semantic_doc.adapters import MarkdownAdapter, AsciiDocAdapter, HTMLAdapter
    registry.register(MarkdownAdapter())
    registry.register(AsciiDocAdapter())
    registry.register(HTMLAdapter())
    md = "# Test\n\nHello\n"
    store = registry.load(md, format="markdown")
    assert store.entity_count > 0

def test_registry_cannot_read_html():
    registry = AdapterRegistry()
    from semantic_doc.adapters import HTMLAdapter
    registry.register(HTMLAdapter())
    try:
        registry.load("<html></html>", format="html")
        assert False, "Should have raised"
    except ValueError as e:
        assert "cannot read" in str(e).lower()

run_module("adapters", [
    test_markdown_reader_paragraph,
    test_markdown_reader_code_block,
    test_markdown_reader_list,
    test_markdown_reader_blockquote,
    test_markdown_reader_thematic_break,
    test_markdown_writer_paragraph,
    test_markdown_writer_code_block,
    test_markdown_writer_section,
    test_markdown_roundtrip,
    test_asciidoc_reader_heading,
    test_asciidoc_reader_code_block,
    test_asciidoc_writer_section,
    test_html_writer_paragraph,
    test_html_writer_escapes,
    test_registry_auto_detect,
    test_registry_cannot_read_html,
])


# ===== SUMMARY =====
print("\n" + "=" * 60)
passed = sum(1 for _, _, ok, _ in test_results if ok)
failed = sum(1 for _, _, ok, _ in test_results if not ok)
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")

if failed > 0:
    print("\nFailures:")
    for module, name, ok, tb in test_results:
        if not ok:
            print(f"\n  {module}.{name}:")
            print(tb)
    sys.exit(1)
else:
    print("\nAll tests passed!")
    sys.exit(0)
