from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from typing import Iterator

from .store import DocumentStore, _NONE
from .types import BlockType, InlineType


def preorder(store: DocumentStore, root: int | None = None) -> Iterator[int]:
    stack: list[int]
    if root is None:
        stack = list(reversed(store._root_children()))
    else:
        stack = [root]
    while stack:
        eid = stack.pop()
        yield eid
        children = store.children(eid)
        stack.extend(reversed(children))


def postorder(store: DocumentStore, root: int | None = None) -> Iterator[int]:
    if root is None:
        nodes = store._root_children()
    else:
        nodes = [root]
    for eid in _postorder_from(store, nodes):
        yield eid


def _postorder_from(store: DocumentStore, roots: list[int]) -> Iterator[int]:
    for eid in roots:
        yield from _postorder_from(store, store.children(eid))
        yield eid


def bfs(store: DocumentStore, root: int | None = None) -> Iterator[int]:
    queue: deque[int]
    if root is None:
        queue = deque(store._root_children())
    else:
        queue = deque([root])
    while queue:
        eid = queue.popleft()
        yield eid
        queue.extend(store.children(eid))


def path(store: DocumentStore, eid: int) -> list[int]:
    result = []
    cur = eid
    while cur != _NONE:
        result.append(cur)
        cur = store.node_parent[cur]
    result.reverse()
    return result


def depth(store: DocumentStore, eid: int) -> int:
    d = 0
    cur = store.node_parent[eid]
    while cur != _NONE:
        d += 1
        cur = store.node_parent[cur]
    return d


def leaves(store: DocumentStore, root: int | None = None) -> Iterator[int]:
    for eid in preorder(store, root):
        if store.node_first_child[eid] == _NONE:
            yield eid


class Visitor(ABC):
    def visit(self, store: DocumentStore, eid: int) -> None:
        node_type = store.node_type[eid]
        if isinstance(node_type, BlockType):
            self.visit_block(store, eid, node_type)
        else:
            self.visit_inline(store, eid, node_type)

    @abstractmethod
    def visit_block(self, store: DocumentStore, eid: int, btype: BlockType) -> None: ...

    @abstractmethod
    def visit_inline(self, store: DocumentStore, eid: int, itype: InlineType) -> None: ...

    def walk(self, store: DocumentStore, root: int | None = None, order: str = "preorder") -> None:
        iter_fn = {"preorder": preorder, "postorder": postorder, "bfs": bfs}[order]
        for eid in iter_fn(store, root):
            self.visit(store, eid)
