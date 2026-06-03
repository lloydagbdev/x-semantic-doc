#!/usr/bin/env python3
"""Block-based structured editor server for semantic document IR."""

import json
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_doc.ir import Builder, DocumentStore
from semantic_doc.ir.types import BlockType, InlineType, ListType, AdmonType
from semantic_doc.serializers import from_dict, from_json, to_dict, to_json
from semantic_doc.vcs import Repository
from semantic_doc.vcs.diff import semantic_diff
from semantic_doc.adapters import load as adapter_load

EDITOR_DIR = Path(__file__).parent
_repo = None
_current_store = None
_history = []
_history_index = -1
_MAX_HISTORY = 50


def get_repo():
    global _repo
    if _repo is None:
        repo_path = EDITOR_DIR / ".editor_repo"
        if not repo_path.exists():
            _repo = Repository.init(str(repo_path))
        else:
            _repo = Repository.open(str(repo_path))
    return _repo


def get_current_store():
    global _current_store
    if _current_store is None:
        b = Builder()
        b.title("Untitled Document")
        s = b.section(1, "Introduction")
        s.paragraph("Start typing here...")
        _current_store = b.build()
    return _current_store


def set_current_store(store, track_history=True):
    global _current_store, _history, _history_index
    if track_history and _current_store is not None:
        _history = _history[:_history_index + 1]
        _history.append(to_dict(_current_store))
        if len(_history) > _MAX_HISTORY:
            _history = _history[-_MAX_HISTORY:]
        _history_index = len(_history) - 1
    _current_store = store


def undo():
    global _current_store, _history_index
    if _history_index > 0:
        _history_index -= 1
        _current_store = from_dict(_history[_history_index])
        return True
    return False


def redo():
    global _current_store, _history_index
    if _history_index < len(_history) - 1:
        _history_index += 1
        _current_store = from_dict(_history[_history_index])
        return True
    return False


def _serialize_store(store):
    data = to_dict(store)
    data["blocks"] = _build_block_tree(store)
    return data


def _build_block_tree(store):
    blocks = []
    for eid in store._root_children():
        blocks.append(_build_block(store, eid))
    return blocks


def _build_block(store, eid):
    node = store.node_type[eid]
    block = {
        "eid": eid,
        "type": node.value,
        "children": [],
    }

    if node == BlockType.SECTION:
        level = store.block_level.get(eid, 1)
        block["level"] = level
        block["title"] = _collect_text(store, eid)

    elif node == BlockType.PARAGRAPH:
        block["content"] = _collect_text(store, eid)

    elif node == BlockType.CODE_BLOCK:
        lang_idx = store.block_language.get(eid, -1)
        block["language"] = store.text(lang_idx) if lang_idx >= 0 else ""
        content_idx = store.block_content.get(eid, -1)
        block["content"] = store.text(content_idx) if content_idx >= 0 else ""

    elif node == BlockType.LIST:
        lt = store.block_list_type.get(eid, ListType.UNORDERED)
        block["list_type"] = lt.value
        for cid in store.children(eid):
            if store.node_type[cid] == BlockType.LIST_ITEM:
                checked = store.block_checked.get(cid, None)
                item = {
                    "eid": cid,
                    "content": _collect_text(store, cid),
                }
                if checked is not None:
                    item["checked"] = checked
                block["children"].append(item)

    elif node == BlockType.BLOCKQUOTE:
        block["content"] = _collect_text(store, eid)

    elif node == BlockType.TABLE:
        rows = []
        for rid in store.children(eid):
            if store.node_type[rid] == BlockType.TABLE_ROW:
                cells = []
                for cid in store.children(rid):
                    if store.node_type[cid] == BlockType.TABLE_CELL:
                        cells.append(_collect_text(store, cid))
                rows.append(cells)
        block["rows"] = rows

    elif node == BlockType.ADMONITION:
        at = store.block_admon_type.get(eid, AdmonType.NOTE)
        block["admon_type"] = at.value
        block["content"] = _collect_text(store, eid)

    elif node == BlockType.THEMATIC_BREAK:
        pass

    return block


def _collect_text(store, eid):
    parts = []
    for cid in store.children(eid):
        if store.node_type[cid] == InlineType.TEXT:
            t = store.inline_text.get(cid, -1)
            if t >= 0:
                parts.append(store.text(t))
    return " ".join(parts)


class EditorHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(EDITOR_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/document":
            self._send_json(_serialize_store(get_current_store()))

        elif parsed.path == "/api/log":
            repo = get_repo()
            commits = repo.log()
            self._send_json([c.to_dict() for c in commits])

        elif parsed.path == "/api/diff":
            repo = get_repo()
            current_hash = repo.get_current_tree_hash()
            if current_hash:
                store1 = repo.get_store(current_hash)
            else:
                store1 = get_current_store()
            store2 = get_current_store()
            diff = semantic_diff(store1, store2)
            self._send_json({
                "ops": [str(op) for op in diff.ops],
                "stats": {
                    "added": diff.stats.added,
                    "removed": diff.stats.removed,
                    "modified": diff.stats.modified,
                },
                "is_clean": diff.is_clean,
            })

        elif parsed.path == "/api/branches":
            repo = get_repo()
            self._send_json({"branches": repo.list_branches(), "current": repo.head_ref})

        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        data = json.loads(body) if body else {}

        if parsed.path == "/api/document":
            store = from_dict(data)
            set_current_store(store)
            self._send_json({"status": "ok"})

        elif parsed.path == "/api/commit":
            repo = get_repo()
            commit = repo.commit(get_current_store(), message=data.get("message", "Editor commit"))
            self._send_json({"status": "ok", "commit": commit.to_dict()})

        elif parsed.path == "/api/insert_block":
            store = get_current_store()
            block_type = data.get("type", "paragraph")
            after_eid = data.get("after")
            parent_eid = data.get("parent")
            content = data.get("content", "")
            language = data.get("language", "")
            level = data.get("level", 1)
            list_type = data.get("list_type", "unordered")
            admon_type = data.get("admon_type", "note")

            if block_type == "section":
                eid = store._alloc_root_node(BlockType.SECTION)
                store.block_level[eid] = level
                if content:
                    text_eid = store.alloc_node(InlineType.TEXT, parent=eid)
                    store.inline_text[text_eid] = store.intern(content)
            elif block_type == "paragraph":
                eid = store._alloc_root_node(BlockType.PARAGRAPH)
                if content:
                    text_eid = store.alloc_node(InlineType.TEXT, parent=eid)
                    store.inline_text[text_eid] = store.intern(content)
            elif block_type == "code_block":
                eid = store._alloc_root_node(BlockType.CODE_BLOCK)
                if language:
                    store.block_language[eid] = store.intern(language)
                store.block_content[eid] = store.intern(content)
            elif block_type == "list":
                eid = store._alloc_root_node(BlockType.LIST)
                store.block_list_type[eid] = ListType(list_type)
            elif block_type == "blockquote":
                eid = store._alloc_root_node(BlockType.BLOCKQUOTE)
                if content:
                    text_eid = store.alloc_node(InlineType.TEXT, parent=eid)
                    store.inline_text[text_eid] = store.intern(content)
            elif block_type == "table":
                eid = store._alloc_root_node(BlockType.TABLE)
            elif block_type == "admonition":
                eid = store._alloc_root_node(BlockType.ADMONITION)
                store.block_admon_type[eid] = AdmonType(admon_type)
                if content:
                    text_eid = store.alloc_node(InlineType.TEXT, parent=eid)
                    store.inline_text[text_eid] = store.intern(content)
            elif block_type == "thematic_break":
                eid = store._alloc_root_node(BlockType.THEMATIC_BREAK)
            else:
                self._send_json({"status": "error", "message": f"Unknown block type: {block_type}"}, 400)
                return

            set_current_store(store)
            self._send_json({"status": "ok", "eid": eid, "document": _serialize_store(store)})

        elif parsed.path == "/api/delete_block":
            store = get_current_store()
            eid = data.get("eid")
            if eid is None:
                self._send_json({"status": "error", "message": "No eid"}, 400)
                return
            _delete_node(store, eid)
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/update_block":
            store = get_current_store()
            eid = data.get("eid")
            if eid is None:
                self._send_json({"status": "error", "message": "No eid"}, 400)
                return
            ntype = store.node_type[eid]

            if "content" in data:
                if ntype in (BlockType.PARAGRAPH, BlockType.BLOCKQUOTE, BlockType.ADMONITION):
                    _set_block_text(store, eid, data["content"])
                elif ntype == BlockType.SECTION:
                    _set_section_title(store, eid, data["content"])

            if "language" in data and ntype == BlockType.CODE_BLOCK:
                store.block_language[eid] = store.intern(data["language"])

            if "code_content" in data and ntype == BlockType.CODE_BLOCK:
                store.block_content[eid] = store.intern(data["code_content"])

            if "level" in data and ntype == BlockType.SECTION:
                store.block_level[eid] = int(data["level"])

            if "list_type" in data and ntype == BlockType.LIST:
                store.block_list_type[eid] = ListType(data["list_type"])

            if "admon_type" in data and ntype == BlockType.ADMONITION:
                store.block_admon_type[eid] = AdmonType(data["admon_type"])

            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/add_list_item":
            store = get_current_store()
            list_eid = data.get("list_eid")
            content = data.get("content", "New item")
            checked = data.get("checked")
            if list_eid is None:
                self._send_json({"status": "error", "message": "No list_eid"}, 400)
                return
            item_eid = store.alloc_node(BlockType.LIST_ITEM, parent=list_eid)
            text_eid = store.alloc_node(InlineType.TEXT, parent=item_eid)
            store.inline_text[text_eid] = store.intern(content)
            if checked is not None:
                store.block_checked[item_eid] = checked
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/delete_list_item":
            store = get_current_store()
            item_eid = data.get("eid")
            if item_eid is None:
                self._send_json({"status": "error", "message": "No eid"}, 400)
                return
            _delete_node(store, item_eid)
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/update_list_item":
            store = get_current_store()
            item_eid = data.get("eid")
            if item_eid is None:
                self._send_json({"status": "error", "message": "No eid"}, 400)
                return
            if "content" in data:
                _set_block_text(store, item_eid, data["content"])
            if "checked" in data:
                store.block_checked[item_eid] = bool(data["checked"])
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/add_table_row":
            store = get_current_store()
            table_eid = data.get("table_eid")
            num_cols = data.get("num_cols", 2)
            if table_eid is None:
                self._send_json({"status": "error", "message": "No table_eid"}, 400)
                return
            row_eid = store.alloc_node(BlockType.TABLE_ROW, parent=table_eid)
            for _ in range(num_cols):
                cell_eid = store.alloc_node(BlockType.TABLE_CELL, parent=row_eid)
                text_eid = store.alloc_node(InlineType.TEXT, parent=cell_eid)
                store.inline_text[text_eid] = store.intern("")
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/update_table_cell":
            store = get_current_store()
            cell_eid = data.get("cell_eid")
            content = data.get("content", "")
            if cell_eid is None:
                self._send_json({"status": "error", "message": "No cell_eid"}, 400)
                return
            _set_block_text(store, cell_eid, content)
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/delete_table_row":
            store = get_current_store()
            row_eid = data.get("row_eid")
            if row_eid is None:
                self._send_json({"status": "error", "message": "No row_eid"}, 400)
                return
            _delete_node(store, row_eid)
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/new":
            b = Builder()
            b.title("Untitled Document")
            s = b.section(1, "Introduction")
            s.paragraph("Start typing here...")
            set_current_store(b.build())
            self._send_json({"status": "ok", "document": _serialize_store(get_current_store())})

        elif parsed.path == "/api/load":
            content = data.get("content", "")
            fmt = data.get("format", "markdown")
            try:
                if fmt == "json":
                    store = from_json(content)
                else:
                    store = adapter_load(content)
                set_current_store(store)
                self._send_json({"status": "ok", "document": _serialize_store(store)})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 400)

        elif parsed.path == "/api/branch":
            repo = get_repo()
            action = data.get("action")
            name = data.get("name")
            if action == "create":
                repo.create_branch(name)
            elif action == "switch":
                repo.switch_branch(name)
                current_hash = repo.head_commit_hash
                if current_hash:
                    commit = repo.get_commit(current_hash)
                    store = repo.get_store(commit.tree_hash)
                    set_current_store(store)
            elif action == "delete":
                repo.delete_branch(name)
            self._send_json({"status": "ok", "document": _serialize_store(get_current_store())})

        elif parsed.path == "/api/move_block":
            store = get_current_store()
            eid = data.get("eid")
            direction = data.get("direction", "up")
            if eid is None:
                self._send_json({"status": "error", "message": "No eid"}, 400)
                return
            node = store.node_type[eid] if eid < store.entity_count else None
            if node is None:
                self._send_json({"status": "error", "message": "Node not found"}, 400)
                return
            parent = store.node_parent[eid]
            if direction == "up":
                prev = store.node_prev[eid]
                if prev != -1:
                    _swap_siblings(store, prev, eid, parent)
            else:
                next_ = store.node_next[eid]
                if next_ != -1:
                    _swap_siblings(store, eid, next_, parent)
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/convert_block":
            store = get_current_store()
            eid = data.get("eid")
            new_type = data.get("new_type")
            if eid is None or new_type is None:
                self._send_json({"status": "error", "message": "Missing params"}, 400)
                return
            old_type = store.node_type[eid]
            content = _collect_text(store, eid)
            parent = store.node_parent[eid]
            _delete_node(store, eid)
            type_map = {
                "paragraph": BlockType.PARAGRAPH,
                "section": BlockType.SECTION,
                "code_block": BlockType.CODE_BLOCK,
                "blockquote": BlockType.BLOCKQUOTE,
                "list": BlockType.LIST,
                "admonition": BlockType.ADMONITION,
                "thematic_break": BlockType.THEMATIC_BREAK,
            }
            bt = type_map.get(new_type)
            if bt is None:
                self._send_json({"status": "error", "message": f"Unknown type: {new_type}"}, 400)
                return
            if parent == -1:
                new_eid = store._alloc_root_node(bt)
            else:
                new_eid = store.alloc_node(bt, parent=parent)
            if bt == BlockType.SECTION:
                store.block_level[new_eid] = 1
                if content:
                    t = store.alloc_node(InlineType.TEXT, parent=new_eid)
                    store.inline_text[t] = store.intern(content)
            elif bt in (BlockType.PARAGRAPH, BlockType.BLOCKQUOTE, BlockType.ADMONITION):
                if content:
                    t = store.alloc_node(InlineType.TEXT, parent=new_eid)
                    store.inline_text[t] = store.intern(content)
            elif bt == BlockType.CODE_BLOCK:
                store.block_content[new_eid] = store.intern(content)
            elif bt == BlockType.ADMONITION:
                store.block_admon_type[new_eid] = AdmonType.NOTE
            elif bt == BlockType.LIST:
                store.block_list_type[new_eid] = ListType.UNORDERED
            set_current_store(store)
            self._send_json({"status": "ok", "eid": new_eid, "document": _serialize_store(store)})

        elif parsed.path == "/api/add_table_column":
            store = get_current_store()
            table_eid = data.get("table_eid")
            if table_eid is None:
                self._send_json({"status": "error", "message": "No table_eid"}, 400)
                return
            for rid in store.children(table_eid):
                if store.node_type[rid] == BlockType.TABLE_ROW:
                    cell_eid = store.alloc_node(BlockType.TABLE_CELL, parent=rid)
                    text_eid = store.alloc_node(InlineType.TEXT, parent=cell_eid)
                    store.inline_text[text_eid] = store.intern("")
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/delete_table_column":
            store = get_current_store()
            table_eid = data.get("table_eid")
            col_idx = data.get("col_idx", 0)
            if table_eid is None:
                self._send_json({"status": "error", "message": "No table_eid"}, 400)
                return
            for rid in store.children(table_eid):
                if store.node_type[rid] == BlockType.TABLE_ROW:
                    cells = store.children(rid)
                    if col_idx < len(cells):
                        _delete_node(store, cells[col_idx])
            set_current_store(store)
            self._send_json({"status": "ok", "document": _serialize_store(store)})

        elif parsed.path == "/api/undo":
            if undo():
                self._send_json({"status": "ok", "document": _serialize_store(get_current_store())})
            else:
                self._send_json({"status": "ok", "message": "Nothing to undo"})

        elif parsed.path == "/api/redo":
            if redo():
                self._send_json({"status": "ok", "document": _serialize_store(get_current_store())})
            else:
                self._send_json({"status": "ok", "message": "Nothing to redo"})

        elif parsed.path == "/api/insert_block_after":
            store = get_current_store()
            after_eid = data.get("after")
            block_type = data.get("type", "paragraph")
            content = data.get("content", "")
            language = data.get("language", "")
            level = data.get("level", 1)
            list_type = data.get("list_type", "unordered")
            admon_type = data.get("admon_type", "note")
            parent_eid = data.get("parent")

            if after_eid is not None and after_eid >= 0:
                after_node_type = store.node_type[after_eid] if after_eid < store.entity_count else None
                if after_node_type:
                    parent_eid = store.node_parent[after_eid]

            type_map = {
                "paragraph": BlockType.PARAGRAPH,
                "section": BlockType.SECTION,
                "code_block": BlockType.CODE_BLOCK,
                "list": BlockType.LIST,
                "blockquote": BlockType.BLOCKQUOTE,
                "table": BlockType.TABLE,
                "admonition": BlockType.ADMONITION,
                "thematic_break": BlockType.THEMATIC_BREAK,
            }
            bt = type_map.get(block_type)
            if bt is None:
                self._send_json({"status": "error", "message": f"Unknown type: {block_type}"}, 400)
                return

            if parent_eid is not None and parent_eid >= 0:
                eid = store.alloc_node(bt, parent=parent_eid)
            else:
                eid = store._alloc_root_node(bt)

            if bt == BlockType.SECTION:
                store.block_level[eid] = level
            elif bt == BlockType.CODE_BLOCK:
                if language:
                    store.block_language[eid] = store.intern(language)
                store.block_content[eid] = store.intern(content)
            elif bt == BlockType.LIST:
                store.block_list_type[eid] = ListType(list_type)
            elif bt == BlockType.ADMONITION:
                store.block_admon_type[eid] = AdmonType(admon_type)

            if content and bt in (BlockType.PARAGRAPH, BlockType.SECTION, BlockType.BLOCKQUOTE, BlockType.ADMONITION):
                t = store.alloc_node(InlineType.TEXT, parent=eid)
                store.inline_text[t] = store.intern(content)

            set_current_store(store)
            self._send_json({"status": "ok", "eid": eid, "document": _serialize_store(store)})

        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def _delete_node(store, eid):
    parent = store.node_parent[eid]
    prev = store.node_prev[eid]
    next_ = store.node_next[eid]

    if prev != -1:
        store.node_next[prev] = next_
    if next_ != -1:
        store.node_prev[next_] = prev

    if parent == -1:
        if store.root_first == eid:
            store.root_first = next_ if next_ != -1 else -1
    else:
        if store.node_first_child[parent] == eid:
            store.node_first_child[parent] = next_ if next_ != -1 else -1

    children_to_delete = list(store.children(eid))
    for child_eid in children_to_delete:
        _delete_node(store, child_eid)


