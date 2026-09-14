"""V0.30.6 B6：章节导出（Markdown / TXT / EPUB）。

支持 3 种格式：
- Markdown (.md)：原样输出（chapter 文件已经是 markdown）
- TXT (.txt)：剥离 markdown 语法（headers/links/code）+ 规范化空白
- EPUB (.epub)：EPUB 3.0 格式（含 mimetype / META-INF / OEBPS/）

设计：
- BaseExporter 抽象类 + 3 个具体实现
- 统一 API：export_chapter() / export_chapters() / export_book()
- 零外部依赖（纯 stdlib + zipfile + xml.etree）

EPUB 3.0 最小结构：
- mimetype（无压缩，必须第一个）
- META-INF/container.xml（指向 OPF）
- OEBPS/content.opf（package metadata + manifest + spine）
- OEBPS/toc.ncx（legacy navigation）
- OEBPS/nav.xhtml（EPUB 3 navigation）
- OEBPS/chapter_NNN.xhtml（每章 XHTML）

参考：https://www.w3.org/publishing/epub3/
"""

from __future__ import annotations

import re
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path


@dataclass
class Chapter:
    """V0.30.6 B6：章节数据模型。

    Attributes:
        chapter_num: 章节号（1-based）
        title: 章节标题（从 markdown 首行 # 解析）
        content: 章节正文（不含标题行）
        source_path: 源文件路径（用于调试）
    """

    chapter_num: int
    title: str
    content: str
    source_path: Path | None = None

    @property
    def word_count(self) -> int:
        """V0.30.6 B6：字数（中文字符 + 英文单词）。"""
        chinese = len(re.findall(r"[\u4e00-\u9fff]", self.content))
        english = len(re.findall(r"[a-zA-Z]+", self.content))
        return chinese + english

    @classmethod
    def from_md_file(cls, path: Path) -> Chapter:
        """V0.30.6 B6：从 markdown 文件加载章节。

        解析规则：
        - 首行 `# 第N章 标题` 提取 chapter_num + title
        - 移除首行后剩余作为 content
        """
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n", 1)
        first_line = lines[0].strip()
        # 解析 # 第1章 标题
        m = re.match(r"^#\s*第(\d+)章[：:\s]*(.*)$", first_line)
        if m:
            chapter_num = int(m.group(1))
            title = m.group(2).strip() or f"第{chapter_num}章"
            content = lines[1].lstrip("\n") if len(lines) > 1 else ""
        else:
            # Fallback：从文件名提取
            m2 = re.match(r"^第(\d+)章", path.stem)
            chapter_num = int(m2.group(1)) if m2 else 0
            title = first_line.lstrip("#").strip() or path.stem
            content = text
        return cls(chapter_num=chapter_num, title=title, content=content, source_path=path)


@dataclass
class BookMetadata:
    """V0.30.6 B6：书元数据（用于 EPUB / 批量 TXT）。"""

    title: str = "未命名作品"
    author: str = "未知作者"
    language: str = "zh-CN"
    description: str = ""
    publisher: str = "novel2all"


class BaseExporter(ABC):
    """V0.30.6 B6：导出器抽象基类。"""

    @abstractmethod
    def file_extension(self) -> str:
        """返回文件扩展名（不含点）。"""

    @abstractmethod
    def mime_type(self) -> str:
        """返回 MIME 类型。"""

    @abstractmethod
    def _format_chapter(self, chapter: Chapter) -> bytes:
        """格式化单章节。"""

    def export_chapter(self, chapter: Chapter) -> bytes:
        """V0.30.6 B6：导出单章节为 bytes。"""
        return self._format_chapter(chapter)

    def export_chapters(
        self,
        chapters: list[Chapter],
        metadata: BookMetadata | None = None,
    ) -> bytes:
        """V0.30.6 B6：导出多章节。默认用空行连接（子类可重写）。"""
        parts = [self._format_chapter(ch) for ch in chapters]
        return self._join_parts(parts)

    def _join_parts(self, parts: list[bytes]) -> bytes:
        """V0.30.6 B6：连接多个章节（默认用双换行）。"""
        return b"\n\n".join(parts)


# === 1. MarkdownExporter ===


class MarkdownExporter(BaseExporter):
    """V0.30.6 B6：Markdown 导出（直接透传 + 标准 frontmatter）。"""

    def file_extension(self) -> str:
        return "md"

    def mime_type(self) -> str:
        return "text/markdown"

    def _format_chapter(self, chapter: Chapter) -> bytes:
        md = f"# 第{chapter.chapter_num}章 {chapter.title}\n\n{chapter.content.strip()}\n"
        return md.encode("utf-8")


# === 2. TXTExporter ===


