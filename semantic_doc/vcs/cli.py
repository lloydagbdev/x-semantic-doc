from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..ir.store import DocumentStore
from ..ir.types import PrivacyLevel
from .commit import Commit
from .diff import DiffResult
from .log import LogQuery
from .privacy import PrivacyAwareRepo, PrivacyContext
from .repo import Repository


def _format_commit(commit: Commit, short: bool = True) -> str:
    dt = datetime.fromtimestamp(commit.timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    hash_str = commit.short_hash() if short else commit.hash
    parent_str = ", ".join(p[:8] for p in commit.parents) if commit.parents else "(root)"
    lines = [
        f"commit {hash_str}",
        f"Author: {commit.author}",
        f"Date:   {dt}",
        f"Parent: {parent_str}",
        "",
        f"    {commit.message}",
    ]
    if commit.metadata:
        lines.append("")
        for k, v in commit.metadata.items():
            lines.append(f"    {k}: {v}")
    return "\n".join(lines)


def cmd_init(args):
    path = Path(args.path) if args.path else Path(".")
    semantic = path / ".semantic"
    if semantic.exists():
        print(f"Already initialized: {semantic}")
        return 0
    repo = Repository.init(path)
    print(f"Initialized empty semantic-doc repository in {repo.semantic}")
    return 0


def cmd_commit(args):
    repo = Repository.open(args.repo)
    store = _load_working_tree(args)
    if store is None:
        print("Error: No document to commit. Provide a file with -f or pipe content.", file=sys.stderr)
        return 1
    commit = repo.commit(store, message=args.message, author=args.author)
    print(f"[{repo.head_ref} {commit.short_hash()}] {commit.message}")
    return 0


def cmd_status(args):
    repo = Repository.open(args.repo)
    current_hash = repo.get_current_tree_hash()
    if current_hash is None:
        print("No commits yet.")
        return 0
    if args.file:
        store = _load_file(args.file)
        if store is None:
            print("Error: Cannot load file.", file=sys.stderr)
            return 1
    else:
        print("Working tree status: use -f <file> to compare against a document file.")
        return 0
    from .diff import semantic_diff
    current_store = repo.get_store(current_hash)
    diff = semantic_diff(current_store, store)
    if diff.is_clean:
        print("Working tree is clean.")
    else:
        print(diff.summary())
    return 0


def cmd_diff(args):
    repo = Repository.open(args.repo)
    commit1_hash = repo._resolve_commit(args.commit1) if args.commit1 else None
    commit2_hash = repo._resolve_commit(args.commit2) if args.commit2 else None
    if args.commit1 and commit1_hash is None:
        print(f"Error: Cannot resolve commit: {args.commit1}", file=sys.stderr)
        return 1
    if args.commit2 and commit2_hash is None:
        print(f"Error: Cannot resolve commit: {args.commit2}", file=sys.stderr)
        return 1
    if commit1_hash and commit2_hash:
        store_a = repo.get_store(repo.get_commit(commit1_hash).tree_hash)
        store_b = repo.get_store(repo.get_commit(commit2_hash).tree_hash)
    elif commit1_hash:
        current_hash = repo.get_current_tree_hash()
        if current_hash is None:
            print("Error: No commits yet.", file=sys.stderr)
            return 1
        store_a = repo.get_store(repo.get_commit(commit1_hash).tree_hash)
        if args.file:
            store_b = _load_file(args.file)
        else:
            store_b = repo.get_store(current_hash)
    else:
        current_hash = repo.get_current_tree_hash()
        if current_hash is None:
            print("Error: No commits yet.", file=sys.stderr)
            return 1
        store_a = repo.get_store(current_hash)
        if args.file:
            store_b = _load_file(args.file)
        else:
            print("Error: Provide a file with -f to diff against working tree.", file=sys.stderr)
            return 1
    if store_b is None:
        print("Error: Cannot load document.", file=sys.stderr)
        return 1
    from .diff import semantic_diff
    diff = semantic_diff(store_a, store_b)
    if diff.is_clean:
        print("No changes.")
    else:
        print(diff.summary())
    return 0


def cmd_log(args):
    repo = Repository.open(args.repo)
    query = LogQuery(repo)
    commits = query.all(branch=args.branch, limit=args.limit)
    if not commits:
        print("No commits.")
        return 0
    for commit in commits:
        print(_format_commit(commit))
        print()
    return 0


def cmd_show(args):
    repo = Repository.open(args.repo)
    commit_hash = repo._resolve_commit(args.commit)
    if commit_hash is None:
        print(f"Error: Cannot resolve commit: {args.commit}", file=sys.stderr)
        return 1
    commit = repo.get_commit(commit_hash)
    print(_format_commit(commit, short=False))
    print()
    if commit.parents:
        parent = repo.get_commit(commit.parents[0])
        parent_store = repo.get_store(parent.tree_hash)
        current_store = repo.get_store(commit.tree_hash)
        from .diff import semantic_diff
        diff = semantic_diff(parent_store, current_store)
        if not diff.is_clean:
            print(diff.summary())
    return 0


def cmd_checkout(args):
    repo = Repository.open(args.repo)
    clearance = PrivacyLevel[args.clearance.upper()] if args.clearance else PrivacyLevel.PUBLIC
    ctx = PrivacyContext(clearance=clearance)
    pw_repo = PrivacyAwareRepo(repo)
    try:
        branch_list = repo.list_branches()
        if args.target in branch_list:
            repo.switch_branch(args.target)
            print(f"Switched to branch '{args.target}'")
            return 0
        store = pw_repo.checkout(args.target, ctx=ctx)
        if args.output:
            from ..serializers import to_json
            Path(args.output).write_text(to_json(store))
            print(f"Checked out to {args.output}")
        else:
            print(f"Checked out {args.target}")
            print(f"  Entities: {store.entity_count}")
            print(f"  Root nodes: {len(store._root_children())}")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_branch(args):
    repo = Repository.open(args.repo)
    if args.list or (not args.create and not args.delete and not args.checkout):
        branches = repo.list_branches()
        current = repo.head_ref
        for b in branches:
            prefix = "* " if b == current else "  "
            print(f"{prefix}{b}")
        return 0
    if args.create:
        try:
            repo.create_branch(args.create, start_from=args.start_from)
            print(f"Created branch '{args.create}'")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.delete:
        try:
            repo.delete_branch(args.delete)
            print(f"Deleted branch '{args.delete}'")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.checkout:
        try:
            repo.switch_branch(args.checkout)
            print(f"Switched to branch '{args.checkout}'")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    return 0


def cmd_merge(args):
    repo = Repository.open(args.repo)
    clearance = PrivacyLevel[args.clearance.upper()] if args.clearance else PrivacyLevel.PUBLIC
    ctx = PrivacyContext(clearance=clearance)
    pw_repo = PrivacyAwareRepo(repo)
    try:
        result = pw_repo.merge(args.branch, ctx=ctx, strategy=args.strategy)
        if result.is_clean:
            commit = repo.commit(result.store, message=f"Merge branch '{args.branch}'", author=args.author)
            print(f"Merge successful: {commit.short_hash()}")
        else:
            print(f"Merge conflicts ({len(result.conflicts)}):")
            for conflict in result.conflicts:
                print(f"  {conflict}")
            if args.strategy in ("ours", "theirs"):
                for conflict in result.conflicts:
                    if conflict.resolution:
                        print(f"  Auto-resolved: {conflict.resolution[:40]}...")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_tag(args):
    repo = Repository.open(args.repo)
    if args.list:
        tags = repo.list_tags()
        if not tags:
            print("No tags.")
        else:
            for t in tags:
                print(t)
        return 0
    try:
        repo.create_tag(args.name, commit_hash=args.commit)
        print(f"Created tag '{args.name}'")
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_gc(args):
    repo = Repository.open(args.repo)
    removed = repo.gc()
    print(f"Removed {removed} unreachable objects.")
    return 0


def cmd_query(args):
    repo = Repository.open(args.repo)
    query = LogQuery(repo)
    if args.author:
        commits = query.by_author(args.author, branch=args.branch)
        print(f"Commits by {args.author}:")
    elif args.message:
        commits = query.by_message(args.message, branch=args.branch)
        print(f"Commits matching '{args.message}':")
    elif args.section:
        commits = query.affecting_section(args.section, branch=args.branch)
        print(f"Commits affecting section '{args.section}':")
    elif args.type:
        from ..ir.types import BlockType, InlineType
        try:
            ntype = BlockType(args.type.lower().replace("-", "_"))
        except ValueError:
            try:
                ntype = InlineType(args.type.lower().replace("-", "_"))
            except ValueError:
                print(f"Error: Unknown node type: {args.type}", file=sys.stderr)
                return 1
        commits = query.affecting_type(ntype, branch=args.branch)
        print(f"Commits affecting {args.type}:")
    else:
        commits = query.all(branch=args.branch, limit=args.limit)
    for commit in commits:
        print(f"  {commit.short_hash()} {commit.message} ({commit.author})")
    if not commits:
        print("  (none)")
    return 0


def _load_file(path: str) -> DocumentStore | None:
    from ..adapters import load
    try:
        return load(path)
    except Exception:
        try:
            from ..serializers import from_json
            return from_json(Path(path).read_text())
        except Exception:
            return None


def _load_working_tree(args) -> DocumentStore | None:
    if args.file:
        return _load_file(args.file)
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        if content.strip():
            return _load_file(content)
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdoc",
        description="Semantic Document Version Control System",
    )
    parser.add_argument("--repo", "-R", default=".", help="Repository path (default: .)")

    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize a new repository")
    p_init.add_argument("path", nargs="?", default=".", help="Directory to initialize")
    p_init.set_defaults(func=cmd_init)

    p_commit = sub.add_parser("commit", help="Commit current working tree")
    p_commit.add_argument("--message", "-m", required=True, help="Commit message")
    p_commit.add_argument("--file", "-f", help="Document file to commit")
    p_commit.add_argument("--author", "-a", help="Author name")
    p_commit.set_defaults(func=cmd_commit)

    p_status = sub.add_parser("status", help="Show working tree status")
    p_status.add_argument("--file", "-f", help="Document file to compare")
    p_status.set_defaults(func=cmd_status)

    p_diff = sub.add_parser("diff", help="Show diff between commits or working tree")
    p_diff.add_argument("commit1", nargs="?", help="First commit (or base)")
    p_diff.add_argument("commit2", nargs="?", help="Second commit")
    p_diff.add_argument("--file", "-f", help="Document file to diff")
    p_diff.set_defaults(func=cmd_diff)

    p_log = sub.add_parser("log", help="Show commit history")
    p_log.add_argument("--branch", "-b", help="Branch name")
    p_log.add_argument("--limit", "-n", type=int, help="Limit number of commits")
    p_log.set_defaults(func=cmd_log)

    p_show = sub.add_parser("show", help="Show commit details")
    p_show.add_argument("commit", help="Commit hash or reference")
    p_show.set_defaults(func=cmd_show)

    p_checkout = sub.add_parser("checkout", help="Checkout a commit or branch")
    p_checkout.add_argument("target", help="Commit hash or branch name")
    p_checkout.add_argument("--output", "-o", help="Output file for checked out document")
    p_checkout.add_argument("--clearance", "-c", default="public", help="Privacy clearance level")
    p_checkout.set_defaults(func=cmd_checkout)

    p_branch = sub.add_parser("branch", help="Manage branches")
    p_branch.add_argument("create", nargs="?", help="Create new branch")
    p_branch.add_argument("--delete", "-d", help="Delete branch")
    p_branch.add_argument("--checkout", "-c", help="Switch to branch")
    p_branch.add_argument("--list", "-l", action="store_true", help="List branches")
    p_branch.add_argument("--start-from", "-s", help="Start branch from commit")
    p_branch.set_defaults(func=cmd_branch)

    p_merge = sub.add_parser("merge", help="Merge a branch")
    p_merge.add_argument("branch", help="Branch to merge")
    p_merge.add_argument("--strategy", "-s", default="auto", choices=["auto", "ours", "theirs"], help="Merge strategy")
    p_merge.add_argument("--author", "-a", help="Author name")
    p_merge.add_argument("--clearance", "-c", default="public", help="Privacy clearance level")
    p_merge.set_defaults(func=cmd_merge)

    p_tag = sub.add_parser("tag", help="Manage tags")
    p_tag.add_argument("name", nargs="?", help="Tag name")
    p_tag.add_argument("commit", nargs="?", help="Commit to tag")
    p_tag.add_argument("--list", "-l", action="store_true", help="List tags")
    p_tag.set_defaults(func=cmd_tag)

    p_gc = sub.add_parser("gc", help="Garbage collect unreachable objects")
    p_gc.set_defaults(func=cmd_gc)

    p_query = sub.add_parser("query", help="Query commit history")
    p_query.add_argument("--author", help="Filter by author")
    p_query.add_argument("--message", help="Filter by commit message pattern")
    p_query.add_argument("--section", help="Filter by affected section title")
    p_query.add_argument("--type", help="Filter by affected node type")
    p_query.add_argument("--branch", "-b", help="Branch name")
    p_query.add_argument("--limit", "-n", type=int, help="Limit results")
    p_query.set_defaults(func=cmd_query)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)
