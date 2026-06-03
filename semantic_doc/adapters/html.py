from __future__ import annotations

import html
from io import StringIO

from ..ir.store import DocumentStore, _NONE
from ..ir.traverse import preorder
from ..ir.types import BlockType, InlineType, ListType
from .base import Dest, Writer, _open_dest, logger


class HTMLWriter(Writer):
    def write(self, store: DocumentStore, dest: Dest) -> None:
        fh = _open_dest(dest)
        try:
            self._emit(store, fh)
        finally:
            if fh is not dest:
                fh.close()

    def _emit(self, store: DocumentStore, fh) -> None:
        title = store.text(store.meta_title) if store.meta_title >= 0 else "Document"
        fh.write("<!DOCTYPE html>\n<html>\n<head>\n")
        fh.write(f"<meta charset=\"utf-8\">\n<title>{html.escape(title)}</title>\n")
        fh.write("</head>\n<body>\n")

        for eid in store._root_children():
            self._emit_block(store, eid, fh)

        fh.write("</body>\n</html>\n")

    def _emit_block(self, store: DocumentStore, eid: int, fh) -> None:
        ntype = store.node_type[eid]

        if ntype == BlockType.SECTION:
            level = store.block_level.get(eid, 1)
            tag = f"h{min(level, 6)}"
            title = self._collect_inline_text(store, eid)
            fh.write(f"<{tag}>{html.escape(title)}</{tag}>\n")
            for cid in store.children(eid):
                if store.node_type[cid] != InlineType.TEXT:
                    self._emit_block(store, cid, fh)

        elif ntype == BlockType.PARAGRAPH:
            text = self._emit_inlines(store, eid)
            if text:
                fh.write(f"<p>{text}</p>\n")

        elif ntype == BlockType.CODE_BLOCK:
            lang = store.block_language.get(eid, _NONE)
            lang_str = store.text(lang) if lang >= 0 else ""
            content = store.block_content.get(eid, _NONE)
            content_str = html.escape(store.text(content)) if content >= 0 else ""
            if lang_str:
                fh.write(f"<pre><code class=\"language-{html.escape(lang_str)}\">{content_str}</code></pre>\n")
            else:
                fh.write(f"<pre><code>{content_str}</code></pre>\n")

        elif ntype == BlockType.LIST:
            list_type = store.block_list_type.get(eid, ListType.UNORDERED)
            tag = "ol" if list_type == ListType.ORDERED else "ul"
            fh.write(f"<{tag}>\n")
            for cid in store.children(eid):
                if store.node_type[cid] == BlockType.LIST_ITEM:
                    text = self._emit_inlines(store, cid)
                    fh.write(f"<li>{text}</li>\n")
            fh.write(f"</{tag}>\n")

        elif ntype == BlockType.BLOCKQUOTE:
            fh.write("<blockquote>\n")
            for cid in store.children(eid):
                child_text = self._emit_inlines(store, cid)
                if child_text:
                    fh.write(f"<p>{child_text}</p>\n")
            fh.write("</blockquote>\n")

        elif ntype == BlockType.TABLE:
            self._emit_table(store, eid, fh)

        elif ntype == BlockType.THEMATIC_BREAK:
            fh.write("<hr>\n")

        elif ntype == BlockType.ADMONITION:
            admon = store.block_admon_type.get(eid)
            label = admon.value.upper() if admon else "NOTE"
            text = self._emit_inlines(store, eid)
            fh.write(f"<div class=\"admonition {label.lower()}\"><p><strong>{label}:</strong> {text}</p></div>\n")

    def _emit_table(self, store: DocumentStore, eid: int, fh) -> None:
        rows = store.children(eid)
        if not rows:
            return
        fh.write("<table>\n")
        first_row = rows[0]
        cells = store.children(first_row)
        fh.write("<thead><tr>\n")
        for c in cells:
            fh.write(f"<th>{self._emit_inlines(store, c)}</th>\n")
        fh.write("</tr></thead>\n")
        if len(rows) > 1:
            fh.write("<tbody>\n")
            for row in rows[1:]:
                cells = store.children(row)
                fh.write("<tr>\n")
                for c in cells:
                    fh.write(f"<td>{self._emit_inlines(store, c)}</td>\n")
                fh.write("</tr>\n")
            fh.write("</tbody>\n")
        fh.write("</table>\n")

    def _emit_inlines(self, store: DocumentStore, parent: int) -> str:
        parts = []
        for cid in store.children(parent):
            parts.append(self._emit_inline(store, cid))
        return "".join(parts)

    def _emit_inline(self, store: DocumentStore, eid: int) -> str:
        ntype = store.node_type[eid]

        if ntype == InlineType.TEXT:
            t = store.inline_text.get(eid, _NONE)
            return html.escape(store.text(t)) if t >= 0 else ""

        if ntype == InlineType.EMPHASIS:
            return f"<em>{self._emit_inlines(store, eid)}</em>"

        if ntype == InlineType.STRONG:
            return f"<strong>{self._emit_inlines(store, eid)}</strong>"

        if ntype == InlineType.INLINE_CODE:
            t = store.inline_text.get(eid, _NONE)
            return f"<code>{html.escape(store.text(t)) if t >= 0 else ''}</code>"

        if ntype == InlineType.LINK:
            url = store.inline_url.get(eid, _NONE)
            url_str = html.escape(store.text(url)) if url >= 0 else ""
            text = self._emit_inlines(store, eid)
            title = store.inline_title.get(eid, _NONE)
            title_attr = f" title=\"{html.escape(store.text(title))}\"" if title >= 0 else ""
            return f"<a href=\"{url_str}\"{title_attr}>{text}</a>"

        if ntype == InlineType.IMAGE:
            url = store.inline_url.get(eid, _NONE)
            alt = store.inline_text.get(eid, _NONE)
            alt_str = html.escape(store.text(alt)) if alt >= 0 else ""
            title = store.inline_title.get(eid, _NONE)
            title_attr = f" title=\"{html.escape(store.text(title))}\"" if title >= 0 else ""
            return f"<img src=\"{html.escape(store.text(url)) if url >= 0 else ''}\" alt=\"{alt_str}\"{title_attr}>"

        if ntype == InlineType.LINE_BREAK:
            return "<br>"

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
