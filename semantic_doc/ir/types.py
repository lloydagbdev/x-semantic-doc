from enum import Enum, StrEnum, auto
from typing import TypeAlias


class BlockType(StrEnum):
    SECTION = auto()
    PARAGRAPH = auto()
    CODE_BLOCK = auto()
    LIST = auto()
    LIST_ITEM = auto()
    BLOCKQUOTE = auto()
    TABLE = auto()
    TABLE_ROW = auto()
    TABLE_CELL = auto()
    THEMATIC_BREAK = auto()
    ADMONITION = auto()


class InlineType(StrEnum):
    TEXT = auto()
    EMPHASIS = auto()
    STRONG = auto()
    INLINE_CODE = auto()
    LINK = auto()
    IMAGE = auto()
    LINE_BREAK = auto()


NodeType: TypeAlias = BlockType | InlineType

BLOCK_TYPES = set(BlockType)
INLINE_TYPES = set(InlineType)


class ListType(StrEnum):
    ORDERED = auto()
    UNORDERED = auto()
    CHECKLIST = auto()


class AdmonType(StrEnum):
    NOTE = auto()
    TIP = auto()
    IMPORTANT = auto()
    WARNING = auto()
    CAUTION = auto()


class PrivacyLevel(StrEnum):
    PUBLIC = auto()
    INTERNAL = auto()
    CONFIDENTIAL = auto()
    SECRET = auto()


class RedactionAction(StrEnum):
    REMOVE = auto()
    REPLACE = auto()
    MASK = auto()
    HASH = auto()
    ANONYMIZE = auto()
