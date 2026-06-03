#!/usr/bin/env python3
"""Simple PoC editor server for semantic document IR."""

import json
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_doc.ir import Builder, DocumentStore
from semantic_doc.ir.types import BlockType, InlineType, ListType
from semantic_doc.serializers import from_dict, from_json, to_dict, to_json
from semantic_doc.vcs import Repository, semantic_diff
from semantic_doc.vcs.diff import semantic_diff as do_diff

EDITOR_DIR = Path(__file__).parent
_repo = None
_current_store = None


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
        b.section(1, "Introduction")
        b.paragraph("Start editing here...")
        _current_store = b.build()
    return _current_store


def set_current_store(store):
    global _current_store
    _current_store = store


class EditorHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/document":
            self._send_json(to_dict(get_current_store()))
        elif parsed.path == "/api/log":
            repo = get_repo()
            commits = repo.log()
            self._send_json([c.to_dict() for c in commits])
        elif parsed.path == "/api/diff":
            repo = get_repo()
            params = parse_qs(parsed.query)
            commit1 = params.get("commit1", [None])[0]
            commit2 = params.get("commit2", [None])[0]
            if commit1 and commit2:
                c1 = repo.get_commit(repo._resolve_commit(commit1))
                c2 = repo.get_commit(repo._resolve_commit(commit2))
                store1 = repo.get_store(c1.tree_hash)
                store2 = repo.get_store(c2.tree_hash)
            elif commit1:
                c1 = repo.get_commit(repo._resolve_commit(commit1))
                store1 = repo.get_store(c1.tree_hash)
                store2 = get_current_store()
            else:
                current_hash = repo.get_current_tree_hash()
                if current_hash:
                    store1 = repo.get_store(current_hash)
                else:
                    store1 = get_current_store()
                store2 = get_current_store()
            diff = do_diff(store1, store2)
            self._send_json({
                "ops": [str(op) for op in diff.ops],
                "stats": {
                    "added": diff.stats.added,
                    "removed": diff.stats.removed,
                    "modified": diff.stats.modified,
                    "moved": diff.stats.moved,
                    "renamed": diff.stats.renamed,
                },
                "is_clean": diff.is_clean,
            })
        elif parsed.path == "/api/branches":
            repo = get_repo()
            self._send_json({"branches": repo.list_branches(), "current": repo.head_ref})
        else:
            if parsed.path == "/" or parsed.path == "/index.html":
                self.path = str(EDITOR_DIR / "index.html")
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""

        if parsed.path == "/api/document":
            data = json.loads(body)
            store = from_dict(data)
            set_current_store(store)
            self._send_json({"status": "ok"})
        elif parsed.path == "/api/commit":
            data = json.loads(body)
            repo = get_repo()
            commit = repo.commit(get_current_store(), message=data.get("message", "Editor commit"))
            self._send_json({"status": "ok", "commit": commit.to_dict()})
        elif parsed.path == "/api/checkout":
            data = json.loads(body)
            repo = get_repo()
            target = data.get("target")
            try:
                store = repo.checkout(target)
                set_current_store(store)
                self._send_json({"status": "ok", "document": to_dict(store)})
            except ValueError as e:
                self._send_json({"status": "error", "message": str(e)}, 400)
        elif parsed.path == "/api/branch":
            data = json.loads(body)
            repo = get_repo()
            action = data.get("action")
            name = data.get("name")
            if action == "create":
                repo.create_branch(name)
                self._send_json({"status": "ok"})
            elif action == "switch":
                repo.switch_branch(name)
                current_hash = repo.head_commit_hash
                if current_hash:
                    commit = repo.get_commit(current_hash)
                    store = repo.get_store(commit.tree_hash)
                    set_current_store(store)
                self._send_json({"status": "ok", "document": to_dict(get_current_store())})
            elif action == "delete":
                repo.delete_branch(name)
                self._send_json({"status": "ok"})
        elif parsed.path == "/api/new":
            b = Builder()
            b.title("Untitled Document")
            b.section(1, "Introduction")
            b.paragraph("Start editing here...")
            set_current_store(b.build())
            self._send_json({"status": "ok", "document": to_dict(get_current_store())})
        elif parsed.path == "/api/load":
            data = json.loads(body)
            content = data.get("content", "")
            fmt = data.get("format", "json")
            try:
                if fmt == "json":
                    store = from_json(content)
                else:
                    from semantic_doc.adapters import load
                    store = load(content)
                set_current_store(store)
                self._send_json({"status": "ok", "document": to_dict(store)})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 400)
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
        pass  # Suppress default logging


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
