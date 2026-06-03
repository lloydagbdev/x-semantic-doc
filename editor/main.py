"""Desktop semantic document editor — pywebview frontend over Python IR."""

from __future__ import annotations

import sys
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_doc.ir import Builder, DocumentStore
from semantic_doc.ir.types import (
    AdmonType, BlockType, InlineType, ListType,
    BLOCK_TYPES, INLINE_TYPES,
)
from semantic_doc.serializers import from_dict, to_dict
from semantic_doc.vcs import Repository
from semantic_doc.vcs.diff import semantic_diff
from semantic_doc.adapters import load as adapter_load

_NONE = -1
_MAX_HISTORY = 100
APP_DIR = Path(__file__).parent / "app"


# ── IR serialization ─────────────────────────────────────────────────────────

def _ser_inlines(store: DocumentStore, eid: int) -> list:
    result = []
    for cid in store.children(eid):
        nt = store.node_type[cid]
        if nt == InlineType.TEXT:
            t = store.inline_text.get(cid, _NONE)
            result.append({"type": "text", "text": store.text(t) if t >= 0 else ""})
        elif nt == InlineType.EMPHASIS:
            result.append({"type": "emphasis", "children": _ser_inlines(store, cid)})
        elif nt == InlineType.STRONG:
            result.append({"type": "strong", "children": _ser_inlines(store, cid)})
        elif nt == InlineType.INLINE_CODE:
            t = store.inline_text.get(cid, _NONE)
            result.append({"type": "inline_code", "text": store.text(t) if t >= 0 else ""})
        elif nt == InlineType.LINK:
            url = store.inline_url.get(cid, _NONE)
            result.append({
                "type": "link",
                "url": store.text(url) if url >= 0 else "",
                "children": _ser_inlines(store, cid),
            })
        elif nt == InlineType.IMAGE:
            url = store.inline_url.get(cid, _NONE)
            alt = store.inline_text.get(cid, _NONE)
            result.append({
                "type": "image",
                "url": store.text(url) if url >= 0 else "",
                "alt": store.text(alt) if alt >= 0 else "",
            })
        elif nt == InlineType.LINE_BREAK:
            result.append({"type": "line_break"})
    return result


def _ser_block(store: DocumentStore, eid: int) -> dict:
    nt = store.node_type[eid]
    b: dict = {"eid": eid, "type": nt.value}

    if nt == BlockType.SECTION:
        b["level"] = store.block_level.get(eid, 1)
        b["inlines"] = _ser_inlines(store, eid)
        b["children"] = [
            _ser_block(store, cid)
            for cid in store.children(eid)
            if store.node_type[cid] in BLOCK_TYPES
        ]
    elif nt == BlockType.PARAGRAPH:
        b["inlines"] = _ser_inlines(store, eid)
    elif nt == BlockType.CODE_BLOCK:
        lang = store.block_language.get(eid, _NONE)
        b["language"] = store.text(lang) if lang >= 0 else ""
        body = store.block_content.get(eid, _NONE)
        b["content"] = store.text(body) if body >= 0 else ""
    elif nt == BlockType.LIST:
        b["list_type"] = store.block_list_type.get(eid, ListType.UNORDERED).value
        b["items"] = [
            {
                "eid": cid,
                "inlines": _ser_inlines(store, cid),
                **({"checked": store.block_checked[cid]}
                   if cid in store.block_checked else {}),
            }
            for cid in store.children(eid)
            if store.node_type[cid] == BlockType.LIST_ITEM
        ]
    elif nt == BlockType.BLOCKQUOTE:
        b["inlines"] = _ser_inlines(store, eid)
    elif nt == BlockType.TABLE:
        b["rows"] = [
            {
                "eid": rid,
                "cells": [
                    {"eid": cid, "inlines": _ser_inlines(store, cid)}
                    for cid in store.children(rid)
                    if store.node_type[cid] == BlockType.TABLE_CELL
                ],
            }
            for rid in store.children(eid)
            if store.node_type[rid] == BlockType.TABLE_ROW
        ]
    elif nt == BlockType.ADMONITION:
        b["admon_type"] = store.block_admon_type.get(eid, AdmonType.NOTE).value
        b["inlines"] = _ser_inlines(store, eid)

    return b


def _ser_doc(store: DocumentStore) -> dict:
    t = store.meta_title
    return {
        "title": store.text(t) if t >= 0 else "",
        "blocks": [_ser_block(store, eid) for eid in store._root_children()],
    }


# ── IR mutation helpers ───────────────────────────────────────────────────────

