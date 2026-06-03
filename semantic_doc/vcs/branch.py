from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..ir.types import PrivacyLevel
from .repo import Repository


@dataclass
class Branch:
    name: str
    head: str = ""
    privacy_level: PrivacyLevel = PrivacyLevel.PUBLIC
    created: float = 0.0
    description: str = ""


class BranchManager:
    def __init__(self, repo: Repository):
        self.repo = repo

    def list(self) -> list[Branch]:
        branches = []
        for name in self.repo.list_branches():
            ref_path = self.repo.heads_path / name
            head = ref_path.read_text().strip() if ref_path.exists() else ""
            branches.append(Branch(name=name, head=head))
        return branches

    def create(self, name: str, start_from: str | None = None, privacy: PrivacyLevel = PrivacyLevel.PUBLIC, description: str = "") -> Branch:
        self.repo.create_branch(name, start_from=start_from)
        ref_path = self.repo.heads_path / name
        head = ref_path.read_text().strip() if ref_path.exists() else ""
        return Branch(name=name, head=head, privacy_level=privacy, description=description)

    def delete(self, name: str) -> None:
        self.repo.delete_branch(name)

    def checkout(self, name: str) -> None:
        self.repo.switch_branch(name)

    def current(self) -> str:
        return self.repo.head_ref

    def set_privacy(self, name: str, level: PrivacyLevel) -> None:
        config_path = self.repo.semantic / "branches" / f"{name}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(f'{{"privacy": "{level.value}"}}')

    def get_privacy(self, name: str) -> PrivacyLevel:
        config_path = self.repo.semantic / "branches" / f"{name}.json"
        if config_path.exists():
            import json
            data = json.loads(config_path.read_text())
            return PrivacyLevel(data.get("privacy", "public"))
        return PrivacyLevel.PUBLIC
