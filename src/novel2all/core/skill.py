"""Skill 加载器与注册中心。"""

from __future__ import annotations

from pathlib import Path

import frontmatter
from pydantic import BaseModel


class SkillDefinition(BaseModel):
    """一个 skill 的定义。"""

    name: str
    description: str
    content: str  # SKILL.md 正文（去掉 frontmatter）
    path: Path  # SKILL.md 文件路径
    references_dir: Path | None = None
    scripts_dir: Path | None = None
    user_invocable: bool = True
    model_invocable: bool = True


class SkillRegistry:
    """skill 注册中心。"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self._registry: dict[str, SkillDefinition] = {}

    def discover(self) -> list[SkillDefinition]:
        """扫描 skills_dir，发现所有 SKILL.md。"""
        self._registry.clear()
        if not self.skills_dir.exists():
            return []

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skill = self._load_skill(skill_md)
                self._registry[skill.name] = skill
            except (OSError, ValueError, KeyError) as e:
                # 单个 skill 失败不影响其他
                import sys

                print(f"Failed to load skill at {skill_md}: {e}", file=sys.stderr)

        return list(self._registry.values())

    def _load_skill(self, skill_md: Path) -> SkillDefinition:
        """加载单个 SKILL.md。"""
        post = frontmatter.load(skill_md)
        meta = post.metadata or {}

        return SkillDefinition(
            name=meta.get("name") or skill_md.parent.name,
            description=meta.get("description", ""),
            content=post.content,
            path=skill_md,
            references_dir=skill_md.parent / "references",
            scripts_dir=skill_md.parent / "scripts",
            user_invocable=meta.get("user-invocable", True) is not False,
            model_invocable=meta.get("model-invocable", True) is not False,
        )

    def get(self, name: str) -> SkillDefinition | None:
        if not self._registry:
            self.discover()
        return self._registry.get(name)

    def list(self) -> list[SkillDefinition]:
        if not self._registry:
            self.discover()
        return list(self._registry.values())

    def names(self) -> list[str]:
        if not self._registry:
            self.discover()
        return sorted(self._registry.keys())
