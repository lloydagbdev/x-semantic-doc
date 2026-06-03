from __future__ import annotations

import re
from typing import TextIO

from ..ir.build import Builder
from ..ir.store import DocumentStore
from ..ir.traverse import preorder
from ..ir.types import AdmonType, BlockType, InlineType, ListType
from .base import Dest, Reader, Source, Writer, _open_dest, _open_source, logger


class AsciiDocReader(Reader):
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

        while i < len(lines):
            line = lines[i].rstrip("\n")

            if not line.strip():
                i += 1
                continue

            if i == 0 and line.startswith("= "):
                b.title(line[2:].strip())
                i += 1
                continue

            if line.startswith(":") and line.endswith(":"):
                m = re.match(r"^:(\w[\w-]*):\s*(.*)", line)
                if m:
                    b.attr(m.group(1), m.group(2).strip())
                i += 1
                continue

            if line.startswith("=="):
                m = re.match(r"^(=+)\s+(.*)", line)
                if m:
                    level = len(m.group(1))
                    title = m.group(2)
                    b.section(level, title)
                i += 1
                continue

            if line.startswith("```") or line.startswith("----") or line.startswith("...."):
                fence = line[:4] if line[:4] in ("----", "....") else line[:3]
                lang = ""
                if fence == "```":
                    lang = line[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines):
                    stripped = lines[i].rstrip()
                    if stripped.startswith(fence):
                        i += 1
                        break
                    code_lines.append(lines[i].rstrip("\n"))
                    i += 1
                b.code_block(lang or None, "\n".join(code_lines))
                continue

            if re.match(r"^(NOTE|TIP|IMPORTANT|WARNING|CAUTION):", line):
                m = re.match(r"^(NOTE|TIP|IMPORTANT|WARNING|CAUTION):\s*(.*)", line)
                if m:
                    admon_type = AdmonType(m.group(1).lower())
                    content = m.group(2)
                    handle = b.admonition(admon_type)
                    if content:
                        handle.paragraph(content)
                i += 1
                continue

            if line.startswith("* ") or line.startswith("- "):
                content = line[2:].strip()
                lst = b.list_block(ListType.UNORDERED)
                lst.item(content)
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip("\n")
                    if next_line.startswith("* ") or next_line.startswith("- "):
                        lst.item(next_line[2:].strip())
                        i += 1
                    else:
                        break
                continue

            if re.match(r"^\d+\.\s+", line):
                content = re.sub(r"^\d+\.\s+", "", line).strip()
                lst = b.list_block(ListType.ORDERED)
                lst.item(content)
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip("\n")
                    if re.match(r"^\d+\.\s+", next_line):
                        lst.item(re.sub(r"^\d+\.\s+", "", next_line).strip())
                        i += 1
                    else:
                        break
                continue

            if line.startswith(">"):
                bq = b.blockquote()
                content = line[1:].strip()
                if content:
                    bq.paragraph(content)
                i += 1
                continue

            if line.strip() == "---" or line.strip() == "'''":
                b.thematic_break()
                i += 1
                continue

            b.paragraph(line.strip())
            i += 1

        return b.build()


