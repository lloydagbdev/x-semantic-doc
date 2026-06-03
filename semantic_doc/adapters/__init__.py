from .base import (
    Adapter,
    AdapterRegistry,
    Dest,
    Reader,
    ReaderWriter,
    Source,
    Writer,
    get_registry,
    load,
    register,
    save,
)
from .asciidoc import AsciiDocReader, AsciiDocWriter
from .html import HTMLWriter
from .markdown import MarkdownReader, MarkdownWriter


class MarkdownAdapter(Adapter, ReaderWriter):
    def __init__(self):
        super().__init__(
            name="markdown",
            extensions=[".md", ".markdown"],
            can_read=True,
            can_write=True,
            capabilities={"full"},
        )
        self._reader = MarkdownReader()
        self._writer = MarkdownWriter()

    def read(self, source):
        return self._reader.read(source)

    def write(self, store, dest):
        self._writer.write(store, dest)


class AsciiDocAdapter(Adapter, ReaderWriter):
    def __init__(self):
        super().__init__(
            name="asciidoc",
            extensions=[".adoc", ".asciidoc", ".asc"],
            can_read=True,
            can_write=True,
            capabilities={"full"},
        )
        self._reader = AsciiDocReader()
        self._writer = AsciiDocWriter()

    def read(self, source):
        return self._reader.read(source)

    def write(self, store, dest):
        self._writer.write(store, dest)


class HTMLAdapter(Adapter, Writer):
    def __init__(self):
        super().__init__(
            name="html",
            extensions=[".html", ".htm"],
            can_read=False,
            can_write=True,
            capabilities={"emit-only"},
        )
        self._writer = HTMLWriter()

    def write(self, store, dest):
        self._writer.write(store, dest)


register(MarkdownAdapter())
register(AsciiDocAdapter())
register(HTMLAdapter())


__all__ = [
    "Adapter",
    "AdapterRegistry",
    "Dest",
    "Reader",
    "ReaderWriter",
    "Source",
    "Writer",
    "get_registry",
    "load",
    "register",
    "save",
    "MarkdownReader",
    "MarkdownWriter",
    "AsciiDocReader",
    "AsciiDocWriter",
    "HTMLWriter",
]
