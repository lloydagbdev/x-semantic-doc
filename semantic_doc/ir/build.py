from __future__ import annotations

from typing import Sequence

from .store import DocumentStore, _NONE, new_store
from .types import AdmonType, BlockType, InlineType, ListType, PrivacyLevel


class _NodeHandle:
    def __init__(self, store: DocumentStore, eid: int):
        self._store = store
        self._eid = eid

    @property
    def eid(self) -> int:
        return self._eid

    @property
    def store(self) -> DocumentStore:
        return self._store


class _BlockHandle(_NodeHandle):
    def paragraph(self, *inlines: str | _InlineHandle) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.PARAGRAPH, parent=self._eid)
        handle = _BlockHandle(self._store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self._store, eid, item)
            else:
                _adopt_inline(self._store, eid, item)
        return handle

    def code_block(self, language: str | None, content: str) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.CODE_BLOCK, parent=self._eid)
        if language is not None:
            self._store.block_language[eid] = self._store.intern(language)
        self._store.block_content[eid] = self._store.intern(content)
        return _BlockHandle(self._store, eid)

    def heading(self, level: int, *inlines: str | _InlineHandle) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.SECTION, parent=self._eid)
        self._store.block_level[eid] = level
        handle = _BlockHandle(self._store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self._store, eid, item)
            else:
                _adopt_inline(self._store, eid, item)
        return handle

    def section(self, level: int, *inlines: str | _InlineHandle) -> _SectionHandle:
        eid = self._store.alloc_node(BlockType.SECTION, parent=self._eid)
        self._store.block_level[eid] = level
        handle = _SectionHandle(self._store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self._store, eid, item)
            else:
                _adopt_inline(self._store, eid, item)
        return handle

    def list_block(self, list_type: ListType = ListType.UNORDERED) -> _ListHandle:
        eid = self._store.alloc_node(BlockType.LIST, parent=self._eid)
        self._store.block_list_type[eid] = list_type
        return _ListHandle(self._store, eid)

    def blockquote(self) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.BLOCKQUOTE, parent=self._eid)
        return _BlockHandle(self._store, eid)

    def table(self) -> _TableHandle:
        eid = self._store.alloc_node(BlockType.TABLE, parent=self._eid)
        return _TableHandle(self._store, eid)

    def thematic_break(self) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.THEMATIC_BREAK, parent=self._eid)
        return _BlockHandle(self._store, eid)

    def admonition(self, admon_type: AdmonType) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.ADMONITION, parent=self._eid)
        self._store.block_admon_type[eid] = admon_type
        return _BlockHandle(self._store, eid)

    def privacy(self, level: PrivacyLevel) -> _BlockHandle:
        self._store.block_privacy[self._eid] = level
        return self


class _SectionHandle(_BlockHandle):
    def body(self) -> _BlockHandle:
        return self


class _ListHandle(_BlockHandle):
    def item(self, *inlines: str | _InlineHandle, checked: bool | None = None) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.LIST_ITEM, parent=self._eid)
        if checked is not None:
            self._store.block_checked[eid] = checked
        handle = _BlockHandle(self._store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self._store, eid, item)
            else:
                _adopt_inline(self._store, eid, item)
        return handle


class _TableHandle(_BlockHandle):
    def row(self, *cells: str | Sequence[str]) -> _BlockHandle:
        eid = self._store.alloc_node(BlockType.TABLE_ROW, parent=self._eid)
        for cell_content in cells:
            cell_eid = self._store.alloc_node(BlockType.TABLE_CELL, parent=eid)
            if isinstance(cell_content, str):
                _add_text(self._store, cell_eid, cell_content)
            else:
                for s in cell_content:
                    _add_text(self._store, cell_eid, s)
        return _BlockHandle(self._store, eid)


class _InlineHandle(_NodeHandle):
    pass


def _add_text(store: DocumentStore, parent: int, text: str) -> int:
    eid = store.alloc_node(InlineType.TEXT, parent=parent)
    store.inline_text[eid] = store.intern(text)
    return eid


def _adopt_inline(store: DocumentStore, parent: int, handle: _InlineHandle) -> None:
    store.node_parent[handle._eid] = parent
    last = store.node_first_child[parent]
    if last == _NONE:
        store.node_first_child[parent] = handle._eid
    else:
        while store.node_next[last] != _NONE:
            last = store.node_next[last]
        store.node_next[last] = handle._eid
        store.node_prev[handle._eid] = last