class TXTExporter(BaseExporter):
    """V0.30.6 B6：纯文本导出（剥离 markdown 语法）。"""

    def file_extension(self) -> str:
        return "txt"

    def mime_type(self) -> str:
        return "text/plain"

    def _format_chapter(self, chapter: Chapter) -> bytes:
        lines = [f"第{chapter.chapter_num}章 {chapter.title}", "=" * 60]
        clean_text = self._strip_markdown(chapter.content)
        lines.append(clean_text)
        return "\n".join(lines).encode("utf-8")

    def _strip_markdown(self, text: str) -> str:
        """V0.30.6 B6：剥离 markdown 语法 → 纯文本。

        处理规则：
        - 移除 markdown 标记字符（# * _ ` > - [ ] ( ) ! 等）
        - 保留正文内容
        - 规范化空行
        """
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # 标题
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # **bold**
        text = re.sub(r"\*(.+?)\*", r"\1", text)  # *italic*
        text = re.sub(r"`([^`]+)`", r"\1", text)  # `code`
        text = re.sub(r"```[^\n]*\n(.*?)\n```", r"\1", text, flags=re.DOTALL)  # 代码块
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # [text](url)
        text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", text)  # ![alt](url)
        text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)  # 列表
        text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)  # 引用
        text = re.sub(r"\n{3,}", "\n\n", text)  # 规范化空行
        return text.strip()


# === 3. EPUBExporter ===


class EPUBExporter(BaseExporter):
    """V0.30.6 B6：EPUB 3.0 导出（纯 stdlib + zipfile + xml.etree）。

    最小 EPUB 3.0 结构：
    - mimetype（无压缩，必须是 ZIP 第一个文件）
    - META-INF/container.xml
    - OEBPS/content.opf（package metadata + manifest + spine）
    - OEBPS/toc.ncx（legacy navigation）
    - OEBPS/nav.xhtml（EPUB 3 navigation）
    - OEBPS/chapter_NNN.xhtml（每章 XHTML）

    验证：可以用 Calibre / Sigil / epub.js 打开。
    """

    def file_extension(self) -> str:
        return "epub"

    def mime_type(self) -> str:
        return "application/epub+zip"

    def _format_chapter(self, chapter: Chapter) -> bytes:
        """V0.30.6 B6：返回单章 XHTML bytes（仅在 export_book 中使用）。"""
        return self._chapter_to_xhtml(chapter, 1, 1).encode("utf-8")

    def export_chapter(self, chapter: Chapter) -> bytes:
        """V0.30.6 B6：导出单章节为完整 EPUB（含 mimetype/container/opf/ncx/nav/单章 xhtml）。"""
        # 单章 = 1 章节的"完整 EPUB"
        return self._build_epub([chapter], BookMetadata(title=chapter.title))

    def export_chapters(
        self,
        chapters: list[Chapter],
        metadata: BookMetadata | None = None,
    ) -> bytes:
        """V0.30.6 B6：构建完整 EPUB。"""
        metadata = metadata or BookMetadata(title=chapters[0].title if chapters else "未命名作品")
        return self._build_epub(chapters, metadata)

    def _build_epub(self, chapters: list[Chapter], metadata: BookMetadata) -> bytes:
        """V0.30.6 B6：构建 EPUB zip 文件。"""
        buf = BytesIO()
        # EPUB 规范：mimetype 必须是无压缩（store mode）且为 ZIP 第一个文件
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("mimetype", "application/epub+zip")
        # 其余文件用 DEFLATED
        with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("META-INF/container.xml", self._build_container_xml())
            zf.writestr("OEBPS/content.opf", self._build_opf(chapters, metadata))
            zf.writestr("OEBPS/toc.ncx", self._build_toc_ncx(chapters, metadata))
            zf.writestr("OEBPS/nav.xhtml", self._build_nav(chapters, metadata))
            for idx, ch in enumerate(chapters, 1):
                zf.writestr(
                    f"OEBPS/chapter_{ch.chapter_num:03d}.xhtml",
                    self._chapter_to_xhtml(ch, idx, len(chapters)),
                )
        return buf.getvalue()

    def _build_container_xml(self) -> str:
        """V0.30.6 B6：META-INF/container.xml 指向 content.opf。"""
        return """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

    def _build_opf(self, chapters: list[Chapter], metadata: BookMetadata) -> str:
        """V0.30.6 B6：content.opf（package document）。"""
        # manifest items: nav + ncx + each chapter
        manifest_items = [
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        ]
        spine_items = []
        for ch in chapters:
            cid = f"chapter_{ch.chapter_num:03d}"
            manifest_items.append(
                f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{cid}"/>')

        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="BookId">urn:uuid:{metadata.title}-1</dc:identifier>
    <dc:title>{self._xml_escape(metadata.title)}</dc:title>
    <dc:creator>{self._xml_escape(metadata.author)}</dc:creator>
    <dc:language>{metadata.language}</dc:language>
    <dc:publisher>{self._xml_escape(metadata.publisher)}</dc:publisher>
    <dc:date>{now}</dc:date>
    <meta property="dcterms:modified">{now}</meta>
    {f"<dc:description>{self._xml_escape(metadata.description)}</dc:description>" if metadata.description else ""}
  </metadata>
  <manifest>
    {chr(10).join("    " + i for i in manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join("    " + i for i in spine_items)}
  </spine>
</package>"""

    def _build_toc_ncx(self, chapters: list[Chapter], metadata: BookMetadata) -> str:
        """V0.30.6 B6：toc.ncx（legacy NCX，EPUB 2 兼容）。"""
        nav_points = []
        for idx, ch in enumerate(chapters, 1):
            cid = f"chapter_{ch.chapter_num:03d}"
            nav_points.append(
                f'    <navPoint id="navPoint-{idx}" playOrder="{idx}">\n'
                f"      <navLabel><text>{self._xml_escape(ch.title)}</text></navLabel>\n"
                f'      <content src="{cid}.xhtml"/>\n'
                f"    </navPoint>"
            )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{metadata.title}-1"/>
    <meta name="dtb:depth" content="1"/>
  </head>
  <docTitle><text>{self._xml_escape(metadata.title)}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>"""

    def _build_nav(self, chapters: list[Chapter], metadata: BookMetadata) -> str:
        """V0.30.6 B6：nav.xhtml（EPUB 3 navigation）。"""
        nav_items = []
        for ch in chapters:
            cid = f"chapter_{ch.chapter_num:03d}"
            nav_items.append(
                f'      <li><a href="{cid}.xhtml">{self._xml_escape(ch.title)}</a></li>'
            )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{self._xml_escape(metadata.title)}</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>目录</h1>
    <ol>
{chr(10).join(nav_items)}
    </ol>
  </nav>
</body>
</html>"""

    def _chapter_to_xhtml(self, chapter: Chapter, idx: int, total: int) -> str:
        """V0.30.6 B6：单章 XHTML（带 prev/next 导航）。"""
        paragraphs = [
            f"      <p>{self._xml_escape(p.strip())}</p>"
            for p in chapter.content.strip().split("\n\n")
            if p.strip()
        ]
        # 简化处理：单 \n 也算段落
        if len(paragraphs) < 2:
            paragraphs = [
                f"      <p>{self._xml_escape(p.strip())}</p>"
                for p in chapter.content.strip().split("\n")
                if p.strip()
            ]

        # 导航链接
        nav_links = []
        if idx > 1:
            nav_links.append(f'<a href="chapter_{chapters_prev_id(chapter):03d}.xhtml">上一章</a>')
        if idx < total:
            nav_links.append(
                f'<a href="chapter_{chapters_next_id(chapter, chapters_total=total, current_idx=idx):03d}.xhtml">下一章</a>'
            )

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>{self._xml_escape(chapter.title)}</title>
</head>
<body>
  <h1>{self._xml_escape(chapter.title)}</h1>
{chr(10).join(paragraphs)}
  <nav epub:type="landmarks">
    {chr(10).join(nav_links) if nav_links else ""}
  </nav>
