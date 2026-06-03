import re

import pytest

from semantic_doc.ir import BlockType, Builder, InlineType, PrivacyLevel
from semantic_doc.ops import (
    PrivacyMask,
    RedactionAction,
    StructuralRule,
    TextRule,
    apply_rules,
    build_index,
    redact,
)


def test_text_rule_replace():
    b = Builder()
    b.paragraph("Contact: john@example.com for info")
    b.paragraph("No email here")
    store = b.build()

    rule = TextRule(
        pattern=re.compile(r"\w+@\w+\.\w+"),
        action=RedactionAction.REPLACE,
        replacement="[EMAIL]",
    )
    mask = apply_rules(store, [rule])
    assert len(mask.affected) > 0

    redacted = redact(store, mask)
    for eid in mask.replacements:
        assert redacted.text(redacted.inline_text[eid]) == "[EMAIL]"


def test_text_rule_mask():
    b = Builder()
    b.paragraph("SSN: 123-45-6789")
    store = b.build()

    rule = TextRule(
        pattern=re.compile(r"\d{3}-\d{2}-\d{4}"),
        action=RedactionAction.MASK,
    )
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    for eid in mask.replacements:
        replaced = redacted.text(redacted.inline_text[eid])
        assert all(c == "\u2588" for c in replaced)


def test_text_rule_hash():
    b = Builder()
    b.paragraph("Secret: password123")
    store = b.build()

    rule = TextRule(
        pattern=re.compile(r"password123"),
        action=RedactionAction.HASH,
    )
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)
    for eid in mask.replacements:
        replaced = redacted.text(redacted.inline_text[eid])
        assert replaced.startswith("[HASH:")
        assert replaced.endswith("]")


def test_structural_rule_remove():
    b = Builder()
    b.paragraph("Keep this")
    b.code_block("python", "secret = 'key'")
    b.paragraph("Also keep")
    store = b.build()

    rule = StructuralRule(
        node_types={BlockType.CODE_BLOCK},
        action=RedactionAction.REMOVE,
    )
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)

    code_blocks = [
        eid for eid in range(redacted.entity_count)
        if redacted.node_type[eid] == BlockType.CODE_BLOCK
    ]
    assert len(code_blocks) == 0


def test_structural_rule_privacy_level():
    b = Builder()
    p1 = b.paragraph("Public text")
    p2 = b.paragraph("Confidential text")
    p2.privacy(PrivacyLevel.CONFIDENTIAL)
    store = b.build()

    rule = StructuralRule(
        min_privacy=PrivacyLevel.CONFIDENTIAL,
        action=RedactionAction.REPLACE,
        replacement="[REDACTED]",
    )
    mask = apply_rules(store, [rule])
    assert len(mask.affected) == 1


def test_redact_does_not_mutate_original():
    b = Builder()
    b.paragraph("Sensitive data")
    store = b.build()

    rule = TextRule(
        pattern=re.compile(r"Sensitive"),
        action=RedactionAction.REPLACE,
        replacement="[REDACTED]",
    )
    mask = apply_rules(store, [rule])
    redacted = redact(store, mask)

    original_text = store.text(store.inline_text[1])
    assert "Sensitive" in original_text