def _remove_node(store: DocumentStore, eid: int) -> None:
    prev = store.node_prev[eid]
    next_ = store.node_next[eid]
    parent = store.node_parent[eid]
    if prev != _NONE:
        store.node_next[prev] = next_
    if next_ != _NONE:
        store.node_prev[next_] = prev
    if parent == _NONE:
        if store.root_first == eid:
            store.root_first = next_
    else:
        if store.node_first_child[parent] == eid:
            store.node_first_child[parent] = next_
    for cid in list(store.children(eid)):
        _remove_node(store, cid)


def _clear_inlines(store: DocumentStore, eid: int) -> None:
    for cid in list(store.children(eid)):
        if store.node_type[cid] in INLINE_TYPES:
            _remove_node(store, cid)


def _add_inline(store: DocumentStore, parent: int, node: dict) -> None:
    t = node.get("type")
    if t == "text":
        eid = store.alloc_node(InlineType.TEXT, parent=parent)
        store.inline_text[eid] = store.intern(node.get("text", ""))
    elif t == "strong":
        eid = store.alloc_node(InlineType.STRONG, parent=parent)
        for child in node.get("children", []):
            _add_inline(store, eid, child)
    elif t == "emphasis":
        eid = store.alloc_node(InlineType.EMPHASIS, parent=parent)
        for child in node.get("children", []):
            _add_inline(store, eid, child)
    elif t == "inline_code":
        eid = store.alloc_node(InlineType.INLINE_CODE, parent=parent)
        store.inline_text[eid] = store.intern(node.get("text", ""))
    elif t == "link":
        eid = store.alloc_node(InlineType.LINK, parent=parent)
        store.inline_url[eid] = store.intern(node.get("url", ""))
        for child in node.get("children", []):
            _add_inline(store, eid, child)
    elif t == "line_break":
        store.alloc_node(InlineType.LINE_BREAK, parent=parent)
    else:
        eid = store.alloc_node(InlineType.TEXT, parent=parent)
        store.inline_text[eid] = store.intern(node.get("text", ""))


def _apply_inlines(store: DocumentStore, eid: int, nodes: list) -> None:
    _clear_inlines(store, eid)
    for node in nodes:
        _add_inline(store, eid, node)


# ── API ───────────────────────────────────────────────────────────────────────

