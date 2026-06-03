from __future__ import annotations

import re
from io import StringIO
from typing import TextIO

from ..ir.build import Builder
from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import preorder
from ..ir.types import BlockType, InlineType, ListType
from .base import Dest, Reader, Source, Writer, _open_dest, _open_source, logger


class MarkdownReader(Reader):
    def read(self, source: Source) -> DocumentStore:
        name, fh = _open_source(source)
        try:
            return self._parse(fh)
        finally:
            if fh is not source:
                fh.close()

    def _parse(self, fh: TextIO) -> DocumentStore:
        b = Builder()
        lines = fh.readlines()
        i = 0
        current_list_type = None
        current_list_handle = None

        while i < len(lines):
            line = lines[i].rstrip("\n")

            if not line.strip():
                i += 1
                current_list_type = None
                current_list_handle = None
                continue

            if line.startswith("#"):
                current_list_type = None
                current_list_handle = None
                m = re.match(r"^(#{1,6})\s+(.*)", line)
                if m:
                    level = len(m.group(1))
                    title = m.group(2)
                    b.section(level, title)
                i += 1
                continue

            if line.strip() == "---" or line.strip() == "***":
                current_list_type = None
                current_list_handle = None
                b.thematic_break()
                i += 1
                continue

            if line.startswith("```") or line.startswith("~~~"):
                current_list_type = None
                current_list_handle = None
                fence = line[:3]
                lang = line[3:].strip() or None
                code_lines = []
                i += 1
                while i < len(lines):
                    if lines[i].rstrip().startswith(fence):
                        i += 1
                        break
                    code_lines.append(lines[i].rstrip("\n"))
                    i += 1
                b.code_block(lang, "\n".join(code_lines))
                continue

            if re.match(r"^[\s]*[-*+]\s+", line):
                if current_list_type != ListType.UNORDERED:
                    current_list_type = ListType.UNORDERED
                    current_list_handle = b.list_block(ListType.UNORDERED)
                content = re.sub(r"^[\s]*[-*+]\s+", "", line)
                current_list_handle.item(content)
                i += 1
                continue

            if re.match(r"^[\s]*\d+\.\s+", line):
                if current_list_type != ListType.ORDERED:
                    current_list_type = ListType.ORDERED
                    current_list_handle = b.list_block(ListType.ORDERED)
                content = re.sub(r"^[\s]*\d+\.\s+", "", line)
                current_list_handle.item(content)
                i += 1
                continue

            if line.startswith(">"):
                current_list_type = None
                current_list_handle = None
                bq = b.blockquote()
                content = line[1:].strip()
                if content:
                    bq.paragraph(content)
                i += 1
                continue

            current_list_type = None
            current_list_handle = None
            b.paragraph(line.strip())
            i += 1

        return b.build()


