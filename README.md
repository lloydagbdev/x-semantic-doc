# x-semantic-doc

An exploration of semantic document infrastructure: a typed IR, a structural version control system, and a desktop editor built on top of both.

## What it is

Most document tools treat content as text with formatting applied on top. This project treats a document as a **tree of typed semantic nodes** — sections, paragraphs, code blocks, lists, inline emphasis — stored in a compact IR. Version control and editor tooling are built on that IR directly, not on a text serialization of it.

The result is a VCS that understands document structure: it knows when a section was renamed (not just modified), when a paragraph was moved (not just deleted and re-added), and can compute structural diffs across branches.

## Architecture

```
IR (DocumentStore)
  ↓
VCS (Repository, semantic diff, branches)
  ↓
Style Layer (style.css — presentation schema)
  ↓
Desktop Editor (pywebview + WebKitGTK)
```

Each layer depends only on the one below it. The style layer is explicitly separate from the editor chrome so the same visual rules can feed HTML/PDF export.

### IR (`semantic_doc/ir/`)

A flat entity-component store. Every node (block or inline) gets an integer entity ID. Node relationships (parent, prev sibling, next sibling, first child) are tracked in parallel arrays. Block-specific data (heading level, list type, code language, admonition kind) lives in sparse dicts keyed by EID.

Block types: `SECTION`, `PARAGRAPH`, `CODE_BLOCK`, `LIST`, `LIST_ITEM`, `BLOCKQUOTE`, `TABLE`, `TABLE_ROW`, `TABLE_CELL`, `THEMATIC_BREAK`, `ADMONITION`

Inline types: `TEXT`, `EMPHASIS`, `STRONG`, `INLINE_CODE`, `LINK`, `IMAGE`, `LINE_BREAK`

### VCS (`semantic_doc/vcs/`)

Git-inspired: content-addressed object store, commits, branches, HEAD. Diffs are computed at the node level — the diff knows the difference between a rename, a move, a modification, and an addition, rather than reducing everything to line changes.

### Editor (`editor/`)

Desktop app using [pywebview](https://pywebview.flowrl.com/) (WebKitGTK on Linux). The Python IR is the source of truth; the JS frontend calls Python methods directly via the pywebview API bridge — no HTTP server, no serialization overhead.

**Writing UX** is Typora-meets-Notion: you write in a clean document surface, markdown syntax triggers convert automatically (type `# ` → heading, `- ` → list, `> ` → blockquote, ```` ``` ```` → code block; `**bold**`, `*italic*`, `` `code` `` render inline as you close the markers), and block controls appear in the left margin on hover only when needed.

**Style layer** (`editor/app/style.css`) is the presentation schema. All visual decisions — font sizes, heading weights, spacing, colors — are expressed as `--ds-*` CSS variables. Override them to create themes; the same schema will feed export rendering.

## Running

```bash
python3 run_editor.py
```

Requires Python 3.11+, pywebview, and WebKitGTK (Linux) or WKWebView (macOS).

```bash
python3 -m pip install pywebview
# Linux: sudo dnf install python3-gobject webkit2gtk4.1
#        (or equivalent for your distro)
```

## Structure

```
semantic_doc/
  ir/          — DocumentStore, Builder, node types
  vcs/         — Repository, commits, branches, semantic diff
  serializers/ — JSON round-trip
  adapters/    — Markdown, AsciiDoc, HTML import
  ops/         — Hashing, indexing, privacy/redaction
editor/
  main.py      — pywebview app + EditorAPI (JS↔Python bridge)
  app/
    index.html — editor UI (HTML + JS)
    chrome.css — editor shell styles (layout, toolbar, panels)
    style.css  — document presentation layer (--ds-* variables)
```

## What's missing / next

- Inline link and image editing UI
- Multi-document file tree
- Export to HTML/PDF using the style layer
- Privacy/redaction UI (`PrivacyLevel` exists in the IR, not surfaced)
- Semantic diff rendered as inline change tracking (not just a log)
- Proper IR mutation API (currently some mutations write node arrays directly)