class AsciiDocWriter(Writer):
    def write(self, store: DocumentStore, dest: Dest) -> None:
        fh = _open_dest(dest)
        try:
            self._emit(store, fh)
        finally:
            if fh is not dest:
                fh.close()

    def _emit(self, store: DocumentStore, fh) -> None:
        if store.meta_title >= 0:
            fh.write(f"= {store.text(store.meta_title)}\n\n")

        for k, v in store.meta_attrs.items():
            fh.write(f":{k}: {v}\n")
        if store.meta_attrs:
            fh.write("\n")

        for eid in store._root_children():
            self._emit_block(store, eid, fh)

    def _emit_block(self, store: DocumentStore, eid: int, fh) -> None:
        ntype = store.node_type[eid]

        if ntype == BlockType.SECTION:
            level = store.block_level.get(eid, 1)
            title = self._collect_inline_text(store, eid)
            fh.write(f"{'=' * level} {title}\n\n")
            for cid in store.children(eid):
                if store.node_type[cid] != InlineType.TEXT:
                    self._emit_block(store, cid, fh)

        elif ntype == BlockType.PARAGRAPH:
            text = self._emit_inlines(store, eid)
            if text:
                fh.write(f"{text}\n\n")

        elif ntype == BlockType.CODE_BLOCK:
            lang = store.block_language.get(eid, -1)
            lang_str = store.text(lang) if lang >= 0 else ""
            content = store.block_content.get(eid, -1)
            content_str = store.text(content) if content >= 0 else ""
            fh.write(f"----\n{content_str}\n----\n\n")

        elif ntype == BlockType.LIST:
            list_type = store.block_list_type.get(eid, ListType.UNORDERED)
            for idx, cid in enumerate(store.children(eid)):
                if store.node_type[cid] == BlockType.LIST_ITEM:
                    text = self._emit_inlines(store, cid)
                    if list_type == ListType.ORDERED:
                        fh.write(f". {text}\n")
                    else:
                        fh.write(f"* {text}\n")
            fh.write("\n")

        elif ntype == BlockType.BLOCKQUOTE:
            for cid in store.children(eid):
                child_text = self._emit_inlines(store, cid)
                if child_text:
                    for line in child_text.split("\n"):
                        fh.write(f"____\n{line}\n____\n")
            fh.write("\n")

        elif ntype == BlockType.TABLE:
            self._emit_table(store, eid, fh)

        elif ntype == BlockType.THEMATIC_BREAK:
            fh.write("'''\n\n")

        elif ntype == BlockType.ADMONITION:
            admon = store.block_admon_type.get(eid)
            label = admon.value.upper() if admon else "NOTE"
            text = self._emit_inlines(store, eid)
            fh.write(f"{label}: {text}\n\n")

    def _emit_table(self, store: DocumentStore, eid: int, fh) -> None:
        rows = store.children(eid)
        if not rows:
            return
        fh.write("|===\n")
        for row in rows:
            cells = store.children(row)
            vals = [self._emit_inlines(store, c) for c in cells]
            fh.write("| " + " | ".join(vals) + "\n")
        fh.write("|===\n\n")

    def _emit_inlines(self, store: DocumentStore, parent: int) -> str:
        parts = []
        for cid in store.children(parent):
            parts.append(self._emit_inline(store, cid))
        return "".join(parts)

    def _emit_inline(self, store: DocumentStore, eid: int) -> str:
        ntype = store.node_type[eid]

        if ntype == InlineType.TEXT:
            t = store.inline_text.get(eid, -1)
            return store.text(t) if t >= 0 else ""

        if ntype == InlineType.EMPHASIS:
            return f"_{self._emit_inlines(store, eid)}_"

        if ntype == InlineType.STRONG:
            return f"*{self._emit_inlines(store, eid)}*"

        if ntype == InlineType.INLINE_CODE:
            t = store.inline_text.get(eid, -1)
            return f"`{store.text(t) if t >= 0 else ''}`"

        if ntype == InlineType.LINK:
            url = store.inline_url.get(eid, -1)
            url_str = store.text(url) if url >= 0 else ""
            text = self._emit_inlines(store, eid)
            return f"{text}[{url_str}]"

        if ntype == InlineType.IMAGE:
            url = store.inline_url.get(eid, -1)
            alt = store.inline_text.get(eid, -1)
            alt_str = store.text(alt) if alt >= 0 else ""
            return f"image::{store.text(url) if url >= 0 else ''}[{alt_str}]"

        if ntype == InlineType.LINE_BREAK:
            return " +\n"

        logger.warning(f"Unknown inline type: {ntype}")
        return self._emit_inlines(store, eid)

    def _collect_inline_text(self, store: DocumentStore, eid: int) -> str:
        parts = []
        for cid in store.children(eid):
            if store.node_type[cid] == InlineType.TEXT:
                t = store.inline_text.get(cid, -1)
                if t >= 0:
                    parts.append(store.text(t))
        return " ".join(parts)