class MarkdownWriter(Writer):
    def write(self, store: DocumentStore, dest: Dest) -> None:
        fh = _open_dest(dest)
        try:
            self._emit(store, fh)
        finally:
            if fh is not dest:
                fh.close()

    def _emit(self, store: DocumentStore, fh) -> None:
        if store.meta_title >= 0:
            fh.write(f"# {store.text(store.meta_title)}\n\n")

        for eid in store._root_children():
            self._emit_block(store, eid, fh, depth=0)

    def _emit_block(self, store: DocumentStore, eid: int, fh, depth: int) -> None:
        ntype = store.node_type[eid]

        if ntype == BlockType.SECTION:
            level = store.block_level.get(eid, 1)
            title = self._collect_inline_text(store, eid)
            fh.write(f"{'#' * level} {title}\n\n")
            for cid in store.children(eid):
                if store.node_type[cid] != InlineType.TEXT:
                    self._emit_block(store, cid, fh, depth + 1)

        elif ntype == BlockType.PARAGRAPH:
            text = self._emit_inlines(store, eid)
            if text:
                fh.write(f"{text}\n\n")

        elif ntype == BlockType.CODE_BLOCK:
            lang = store.block_language.get(eid, _NONE)
            lang_str = store.text(lang) if lang >= 0 else ""
            content = store.block_content.get(eid, _NONE)
            content_str = store.text(content) if content >= 0 else ""
            fh.write(f"```{lang_str}\n{content_str}\n```\n\n")

        elif ntype == BlockType.LIST:
            list_type = store.block_list_type.get(eid, ListType.UNORDERED)
            bullet = "-" if list_type == ListType.UNORDERED else "1."
            for idx, cid in enumerate(store.children(eid)):
                if store.node_type[cid] == BlockType.LIST_ITEM:
                    text = self._emit_inlines(store, cid)
                    fh.write(f"{bullet} {text}\n")
            fh.write("\n")

        elif ntype == BlockType.BLOCKQUOTE:
            for cid in store.children(eid):
                child_text = self._emit_inlines(store, cid)
                if child_text:
                    for line in child_text.split("\n"):
                        fh.write(f"> {line}\n")
            fh.write("\n")

        elif ntype == BlockType.TABLE:
            self._emit_table(store, eid, fh)

        elif ntype == BlockType.THEMATIC_BREAK:
            fh.write("---\n\n")

        elif ntype == BlockType.ADMONITION:
            admon = store.block_admon_type.get(eid)
            label = admon.value.upper() if admon else "NOTE"
            text = self._emit_inlines(store, eid)
            fh.write(f"> [!{label}]\n> {text}\n\n")

    def _emit_table(self, store: DocumentStore, eid: int, fh) -> None:
        rows = store.children(eid)
        if not rows:
            return
        first_row = rows[0]
        cells = store.children(first_row)
        headers = [self._emit_inlines(store, c) for c in cells]
        fh.write("| " + " | ".join(headers) + " |\n")
        fh.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for row in rows[1:]:
            cells = store.children(row)
            vals = [self._emit_inlines(store, c) for c in cells]
            fh.write("| " + " | ".join(vals) + " |\n")
        fh.write("\n")

    def _emit_inlines(self, store: DocumentStore, parent: int) -> str:
        parts = []
        for cid in store.children(parent):
            parts.append(self._emit_inline(store, cid))
        return "".join(parts)

    def _emit_inline(self, store: DocumentStore, eid: int) -> str:
        ntype = store.node_type[eid]

        if ntype == InlineType.TEXT:
            t = store.inline_text.get(eid, _NONE)
            return store.text(t) if t >= 0 else ""

        if ntype == InlineType.EMPHASIS:
            return f"*{self._emit_inlines(store, eid)}*"

        if ntype == InlineType.STRONG:
            return f"**{self._emit_inlines(store, eid)}**"

        if ntype == InlineType.INLINE_CODE:
            t = store.inline_text.get(eid, _NONE)
            return f"`{store.text(t) if t >= 0 else ''}`"

        if ntype == InlineType.LINK:
            url = store.inline_url.get(eid, _NONE)
            url_str = store.text(url) if url >= 0 else ""
            text = self._emit_inlines(store, eid)
            title = store.inline_title.get(eid, _NONE)
            if title >= 0:
                return f"[{text}]({url_str} \"{store.text(title)}\")"
            return f"[{text}]({url_str})"

        if ntype == InlineType.IMAGE:
            url = store.inline_url.get(eid, _NONE)
            alt = store.inline_text.get(eid, _NONE)
            alt_str = store.text(alt) if alt >= 0 else ""
            title = store.inline_title.get(eid, _NONE)
            if title >= 0:
                return f"![{alt_str}]({store.text(url) if url >= 0 else ''} \"{store.text(title)}\")"
            return f"![{alt_str}]({store.text(url) if url >= 0 else ''})"

        if ntype == InlineType.LINE_BREAK:
            return "\n"

        logger.warning(f"Unknown inline type: {ntype}")
        return self._emit_inlines(store, eid)

    def _collect_inline_text(self, store: DocumentStore, eid: int) -> str:
        parts = []
        for cid in store.children(eid):
            if store.node_type[cid] == InlineType.TEXT:
                t = store.inline_text.get(cid, _NONE)
                if t >= 0:
                    parts.append(store.text(t))
        return " ".join(parts)
