"""V1.0.2 B2：项目设定文件 hash（用于 LLM cache 失效）。

背景：
- 用户修改 ``创作设定.md`` 或 ``设定/文风.md`` 后，旧 cache 条目应该失效
- 否则会用旧设定生成的 cache 响应（不符合新风格）
- 解法：每次 ``_make_cache_key`` 时计算 settings hash，纳入 cache key

设计：
- 收集所有"可能影响 LLM 输出的设定文件"，拼接后 sha256 截前 16 字符
- 路径基于 ``project_root``（项目根目录，含 ``正文/``、``设定/`` 等子目录）
- 设定文件不存在时按空字符串处理（避免 Path 错误）
- 排序：角色设定按文件名排序（确保 hash 稳定）

注意：
- 这是"项目级"hash，不是"全局"hash
- 不同项目的 hash 独立（避免跨项目 cache 污染）
- 单项目内 hash 变化时（如编辑文风），旧 cache 自动失效
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# 模块常量：定义哪些文件影响 cache
# V1.0.2：基础设定（创作设定 + 文风 + 角色列表）
SETTING_FILES: tuple[str, ...] = (
    "创作设定.md",
    "设定/文风.md",
)
# 角色设定目录
ROLES_SUBDIR: str = "设定/角色"
# 角色文件 glob 模式
ROLES_GLOB: str = "*.md"


def compute_settings_hash(project_root: Path | None) -> str:
    """V1.0.2 B2：计算项目设定文件 hash（用于 cache 失效）。

    流程：
    1. 收集 ``创作设定.md``、``设定/文风.md``、``设定/角色/*.md`` 的内容
    2. 拼接后 sha256，截前 16 字符
    3. 任何文件不存在 → 跳过（不参与 hash）

    Args:
        project_root: 项目根目录。``None`` 或不存在 → 返回空 hash（向后兼容）。

    Returns:
        16 字符 hex string（sha256 截前 16 字符）。空项目 / ``None`` → 全 0。
    """
    if project_root is None:
        return "0" * 16
    root = Path(project_root)
    if not root.exists() or not root.is_dir():
        return "0" * 16

    # V1.0.2：收集所有相关文件的内容（只包含存在的文件）
    parts: list[str] = []
    for rel in SETTING_FILES:
        path = root / rel
        if path.exists() and path.is_file():
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue

    # 角色设定（按文件名排序，确保 hash 稳定）
    roles_dir = root / ROLES_SUBDIR
    if roles_dir.exists() and roles_dir.is_dir():
        for role_file in sorted(roles_dir.glob(ROLES_GLOB)):
            if role_file.is_file():
                try:
                    parts.append(role_file.read_text(encoding="utf-8"))
                except OSError:
                    continue

    if not parts:
        # 无任何设定文件 → 全 0 hash（向后兼容 + 跨空项目一致）
        return "0" * 16

    content = "|".join(parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
