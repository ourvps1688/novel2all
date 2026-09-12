"""项目结构管理。

novel2all 的项目目录布局：

{project_root}/
├── _tracking-state.json         # 机器可读的项目状态（MemoryManager.tracker）
├── 创作设定.md                   # 用户初始创作设定
├── 设定/
│   ├── 文风.md                  # 文风锚点（L1 永远加载）
│   ├── 世界观/                  # 力量体系 / 地理 / 背景
│   └── 角色/                    # 角色档案（每个角色一个文件）
├── 大纲/
│   ├── 大纲.md                  # 全书卷级结构
│   ├── 卷纲_第N卷.md            # 每卷的详细大纲
│   └── 细纲_第NNN章.md          # 每章细纲（pre-write hook 检查）
├── 正文/
│   └── 第NNN章_章名.md          # 每章正文
├── 拆文库/                      # 对标参考书拆文
│   └── {书名}/
│       ├── 拆文报告.md
│       ├── 角色/
│       ├── 剧情/
│       └── 设定/
└── .novel2all/                  # novel2all 内部元数据
    ├── memory.db                # 向量数据库（v0.21+）
    └── cache/                   # 临时缓存
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class ProjectStructure(BaseModel):
    """项目目录结构。"""

    root: Path

    @property
    def tracking_state_file(self) -> Path:
        return self.root / "_tracking-state.json"

    @property
    def setup_md(self) -> Path:
        return self.root / "创作设定.md"

    @property
    def style_md(self) -> Path:
        return self.root / "设定" / "文风.md"

    @property
    def worldview_dir(self) -> Path:
        return self.root / "设定" / "世界观"

    @property
    def characters_dir(self) -> Path:
        return self.root / "设定" / "角色"

    @property
    def outline_dir(self) -> Path:
        return self.root / "大纲"

    def chapter_outline(self, chapter: int) -> Path:
        """第 N 章的细纲。"""
        return self.outline_dir / f"细纲_第{chapter:03d}章.md"

    @property
    def prose_dir(self) -> Path:
        return self.root / "正文"

    def chapter_prose(self, chapter: int) -> Path:
        """第 N 章的正文。"""
        return self.prose_dir / f"第{chapter:03d}章.md"

    @property
    def reference_lib_dir(self) -> Path:
        return self.root / "拆文库"

    @property
    def metadata_dir(self) -> Path:
        return self.root / ".novel2all"

    def init(self) -> None:
        """初始化项目目录结构。"""
        self.root.mkdir(parents=True, exist_ok=True)
        for d in [
            self.worldview_dir,
            self.characters_dir,
            self.outline_dir,
            self.prose_dir,
            self.reference_lib_dir,
            self.metadata_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.tracking_state_file.exists()
