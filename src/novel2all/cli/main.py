"""novel2all CLI 主入口。

用法：
    novel2all --help
    novel2all setup                          # 初始化项目
    novel2all status                         # 查看项目状态
    novel2all write 5 --outline "..."        # 写第 5 章
    novel2all review 5                       # 审查第 5 章
    novel2all web                            # 启动 Web UI
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from novel2all import __version__
from novel2all.core import (
    LLMConfig,
    LLMProvider,
    MemoryManager,
)
from novel2all.core.memory import Tracker
from novel2all.core.pipeline import (
    BlockingIssuesError,
    LLMAuthError,
    OutlineNotFoundError,
    PipelineError,
    WritingPipeline,
)
from novel2all.core.project import ProjectStructure
from novel2all.core.role import RoleRegistry
from novel2all.core.skill import SkillRegistry

app = typer.Typer(
    name="novel2all",
    help="novel2all - novel-to-all 创作工具集",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()

# V0.29.3：LLMProvider 单例（缓存 cache stats 跨 CLI 调用连续）
_llm_instance: LLMProvider | None = None


def get_project_root() -> Path:
    """获取当前项目根目录（默认 ./ 或环境变量）。"""
    import os

    root = os.environ.get("NOVEL2ALL_PROJECT", ".")
    return Path(root).resolve()


def get_llm() -> LLMProvider:
    """获取 LLMProvider 单例（V0.29.3）。

    之前每次调用都新建 LLMProvider，导致 cache stats 跨调用重置。
    现在改为模块级单例：首次调用创建并缓存，后续直接返回。

    测试用：reset_llm() 重置单例（强制下次创建新实例）。
    """
    import os

    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMProvider(
            LLMConfig(
                default_model=os.environ.get("NOVEL2ALL_MODEL", "claude-sonnet-4-20250514"),
                api_key_anthropic=os.environ.get("ANTHROPIC_API_KEY"),
                api_key_openai=os.environ.get("OPENAI_API_KEY"),
                api_key_deepseek=os.environ.get("DEEPSEEK_API_KEY"),
            )
        )
    return _llm_instance


def get_llm_for_model(model: str | None) -> LLMProvider:
    """V0.29.4：根据 --model 参数获取 LLMProvider。

    - model=None：返回单例（用环境变量 NOVEL2ALL_MODEL）
    - model=<name>：创建新 LLMProvider（不污染单例，让用户能临时切模型）

    注意：传 model 时返回的不是单例，cache stats 与单例分离（避免混淆）。
    """
    import os

    if model is None:
        return get_llm()
    return LLMProvider(
        LLMConfig(
            default_model=model,
            api_key_anthropic=os.environ.get("ANTHROPIC_API_KEY"),
            api_key_openai=os.environ.get("OPENAI_API_KEY"),
            api_key_deepseek=os.environ.get("DEEPSEEK_API_KEY"),
        )
    )


def reset_llm() -> None:
    """重置 LLMProvider 单例（V0.29.3 测试用）。"""
    global _llm_instance
    _llm_instance = None


@app.command()
def version() -> None:
    """显示版本号。"""
    console.print(f"[bold cyan]novel2all[/bold cyan] v{__version__}")


@app.command()
def status() -> None:
    """显示项目状态。"""
    root = get_project_root()
    tracker = Tracker(root / "_tracking-state.json")

    table = Table(title=f"novel2all 项目状态 ({root})")
    table.add_column("项", style="cyan")
    table.add_column("状态", style="green")

    if tracker.exists():
        state = tracker.read()
        table.add_row("项目名", state.project_name)
        table.add_row("题材", state.genre or "(未设置)")
        table.add_row("文风", state.style_anchor or "(未设置)")
        table.add_row("目标章节", str(state.total_chapters_target or "?"))
        table.add_row("目标字数", str(state.total_word_count_target or "?"))
        table.add_row("当前章节", str(state.last_updated_chapter))
        table.add_row("角色数", str(len(state.characters)))
        table.add_row(
            "活跃伏笔", str(len([f for f in state.foreshadowing.values() if f.status == "active"]))
        )
        table.add_row("时间线条目", str(len(state.timeline)))
        table.add_row("已有摘要", f"{len(state.recent_chapter_summaries)} 章")
        console.print(table)
    else:
        table.add_row("项目状态", "[red]未初始化[/red]")
        table.add_row("提示", "运行 `novel2all setup` 初始化")
        console.print(table)


@app.command()
def setup(
    name: str = typer.Option(..., "--name", "-n", help="项目名（书名）"),
    genre: str = typer.Option(None, "--genre", "-g", help="题材（如 玄幻 / 都市 / 言情）"),
    style: str = typer.Option(None, "--style", "-s", help="文风锚点"),
    chapters: int = typer.Option(None, "--chapters", "-c", help="目标章节数"),
    words: int = typer.Option(None, "--words", "-w", help="目标字数"),
) -> None:
    """初始化项目。"""
    from novel2all.core.project import ProjectStructure

    root = get_project_root()
    project = ProjectStructure(root=root)
    project.init()

    tracker = Tracker(project.tracking_state_file)
    state = tracker.init(
        project_name=name,
        genre=genre,
        style_anchor=style,
        total_chapters_target=chapters,
        total_word_count_target=words,
    )

    # 创建 创作设定.md 模板
    setup_md = project.setup_md
    if not setup_md.exists():
        setup_md.write_text(
            f"""# 创作设定

