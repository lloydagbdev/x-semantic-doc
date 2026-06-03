import sys
import traceback
import tempfile
import json
from pathlib import Path

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


def main():
    from semantic_doc.vcs.commit import Commit, make_commit
    from semantic_doc.vcs.store import ObjectStore
    from semantic_doc.vcs.repo import Repository
    from semantic_doc.ir import Builder, BlockType, InlineType, ListType

    def test_commit_serialization():
        c = make_commit(tree_hash="abc123", message="test", author="user")
        data = c.serialize()
        c2 = Commit.deserialize(data)
        assert c2.tree_hash == "abc123"
        assert c2.message == "test"
        assert c2.author == "user"

    def test_object_store():
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ObjectStore(Path(tmpdir))
            data = b"hello world"
            h = store.put(data)
            assert store.has(h)
            assert store.get(h) == data

    def test_repo_init():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            assert repo.semantic.exists()
            assert repo.objects_path.exists()
            assert repo.head_file.exists()

    def test_repo_commit():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            commit = repo.commit(store, message="Initial")
            assert commit.message == "Initial"
            assert commit.tree_hash
            assert repo.head_commit_hash is not None

    def test_repo_log():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            c1 = repo.commit(store, message="First")
            b2 = Builder()
            b2.paragraph("World")
            store2 = b2.build()
            c2 = repo.commit(store2, message="Second")
            commits = repo.log()
            assert len(commits) == 2
            assert commits[0].message == "Second"
            assert commits[1].message == "First"

    def test_repo_checkout():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            c1 = repo.commit(store, message="First")
            b2 = Builder()
            b2.paragraph("World")
            store2 = b2.build()
            c2 = repo.commit(store2, message="Second")
            checked_out = repo.checkout(c1.hash)
            assert checked_out.entity_count == 2

    def test_repo_branch():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            repo.commit(store, message="Initial")
            repo.create_branch("feature")
            assert "feature" in repo.list_branches()
            repo.switch_branch("feature")
            assert repo.head_ref == "feature"

    def test_repo_gc():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            repo.commit(store, message="Initial")
            removed = repo.gc()
            assert removed >= 0

    run_module("vcs_core", [
        test_commit_serialization,
        test_object_store,
        test_repo_init,
        test_repo_commit,
        test_repo_log,
        test_repo_checkout,
        test_repo_branch,
        test_repo_gc,
    ])


    from semantic_doc.vcs.diff import semantic_diff, NodeAdded, NodeRemoved, NodeModified

    def test_diff_no_changes():
        b = Builder()
        b.paragraph("Hello")
        store = b.build()
        diff = semantic_diff(store, store)
        assert diff.is_clean

    def test_diff_add_paragraph():
        b1 = Builder()
        b1.paragraph("Hello")
        store1 = b1.build()
        b2 = Builder()
        b2.paragraph("Hello")
        b2.paragraph("World")
        store2 = b2.build()
        diff = semantic_diff(store1, store2)
        assert not diff.is_clean
        assert diff.stats.added >= 1

    def test_diff_remove_paragraph():
        b1 = Builder()
        b1.paragraph("Hello")
        b1.paragraph("World")
        store1 = b1.build()
        b2 = Builder()
        b2.paragraph("Hello")
        store2 = b2.build()
        diff = semantic_diff(store1, store2)
        assert not diff.is_clean
        assert diff.stats.removed >= 1

    def test_diff_modify_paragraph():
        b1 = Builder()
        b1.paragraph("Hello")
        store1 = b1.build()
        b2 = Builder()
        b2.paragraph("World")
        store2 = b2.build()
        diff = semantic_diff(store1, store2)
        assert not diff.is_clean
        assert diff.stats.modified >= 1

    run_module("diff", [
        test_diff_no_changes,
        test_diff_add_paragraph,
        test_diff_remove_paragraph,
        test_diff_modify_paragraph,
    ])


    from semantic_doc.vcs.merge import semantic_merge, MergeConflict

    def test_merge_clean():
        b = Builder()
        b.paragraph("Base")
        base = b.build()
        b2 = Builder()
        b2.paragraph("Base modified")
        ours = b2.build()
        b3 = Builder()
        b3.paragraph("Base")
        b3.paragraph("New paragraph")
        theirs = b3.build()
        result = semantic_merge(base, ours, theirs)
        assert result.is_clean or len(result.conflicts) == 0

    def test_merge_conflict():
        b = Builder()
        b.paragraph("Base")
        base = b.build()
        b2 = Builder()
        b2.paragraph("Ours")
        ours = b2.build()
        b3 = Builder()
        b3.paragraph("Theirs")
        theirs = b3.build()
        result = semantic_merge(base, ours, theirs)
        assert not result.is_clean
        assert len(result.conflicts) >= 1

    run_module("merge", [
        test_merge_clean,
        test_merge_conflict,
    ])


    from semantic_doc.vcs.privacy import PrivacyAwareRepo, PrivacyContext
    from semantic_doc.ir.types import PrivacyLevel

    def test_privacy_checkout():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Public text")
            p = b.paragraph("Secret text")
            p.privacy(PrivacyLevel.SECRET)
            store = b.build()
            repo.commit(store, message="Initial")
            pw_repo = PrivacyAwareRepo(repo)
            ctx_public = PrivacyContext(clearance=PrivacyLevel.PUBLIC)
            public_store = pw_repo.checkout(repo.head_commit_hash, ctx=ctx_public)
            public_roots = public_store._root_children()
            assert len(public_roots) < len(store._root_children())

    def test_privacy_full_clearance():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Public text")
            p = b.paragraph("Secret text")
            p.privacy(PrivacyLevel.SECRET)
            store = b.build()
            repo.commit(store, message="Initial")
            pw_repo = PrivacyAwareRepo(repo)
            ctx_secret = PrivacyContext(clearance=PrivacyLevel.SECRET)
            secret_store = pw_repo.checkout(repo.head_commit_hash, ctx=ctx_secret)
            assert secret_store.entity_count == store.entity_count

    run_module("privacy", [
        test_privacy_checkout,
        test_privacy_full_clearance,
    ])


    from semantic_doc.vcs.log import LogQuery

    def test_query_by_author():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            repo.commit(store, message="First", author="alice")
            repo.commit(store, message="Second", author="bob")
            query = LogQuery(repo)
            alice_commits = query.by_author("alice")
            bob_commits = query.by_author("bob")
            assert len(alice_commits) == 1
            assert len(bob_commits) == 1

    def test_query_by_message():
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Repository.init(tmpdir)
            b = Builder()
            b.paragraph("Hello")
            store = b.build()
            repo.commit(store, message="Add intro")
            repo.commit(store, message="Fix typo")
            query = LogQuery(repo)
            result = query.by_message("intro")
            assert len(result) == 1

    run_module("log_query", [
        test_query_by_author,
        test_query_by_message,
    ])


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


if __name__ == "__main__":
    main()
