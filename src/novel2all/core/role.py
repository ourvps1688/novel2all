"""Role 注册中心。

Role 是 subagent：被 Skill 调用来执行专门任务（角色设计 / 写手 / 一致性检查等）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RoleDefinition(BaseModel):
    """一个 role 的定义。"""

    name: str
    description: str
    system_prompt: str  # role 的完整系统提示
    path: Path
    preferred_model: str | None = None  # role 推荐使用的模型


class RoleRegistry:
    """role 注册中心。"""

    def __init__(self, roles_dir: Path):
        self.roles_dir = roles_dir
        self._registry: dict[str, RoleDefinition] = {}

    def discover(self) -> list[RoleDefinition]:
        """扫描 roles_dir，发现所有 .md。"""
        self._registry.clear()
        if not self.roles_dir.exists():
            return []

        for role_md in sorted(self.roles_dir.glob("*.md")):
            try:
                role = self._load_role(role_md)
                self._registry[role.name] = role
            except (OSError, ValueError, KeyError) as e:
                logger.warning("Failed to load role at %s: %s", role_md, e)

        return list(self._registry.values())

    def _load_role(self, role_md: Path) -> RoleDefinition:
        """加载单个 role markdown。"""
        # 简单的 frontmatter 解析
        text = role_md.read_text(encoding="utf-8")
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                frontmatter = text[3:end].strip()
                content = text[end + 3 :].strip()

                # 解析 frontmatter（极简版）
                meta: dict[str, str] = {}
                for line in frontmatter.split("\n"):
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
            else:
                meta = {}
                content = text
        else:
            meta = {}
            content = text

        return RoleDefinition(
            name=meta.get("name") or role_md.stem,
            description=meta.get("description", ""),
            system_prompt=content,
            path=role_md,
            preferred_model=meta.get("model"),
        )

    def get(self, name: str) -> RoleDefinition | None:
        if not self._registry:
            self.discover()
        return self._registry.get(name)

    def list(self) -> list[RoleDefinition]:
        if not self._registry:
            self.discover()
        return list(self._registry.values())

    def names(self) -> list[str]:
        if not self._registry:
            self.discover()
        return sorted(self._registry.keys())