class Builder:
    def __init__(self):
        self.store = new_store()

    def title(self, text: str) -> Builder:
        self.store.meta_title = self.store.intern(text)
        return self

    def attr(self, key: str, value: str) -> Builder:
        self.store.meta_attrs[key] = value
        return self

    def paragraph(self, *inlines: str | _InlineHandle) -> _BlockHandle:
        eid = self.store._alloc_root_node(BlockType.PARAGRAPH)
        handle = _BlockHandle(self.store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self.store, eid, item)
            else:
                _adopt_inline(self.store, eid, item)
        return handle

    def code_block(self, language: str | None, content: str) -> _BlockHandle:
        eid = self.store._alloc_root_node(BlockType.CODE_BLOCK)
        if language is not None:
            self.store.block_language[eid] = self.store.intern(language)
        self.store.block_content[eid] = self.store.intern(content)
        return _BlockHandle(self.store, eid)

    def section(self, level: int, *inlines: str | _InlineHandle) -> _SectionHandle:
        eid = self.store._alloc_root_node(BlockType.SECTION)
        self.store.block_level[eid] = level
        handle = _SectionHandle(self.store, eid)
        for item in inlines:
            if isinstance(item, str):
                _add_text(self.store, eid, item)
            else:
                _adopt_inline(self.store, eid, item)
        return handle

    def list_block(self, list_type: ListType = ListType.UNORDERED) -> _ListHandle:
        eid = self.store._alloc_root_node(BlockType.LIST)
        self.store.block_list_type[eid] = list_type
        return _ListHandle(self.store, eid)

    def blockquote(self) -> _BlockHandle:
        eid = self.store._alloc_root_node(BlockType.BLOCKQUOTE)
        return _BlockHandle(self.store, eid)

    def table(self) -> _TableHandle:
        eid = self.store._alloc_root_node(BlockType.TABLE)
        return _TableHandle(self.store, eid)

    def thematic_break(self) -> _BlockHandle:
        eid = self.store._alloc_root_node(BlockType.THEMATIC_BREAK)
        return _BlockHandle(self.store, eid)

    def admonition(self, admon_type: AdmonType) -> _BlockHandle:
        eid = self.store._alloc_root_node(BlockType.ADMONITION)
        self.store.block_admon_type[eid] = admon_type
        return _BlockHandle(self.store, eid)

    def build(self) -> DocumentStore:
        return self.store

    def text(self, content: str) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.TEXT)
        self.store.inline_text[eid] = self.store.intern(content)
        return _InlineHandle(self.store, eid)

    def emphasis(self, *children: str | _InlineHandle) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.EMPHASIS)
        handle = _InlineHandle(self.store, eid)
        for item in children:
            if isinstance(item, str):
                _add_text(self.store, eid, item)
            else:
                _adopt_inline(self.store, eid, item)
        return handle

    def strong(self, *children: str | _InlineHandle) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.STRONG)
        handle = _InlineHandle(self.store, eid)
        for item in children:
            if isinstance(item, str):
                _add_text(self.store, eid, item)
            else:
                _adopt_inline(self.store, eid, item)
        return handle

    def inline_code(self, content: str) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.INLINE_CODE)
        self.store.inline_text[eid] = self.store.intern(content)
        return _InlineHandle(self.store, eid)

    def link(self, url: str, *children: str | _InlineHandle, title: str | None = None) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.LINK)
        self.store.inline_url[eid] = self.store.intern(url)
        if title is not None:
            self.store.inline_title[eid] = self.store.intern(title)
        handle = _InlineHandle(self.store, eid)
        for item in children:
            if isinstance(item, str):
                _add_text(self.store, eid, item)
            else:
                _adopt_inline(self.store, eid, item)
        return handle

    def image(self, url: str, alt: str, title: str | None = None) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.IMAGE)
        self.store.inline_url[eid] = self.store.intern(url)
        self.store.inline_text[eid] = self.store.intern(alt)
        if title is not None:
            self.store.inline_title[eid] = self.store.intern(title)
        return _InlineHandle(self.store, eid)

    def line_break(self) -> _InlineHandle:
        eid = self.store.alloc_node(InlineType.LINE_BREAK)
        return _InlineHandle(self.store, eid)