def _set_block_text(store, eid, text):
    text_child = None
    for cid in store.children(eid):
        if store.node_type[cid] == InlineType.TEXT:
            text_child = cid
            break
    if text_child is None:
        text_child = store.alloc_node(InlineType.TEXT, parent=eid)
    store.inline_text[text_child] = store.intern(text)


def _set_section_title(store, eid, text):
    text_child = None
    for cid in store.children(eid):
        if store.node_type[cid] == InlineType.TEXT:
            text_child = cid
            break
    if text_child is None:
        text_child = store.alloc_node(InlineType.TEXT, parent=eid)
    store.inline_text[text_child] = store.intern(text)


def _swap_siblings(store, a, b, parent):
    a_prev = store.node_prev[a]
    a_next = store.node_next[a]
    b_prev = store.node_prev[b]
    b_next = store.node_next[b]

    store.node_prev[a] = b_prev
    store.node_next[a] = b_next
    store.node_prev[b] = a_prev
    store.node_next[b] = a_next

    if a_prev != -1:
        store.node_next[a_prev] = b
    if b_next != -1:
        store.node_prev[b_next] = a

    if parent == -1:
        if store.root_first == a:
            store.root_first = b
        elif store.root_first == b:
            store.root_first = a
    else:
        if store.node_first_child[parent] == a:
            store.node_first_child[parent] = b
        elif store.node_first_child[parent] == b:
            store.node_first_child[parent] = a


def main():
    port = 8765
    server = HTTPServer(("127.0.0.1", port), EditorHandler)
    print(f"Editor server running at http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