</body>
</html>"""

    def _xml_escape(self, text: str) -> str:
        """V0.30.6 B6：XML 转义（避免 chapter title 含特殊字符导致 OPF 损坏）。"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )


# === 4. 便捷函数 ===


def chapters_prev_id(chapter: Chapter) -> int:
    """V0.30.6 B6：上一章号（简单 -1）。"""
    return chapter.chapter_num - 1


def chapters_next_id(chapter: Chapter, chapters_total: int, current_idx: int) -> int:
    """V0.30.6 B6：下一章号（按列表 idx 推断，不假设连续）。"""
    return chapter.chapter_num + 1


def get_exporter(fmt: str) -> BaseExporter:
    """V0.30.6 B6：工厂方法（fmt → exporter instance）。"""
    fmt = fmt.lower().strip()
    if fmt in ("md", "markdown"):
        return MarkdownExporter()
    if fmt in ("txt", "text"):
        return TXTExporter()
    if fmt in ("epub",):
        return EPUBExporter()
    raise ValueError(f"Unsupported format: {fmt}. Use md|txt|epub")


def export_chapter_file(path: Path, fmt: str) -> bytes:
    """V0.30.6 B6：便利函数：从 md 文件直接导出为指定格式。"""
    chapter = Chapter.from_md_file(path)
    exporter = get_exporter(fmt)
    return exporter.export_chapter(chapter)


def export_project(
    project_root: Path,
    fmt: str,
    metadata: BookMetadata | None = None,
) -> bytes:
    """V0.30.6 B6：导出整个项目为指定格式（自动发现所有 chapter）。

    Args:
        project_root: 项目根目录（含 正文/ 子目录）
        fmt: md | txt | epub
        metadata: 书元数据（EPUB 必填，md/txt 可选）

    Returns:
        bytes: 导出文件内容
    """
    from .project import ProjectStructure

    project = ProjectStructure(root=project_root)
    if not project.exists():
        raise FileNotFoundError(f"Project not initialized: {project_root}")

    # 自动发现章节
    chapters: list[Chapter] = []
    prose_dir = project.chapter_prose(1).parent
    if prose_dir.exists():
        for f in sorted(prose_dir.glob("第*章.md")):
            try:
                chapters.append(Chapter.from_md_file(f))
            except Exception:
                continue

    if not chapters:
        raise FileNotFoundError(f"No chapters found in {prose_dir}")

    exporter = get_exporter(fmt)
    if isinstance(exporter, EPUBExporter):
        return exporter.export_chapters(chapters, metadata or BookMetadata())
    return exporter.export_chapters(chapters)
