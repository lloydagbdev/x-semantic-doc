import pytest

from semantic_doc.ir import BlockType, Builder, InlineType, ListType
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
    assert "python" in store.text(store.block_language[0])


def test_markdown_reader_list():
    md = "- Item 1\n- Item 2\n- Item 3\n"
    reader = MarkdownReader()
    store = reader.read(md)
    assert store.node_type[0] == BlockType.LIST


def test_markdown_reader_ordered_list():
    md = "1. First\n2. Second\n"
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


def test_markdown_writer_list():
    b = Builder()
    lst = b.list_block(ListType.UNORDERED)
    lst.item("A")
    lst.item("B")
    store = b.build()
    writer = MarkdownWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "- A" in result
    assert "- B" in result


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
    assert "---" in result


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


def test_asciidoc_reader_list():
    adoc = "* Item 1\n* Item 2\n"
    reader = AsciiDocReader()
    store = reader.read(adoc)
    assert store.node_type[0] == BlockType.LIST


def test_asciidoc_writer_paragraph():
    b = Builder()
    b.paragraph("Hello world")
    store = b.build()
    writer = AsciiDocWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    assert "Hello world" in "".join(output)


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
    assert "== Introduction" in "".join(output)


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


def test_html_writer_section():
    b = Builder()
    b.section(1, "Introduction")
    store = b.build()
    writer = HTMLWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "<h1>Introduction</h1>" in result


def test_html_writer_code_block():
    b = Builder()
    b.code_block("python", "print('hi')")
    store = b.build()
    writer = HTMLWriter()
    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    writer.write(store, FakeFile())
    result = "".join(output)
    assert "<pre><code" in result
    assert "print('hi')" in result


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


def test_registry_format_explicit():
    registry = AdapterRegistry()
    from semantic_doc.adapters import MarkdownAdapter, HTMLAdapter
    registry.register(MarkdownAdapter())
    registry.register(HTMLAdapter())

    b = Builder()
    b.paragraph("Test")
    store = b.build()

    output = []
    class FakeFile:
        def write(self, s): output.append(s)
        def close(self): pass
    registry.save(store, FakeFile(), format="html")
    result = "".join(output)
    assert "<!DOCTYPE html>" in result


def test_registry_cannot_read_html():
    registry = AdapterRegistry()
    from semantic_doc.adapters import HTMLAdapter
    registry.register(HTMLAdapter())

    try:
        registry.load("<html></html>", format="html")
        assert False, "Should have raised"
    except ValueError as e:
        assert "cannot read" in str(e).lower()