## 项目名
{name}

## 题材
{genre or "（待填）"}

## 文风
{style or "（待填）"}

## 目标
- 章节数：{chapters or "（待定）"}
- 字数：{words or "（待定）"}

## 主角
（待填）

## 故事梗概
（待填）

## 主线冲突
（待填）

## 世界观设定
（待填）

## 力量体系
（待填）
""",
            encoding="utf-8",
        )

    console.print(f"[bold green]✓[/bold green] 项目已初始化：{root}")
    console.print(f"  项目名：{state.project_name}")
    console.print(f"  文风锚点：{state.style_anchor or '未设置'}")
    console.print(f"  跟踪文件：{project.tracking_state_file}")
    console.print()
    console.print("下一步：")
    console.print("  [cyan]novel2all status[/cyan]                 # 查看状态")
    console.print("  [cyan]novel2all skills list[/cyan]            # 查看可用 skill")
    console.print("  编辑 [cyan]创作设定.md[/cyan] 完善设定")


# === skills 子命令 ===
skills_app = typer.Typer(help="skill 管理")
app.add_typer(skills_app, name="skills")


@skills_app.command("list")
def skills_list() -> None:
    """列出所有可用 skill。"""
    # 找 skills 目录（默认在包内，未来可被项目级覆盖）
    skills_dir = Path(__file__).parent.parent / "skills"
    registry = SkillRegistry(skills_dir)
    registry.discover()

    table = Table(title=f"novel2all skills ({len(registry.list())} 个)")
    table.add_column("name", style="cyan")
    table.add_column("description", style="dim")
    for skill in registry.list():
        desc = skill.description[:80] + "..." if len(skill.description) > 80 else skill.description
        table.add_row(skill.name, desc)
    console.print(table)


# === roles 子命令 ===
roles_app = typer.Typer(help="role 管理")
app.add_typer(roles_app, name="roles")


@roles_app.command("list")
def roles_list() -> None:
    """列出所有可用 role。"""
    roles_dir = Path(__file__).parent.parent / "roles"
    registry = RoleRegistry(roles_dir)
    registry.discover()

    table = Table(title=f"novel2all roles ({len(registry.list())} 个)")
    table.add_column("name", style="cyan")
    table.add_column("description", style="dim")
    for role in registry.list():
        desc = role.description[:80] + "..." if len(role.description) > 80 else role.description
        table.add_row(role.name, desc)
    console.print(table)


# === write 子命令 ===
write_app = typer.Typer(help="写作")
app.add_typer(write_app, name="write")


@write_app.command("chapter")
def write_chapter(
    chapter: int = typer.Argument(..., help="章节号"),
    outline_file: Path = typer.Option(
        None,
        "--outline",
        "-o",
        help="细纲文件路径（默认 大纲/细纲_第NNN章.md）",
        exists=False,
        dir_okay=False,
        readable=True,
    ),
    skill: str = typer.Option(
        "story-long-write", "--skill", "-s", help="使用的 skill（默认 story-long-write）"
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="V0.29.4：指定模型（如 minimax/MiniMax-M3 / deepseek/deepseek-v4-pro）。"
        "默认用环境变量 NOVEL2ALL_MODEL 或配置 default_model。"
        "传 --model 会创建新 provider（不污染单例，cache stats 独立）。",
    ),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="流式输出到 console"),
    min_chars: int = typer.Option(2000, "--min-chars", help="最低字数（低于则警告）"),
    skip_pre_write: bool = typer.Option(
        False,
        "--skip-pre-write/--no-skip-pre-write",
        help="跳过 pre-write check（开发/测试用）",
    ),
) -> None:
    """写第 N 章（v0.21+ 接真实 LLM）。"""
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()  # 加载 .env（DEEPSEEK_API_KEY 等）

    root = get_project_root()
    project = ProjectStructure(root=root)
    if not project.exists():
        console.print("[red]项目未初始化，先跑 novel2all setup[/red]")
        raise typer.Exit(1)

    outline_path = outline_file or project.chapter_outline(chapter)

    # V0.29.4：根据 --model 选 provider（None 时用单例）
    llm = get_llm_for_model(model)
    manager = MemoryManager(project_root=root, llm=llm)
    skills_dir = Path(__file__).parent.parent / "skills"
    skill_registry = SkillRegistry(skills_dir)
    skill_registry.discover()

    pipeline = WritingPipeline(
        manager=manager,
        skill_registry=skill_registry,
        llm=llm,
        project=project,
    )

    console.print(f"[bold]开始写第 {chapter} 章[/bold]")
    console.print(f"  细纲：{outline_path}")
    console.print(f"  skill：{skill}")
    console.print(f"  model：{llm.config.default_model}")  # V0.29.4
    console.print(f"  项目：{root}")
    console.print()

    def on_chunk(chunk: str) -> None:
        if stream:
            typer.echo(chunk, nl=False)

    try:
        result = asyncio.run(
            pipeline.write_chapter(
                chapter=chapter,
                outline_path=outline_path,
                skill_name=skill,
                stream_callback=on_chunk,
                min_chars=min_chars,
                skip_pre_write_check=skip_pre_write,
            )
        )
    except OutlineNotFoundError as e:
        console.print(f"[red]✗ 细纲缺失[/red] {e}")
        raise typer.Exit(1)
    except BlockingIssuesError as e:
        console.print(f"[red]✗ 发现 {len(e.issues)} 个 critical 一致性问题[/red]")
        for issue in e.issues:
            console.print(f"  - [{issue.category}] {issue.description}")
        raise typer.Exit(2)
    except LLMAuthError as e:
        console.print(f"[red]✗ LLM 鉴权失败[/red] {e}")
        console.print("  请检查 .env 里的 API key")
        raise typer.Exit(3)
    except PipelineError as e:
        console.print(f"[red]✗ Pipeline 错误[/red] {e}")
        raise typer.Exit(4)

    if stream:
        console.print()  # 流式输出结束换行
    console.print()
    console.print(f"[green]✓[/green] 第 {chapter} 章已生成")
    console.print(f"  文件：{result.output_path}")
    console.print(f"  字数：{result.content_chars}")
    console.print(f"  pre-write 警告：{len(result.pre_write_issues)} 个")
    console.print(f"  post-write 警告：{len(result.post_write_issues)} 个")
    if result.post_write_issues:
        for issue in result.post_write_issues[:3]:
            console.print(f"    - [{issue.category}] {issue.description}")


@app.command()
def cache_migrate(
    src: str = typer.Option(..., "--src", help="源 cache 文件路径（json 或 sqlite）"),
    dst: str = typer.Option(..., "--dst", help="目标 cache 文件路径（json 或 sqlite）"),
    src_backend: str = typer.Option(
        "auto", "--src-backend", help="源 backend（json / sqlite / auto）"
    ),
    dst_backend: str = typer.Option(
        "auto", "--dst-backend", help="目标 backend（json / sqlite / auto）"
    ),
    max_size: int = typer.Option(1024, "--max-size", help="目标 max_size"),
    ttl: int = typer.Option(0, "--ttl", help="目标 TTL（秒），0 = 永不过期"),
) -> None:
    """V0.43：在不同 cache backend 之间平滑迁移（零数据丢失）。

    典型场景：JSONFile 升级到 SQLite（更好并发、跨 OS 共享）。

    自动检测 backend 类型（从文件后缀：.json / .db）。

    示例：
        novel2all cache-migrate --src .novel2all/cache.json --dst .novel2all/cache.db
    """
    from novel2all.core.migration import migrate_cache

    # auto-detect backend from extension
    if src_backend == "auto":
        if src.endswith(".json"):
            src_backend = "json"
        elif src.endswith((".db", ".sqlite")):
            src_backend = "sqlite"
        elif src.startswith("redis://"):
            src_backend = "redis"
        else:
            console.print(f"[red]无法自动检测 src backend（{src}），请显式指定 --src-backend[/red]")
            raise typer.Exit(1)
    if dst_backend == "auto":
        if dst.endswith(".json"):
            dst_backend = "json"
        elif dst.endswith((".db", ".sqlite")):
            dst_backend = "sqlite"
        elif dst.startswith("redis://"):
            dst_backend = "redis"
        else:
            console.print(f"[red]无法自动检测 dst backend（{dst}），请显式指定 --dst-backend[/red]")
            raise typer.Exit(1)

    if src_backend == "memory" or dst_backend == "memory":
        console.print("[red]memory backend 不支持迁移（无持久化）[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]迁移 cache: {src_backend} → {dst_backend}[/bold cyan]")
    console.print(f"  src: {src}")
    console.print(f"  dst: {dst}")

    def progress(done: int, total: int) -> None:
        pct = (done / total * 100) if total > 0 else 100
        console.print(f"  进度: {done}/{total} ({pct:.1f}%)")

    result = migrate_cache(
        src_backend=src_backend,
        dst_backend=dst_backend,
        src_path=src,
        dst_path=dst,
        max_size=max_size,
        ttl_seconds=ttl,
        progress_callback=progress,
    )

    console.print(f"\n[green]{result.summary()}[/green]")

    if result.errors:
        console.print(f"\n[red]警告：{len(result.errors)} 条迁移失败[/red]")
        for err in result.errors[:5]:
            console.print(f"  - {err}")
        raise typer.Exit(1)

    if result.migrated > 0:
        console.print(
            f"\n[bold yellow]提示：迁移成功！建议备份或删除源文件 {src}（手动）[/bold yellow]"
        )


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8765, "--port", "-p"),
) -> None:
    """启动 Web UI。"""
    import uvicorn

    from novel2all.web.app import create_app

    console.print(f"[bold cyan]novel2all Web UI[/bold cyan] -> http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
