from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import TextIO

from ..ir.store import DocumentStore

logger = logging.getLogger(__name__)

Source = str | Path | TextIO
Dest = str | Path | TextIO


def _open_source(source: Source) -> tuple[str, TextIO]:
    if isinstance(source, Path):
        return source.name, source.open(encoding="utf-8")
    if isinstance(source, str):
        p = Path(source)
        if p.exists():
            return p.name, p.open(encoding="utf-8")
        return source, StringIO(source)
    return getattr(source, "name", "<stream>"), source


def _open_dest(dest: Dest) -> TextIO:
    if isinstance(dest, (str, Path)):
        return open(dest, "w", encoding="utf-8")
    return dest


class Reader(ABC):
    @abstractmethod
    def read(self, source: Source) -> DocumentStore: ...


class Writer(ABC):
    @abstractmethod
    def write(self, store: DocumentStore, dest: Dest) -> None: ...


class ReaderWriter(Reader, Writer):
    pass


@dataclass
class Adapter(ABC):
    name: str
    extensions: list[str] = field(default_factory=list)
    can_read: bool = False
    can_write: bool = False
    capabilities: set[str] = field(default_factory=set)


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, Adapter] = {}
        self._ext_map: dict[str, str] = {}

    def register(self, adapter: Adapter) -> None:
        self._adapters[adapter.name] = adapter
        for ext in adapter.extensions:
            self._ext_map[ext.lower()] = adapter.name

    def get(self, name: str) -> Adapter:
        return self._adapters[name]

    def get_for_extension(self, ext: str) -> Adapter | None:
        name = self._ext_map.get(ext.lower())
        if name:
            return self._adapters[name]
        return None

    def get_for_path(self, path: str | Path) -> Adapter | None:
        ext = Path(path).suffix
        return self.get_for_extension(ext)

    def load(self, source: Source, format: str | None = None) -> DocumentStore:
        if format:
            adapter = self._adapters[format]
        elif isinstance(source, (str, Path)):
            adapter = self.get_for_path(source)
        else:
            raise ValueError("Cannot auto-detect format from stream, specify format=...")

        if adapter is None:
            raise ValueError(f"No adapter found for {source}")
        if not adapter.can_read:
            raise ValueError(f"Adapter {adapter.name} cannot read")

        reader: Reader = adapter  # type: ignore
        return reader.read(source)

    def save(self, store: DocumentStore, dest: Dest, format: str | None = None) -> None:
        if format:
            adapter = self._adapters[format]
        elif isinstance(dest, (str, Path)):
            adapter = self.get_for_path(dest)
        else:
            raise ValueError("Cannot auto-detect format from stream, specify format=...")

        if adapter is None:
            raise ValueError(f"No adapter found for {dest}")
        if not adapter.can_write:
            raise ValueError(f"Adapter {adapter.name} cannot write")

        writer: Writer = adapter  # type: ignore
        writer.write(store, dest)


_default_registry = AdapterRegistry()


def register(adapter: Adapter) -> None:
    _default_registry.register(adapter)


def load(source: Source, format: str | None = None) -> DocumentStore:
    return _default_registry.load(source, format)


def save(store: DocumentStore, dest: Dest, format: str | None = None) -> None:
    _default_registry.save(store, dest, format)


def get_registry() -> AdapterRegistry:
    return _default_registry