class EditorAPI:
    def __init__(self):
        self._store: DocumentStore | None = None
        self._history: list[dict] = []
        self._idx: int = -1
        self._repo: Repository | None = None
        self._repo_path = Path(__file__).parent / ".editor_repo"
        self._init_store()

    def _init_store(self) -> None:
        b = Builder()
        b.title("Untitled")
        s = b.section(1, "Introduction")
        s.paragraph("Start writing here.")
        self._store = b.build()
        self._push()

    def _push(self) -> None:
        self._history = self._history[: self._idx + 1]
        self._history.append(to_dict(self._store))
        if len(self._history) > _MAX_HISTORY:
            self._history = self._history[-_MAX_HISTORY:]
        self._idx = len(self._history) - 1

    def _repo_(self) -> Repository:
        if self._repo is None:
            if not self._repo_path.exists():
                self._repo = Repository.init(str(self._repo_path))
            else:
                self._repo = Repository.open(str(self._repo_path))
        return self._repo

    # ── Document ─────────────────────────────────────────────────────────────

    def get_document(self) -> dict:
        return _ser_doc(self._store)

    def update_title(self, title: str) -> dict:
        self._store.meta_title = self._store.intern(title)
        self._push()
        return {"ok": True}

    def update_inline(self, eid: int, nodes: list) -> dict:
        _apply_inlines(self._store, eid, nodes)
        self._push()
        return {"ok": True}

    def update_code(self, eid: int, content: str, language: str = "") -> dict:
        self._store.block_content[eid] = self._store.intern(content)
        self._store.block_language[eid] = self._store.intern(language)
        self._push()
        return {"ok": True}

    def update_table_cell(self, eid: int, nodes: list) -> dict:
        _apply_inlines(self._store, eid, nodes)
        self._push()
        return {"ok": True}

    # ── Block structure ───────────────────────────────────────────────────────

    def insert_block(self, block_type: str, after_eid: int = -1, opts: dict | None = None) -> dict:
        if opts is None:
            opts = {}
        _type_map = {
            "paragraph": BlockType.PARAGRAPH,
            "section": BlockType.SECTION,
            "code_block": BlockType.CODE_BLOCK,
            "list": BlockType.LIST,
            "blockquote": BlockType.BLOCKQUOTE,
            "table": BlockType.TABLE,
            "admonition": BlockType.ADMONITION,
            "thematic_break": BlockType.THEMATIC_BREAK,
        }
        bt = _type_map.get(block_type)
        if bt is None:
            return {"ok": False, "error": f"Unknown: {block_type}"}

        s = self._store
        if 0 <= after_eid < s.entity_count:
            eid = s.insert_after(bt, after_eid)
        else:
            eid = s._alloc_root_node(bt)

        if bt == BlockType.SECTION:
            s.block_level[eid] = int(opts.get("level", 2))
        elif bt == BlockType.CODE_BLOCK:
            s.block_content[eid] = s.intern("")
            s.block_language[eid] = s.intern(str(opts.get("language", "")))
        elif bt == BlockType.LIST:
            s.block_list_type[eid] = ListType(opts.get("list_type", "unordered"))
        elif bt == BlockType.ADMONITION:
            s.block_admon_type[eid] = AdmonType(opts.get("admon_type", "note"))
        elif bt == BlockType.TABLE:
            for _ in range(2):
                rid = s.alloc_node(BlockType.TABLE_ROW, parent=eid)
                for _ in range(3):
                    cid = s.alloc_node(BlockType.TABLE_CELL, parent=rid)
                    tid = s.alloc_node(InlineType.TEXT, parent=cid)
                    s.inline_text[tid] = s.intern("")

        self._push()
        return {"ok": True, "eid": eid, "document": _ser_doc(s)}

    def delete_block(self, eid: int) -> dict:
        _remove_node(self._store, eid)
        self._push()
        return {"ok": True, "document": _ser_doc(self._store)}

    def move_block(self, eid: int, direction: str) -> dict:
        s = self._store
        if direction == "up":
            prev = s.node_prev[eid]
            if prev != _NONE:
                self._swap(prev, eid)
        else:
            nxt = s.node_next[eid]
            if nxt != _NONE:
                self._swap(eid, nxt)
        self._push()
        return {"ok": True, "document": _ser_doc(s)}

    def _swap(self, a: int, b: int) -> None:
        s = self._store
        a_prev, b_next = s.node_prev[a], s.node_next[b]
        parent = s.node_parent[a]
        s.node_prev[b] = a_prev
        s.node_next[b] = a
        s.node_prev[a] = b
        s.node_next[a] = b_next
        if a_prev != _NONE:
            s.node_next[a_prev] = b
        if b_next != _NONE:
            s.node_prev[b_next] = a
        if parent == _NONE:
            if s.root_first == a:
                s.root_first = b
        else:
            if s.node_first_child[parent] == a:
                s.node_first_child[parent] = b

    def convert_block(self, eid: int, new_type: str, opts: dict | None = None) -> dict:
        """Convert a block to a different type in place (used by markdown triggers)."""
        if opts is None:
            opts = {}
        type_map = {
            "paragraph": BlockType.PARAGRAPH,
            "section": BlockType.SECTION,
            "code_block": BlockType.CODE_BLOCK,
            "list": BlockType.LIST,
            "blockquote": BlockType.BLOCKQUOTE,
            "thematic_break": BlockType.THEMATIC_BREAK,
            "admonition": BlockType.ADMONITION,
        }
        bt = type_map.get(new_type)
        if bt is None:
            return {"ok": False, "error": f"Unknown type: {new_type}"}
        s = self._store
        s.node_type[eid] = bt
        _clear_inlines(s, eid)
        if bt == BlockType.SECTION:
            s.block_level[eid] = int(opts.get("level", 1))
        elif bt == BlockType.CODE_BLOCK:
            s.block_content[eid] = s.intern("")
            s.block_language[eid] = s.intern("")
        elif bt == BlockType.LIST:
            s.block_list_type[eid] = ListType(opts.get("list_type", "unordered"))
            ieid = s.alloc_node(BlockType.LIST_ITEM, parent=eid)
            tid = s.alloc_node(InlineType.TEXT, parent=ieid)
            s.inline_text[tid] = s.intern("")
        elif bt == BlockType.ADMONITION:
            s.block_admon_type[eid] = AdmonType(opts.get("admon_type", "note"))
        self._push()
        return {"ok": True, "eid": eid, "document": _ser_doc(s)}

    def set_section_level(self, eid: int, level: int) -> dict:
        self._store.block_level[eid] = int(level)
        self._push()
        return {"ok": True}

    def set_list_type(self, eid: int, list_type: str) -> dict:
        self._store.block_list_type[eid] = ListType(list_type)
        self._push()
        return {"ok": True}

    def set_admon_type(self, eid: int, admon_type: str) -> dict:
        self._store.block_admon_type[eid] = AdmonType(admon_type)
        self._push()
        return {"ok": True}

    def add_list_item(self, list_eid: int, after_item_eid: int = -1) -> dict:
        s = self._store
        if 0 <= after_item_eid < s.entity_count:
            ieid = s.insert_after(BlockType.LIST_ITEM, after_item_eid)
        else:
            ieid = s.alloc_node(BlockType.LIST_ITEM, parent=list_eid)
        tid = s.alloc_node(InlineType.TEXT, parent=ieid)
        s.inline_text[tid] = s.intern("")
        if s.block_list_type.get(list_eid) == ListType.CHECKLIST:
            s.block_checked[ieid] = False
        self._push()
        return {"ok": True, "item_eid": ieid, "document": _ser_doc(s)}

    def delete_list_item(self, eid: int) -> dict:
        _remove_node(self._store, eid)
        self._push()
        return {"ok": True, "document": _ser_doc(self._store)}

    def toggle_checked(self, eid: int) -> dict:
        cur = self._store.block_checked.get(eid, False)
        self._store.block_checked[eid] = not cur
        self._push()
        return {"ok": True, "checked": not cur}

    def add_table_row(self, table_eid: int) -> dict:
        s = self._store
        rows = [c for c in s.children(table_eid) if s.node_type[c] == BlockType.TABLE_ROW]
        ncols = len(s.children(rows[0])) if rows else 3
        rid = s.alloc_node(BlockType.TABLE_ROW, parent=table_eid)
        for _ in range(ncols):
            cid = s.alloc_node(BlockType.TABLE_CELL, parent=rid)
            tid = s.alloc_node(InlineType.TEXT, parent=cid)
            s.inline_text[tid] = s.intern("")
        self._push()
        return {"ok": True, "document": _ser_doc(s)}

    def add_table_col(self, table_eid: int) -> dict:
        s = self._store
        for rid in s.children(table_eid):
            if s.node_type[rid] == BlockType.TABLE_ROW:
                cid = s.alloc_node(BlockType.TABLE_CELL, parent=rid)
                tid = s.alloc_node(InlineType.TEXT, parent=cid)
                s.inline_text[tid] = s.intern("")
        self._push()
        return {"ok": True, "document": _ser_doc(s)}

    # ── Undo / Redo ──────────────────────────────────────────────────────────

    def undo(self) -> dict:
        if self._idx > 0:
            self._idx -= 1
            self._store = from_dict(self._history[self._idx])
            return {"ok": True, "document": _ser_doc(self._store)}
        return {"ok": False}

    def redo(self) -> dict:
        if self._idx < len(self._history) - 1:
            self._idx += 1
            self._store = from_dict(self._history[self._idx])
            return {"ok": True, "document": _ser_doc(self._store)}
        return {"ok": False}

    # ── VCS ──────────────────────────────────────────────────────────────────

    def commit(self, message: str) -> dict:
        c = self._repo_().commit(self._store, message=message)
        h = (getattr(c, "hash", None) or getattr(c, "tree_hash", ""))[:8]
        return {"ok": True, "hash": h}

    def get_diff(self) -> dict:
        repo = self._repo_()
        h = repo.get_current_tree_hash()
        old = repo.get_store(h) if h else self._store
        diff = semantic_diff(old, self._store)
        return {
            "is_clean": diff.is_clean,
            "ops": [str(op) for op in diff.ops],
            "stats": vars(diff.stats),
        }

    def get_log(self) -> list:
        commits = self._repo_().log()
        return [
            {
                "hash": (getattr(c, "hash", None) or getattr(c, "tree_hash", ""))[:8],
                "message": c.message,
                "author": c.author,
                "timestamp": c.timestamp,
            }
            for c in commits
        ]

    def get_branches(self) -> dict:
        repo = self._repo_()
        return {"branches": repo.list_branches(), "current": repo.head_ref}

    def create_branch(self, name: str) -> dict:
        self._repo_().create_branch(name)
        return {"ok": True}

    def switch_branch(self, name: str) -> dict:
        repo = self._repo_()
        repo.switch_branch(name)
        h = repo.head_commit_hash
        if h:
            self._store = repo.get_store(repo.get_commit(h).tree_hash)
            self._push()
        return {"ok": True, "document": _ser_doc(self._store)}

    def delete_branch(self, name: str) -> dict:
        self._repo_().delete_branch(name)
        return {"ok": True}

    def load_markdown(self, content: str) -> dict:
        try:
            self._store = adapter_load(content)
            self._push()
            return {"ok": True, "document": _ser_doc(self._store)}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    api = EditorAPI()
    webview.create_window(
        "Semantic Doc",
        str(APP_DIR / "index.html"),
        js_api=api,
        width=1280,
        height=800,
        min_size=(800, 600),
    )
    webview.start(debug=True)


if __name__ == "__main__":
    main()
