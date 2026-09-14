"""V0.30.6 B6：章节导出单元测试。

测试范围：
1. Chapter 数据模型 + from_md_file 解析
2. MarkdownExporter（透传 + frontmatter）
3. TXTExporter（剥离 markdown + 规范化空行）
4. EPUBExporter（完整 EPUB 3.0 结构）
5. 工厂函数 get_exporter
6. export_project 集成
7. Web 端点 /api/chapter/{n}/export 和 /api/export
8. 边界情况（空 chapter / 特殊字符 / 超长内容）
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel2all.core.exporter import (
    BookMetadata,
    Chapter,
    EPUBExporter,
    MarkdownExporter,
    TXTExporter,
    export_chapter_file,
    get_exporter,
)
from novel2all.web.app import create_app

# === Test 1：Chapter 数据模型 ===


def test_chapter_from_md_parses_title() -> None:
    """V0.30.6 B6：Chapter.from_md_file 解析 # 第N章 标题。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# 第5章 林雷觉醒\n\n林雷在废墟中醒来...")
        path = Path(f.name)
    try:
        ch = Chapter.from_md_file(path)
        assert ch.chapter_num == 5
        assert ch.title == "林雷觉醒"
        assert "林雷在废墟中醒来" in ch.content
    finally:
        path.unlink()


def test_chapter_from_md_handles_no_title() -> None:
    """V0.30.6 B6：缺少 # 标题行时 fallback 到文件名。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("这是没有标题行的章节内容。")
        path = Path(f.name)
    try:
        ch = Chapter.from_md_file(path)
        # 应 fallback：chapter_num = 0 (因为文件名不含 第N章)
        assert ch.chapter_num == 0
        assert "没有标题行" in ch.content or ch.title != ""
    finally:
        path.unlink()


def test_chapter_word_count_chinese() -> None:
    """V0.30.6 B6：word_count 正确统计中文字符（不含标点）。"""
    # 你好世界这是一个测试 = 10 个中文字符（标点 ，。 不计）
    ch = Chapter(chapter_num=1, title="test", content="你好世界，这是一个测试。")
    assert ch.word_count == 10


def test_chapter_word_count_mixed() -> None:
    """V0.30.6 B6：word_count 中英文混合统计。"""
    # 中文：你好这/是/一/个/句/子 = 8；英文：world + test = 2 → 共 10
    ch = Chapter(chapter_num=1, title="test", content="你好 world 这是一个 test 句子。")
    assert ch.word_count == 10


# === Test 2：MarkdownExporter ===


def test_markdown_exporter_basic() -> None:
    """V0.30.6 B6：MarkdownExporter 透传 + 标题行。"""
    exporter = MarkdownExporter()
    ch = Chapter(chapter_num=1, title="测试章", content="这是内容。")
    output = exporter.export_chapter(ch)
    text = output.decode("utf-8")
    assert "# 第1章 测试章" in text
    assert "这是内容。" in text
    assert exporter.file_extension() == "md"
    assert exporter.mime_type() == "text/markdown"


def test_markdown_exporter_multiple_chapters() -> None:
    """V0.30.6 B6：MarkdownExporter 拼接多章节。"""
    exporter = MarkdownExporter()
    chapters = [
        Chapter(chapter_num=1, title="第一章", content="第一段。"),
        Chapter(chapter_num=2, title="第二章", content="第二段。"),
    ]
    output = exporter.export_chapters(chapters)
    text = output.decode("utf-8")
    assert "# 第1章 第一章" in text
    assert "# 第2章 第二章" in text
    assert "第一段。" in text
    assert "第二段。" in text


# === Test 3：TXTExporter ===


def test_txt_exporter_basic() -> None:
    """V0.30.6 B6：TXTExporter 剥离 markdown 语法。"""
    exporter = TXTExporter()
    ch = Chapter(
        chapter_num=1,
        title="测试",
        content="# 内部标题\n\n这是**粗体**和*斜体*。\n\n[链接](http://example.com)。",
    )
    output = exporter.export_chapter(ch)
    text = output.decode("utf-8")
    assert "第1章 测试" in text
    assert "====" in text  # 分隔符
    assert "# 内部标题" not in text  # markdown 标记被剥离
    assert "**粗体**" not in text
    assert "粗体" in text  # 内容保留
    assert "链接" in text  # 链接文本保留
    assert "http://example.com" not in text  # URL 被剥离


def test_txt_exporter_strips_code_blocks() -> None:
    """V0.30.6 B6：TXTExporter 剥离代码块标记。"""
    exporter = TXTExporter()
    ch = Chapter(
        chapter_num=1,
        title="test",
        content="```python\nprint('hello')\n```\n\n正常文本。",
    )
    text = exporter.export_chapter(ch).decode("utf-8")
    assert "```" not in text
    assert "print" in text
    assert "正常文本" in text


def test_txt_exporter_strips_lists() -> None:
    """V0.30.6 B6：TXTExporter 剥离列表标记。"""
    exporter = TXTExporter()
    ch = Chapter(
        chapter_num=1,
        title="test",
        content="- 第一项\n- 第二项\n- 第三项",
    )
    text = exporter.export_chapter(ch).decode("utf-8")
    assert "- 第一项" not in text
    assert "第一项" in text


def test_txt_exporter_normalizes_blank_lines() -> None:
    """V0.30.6 B6：TXTExporter 规范化连续空行（最多 2）。"""
    exporter = TXTExporter()
    ch = Chapter(
        chapter_num=1,
        title="test",
        content="段落1\n\n\n\n\n段落2",
    )
    text = exporter.export_chapter(ch).decode("utf-8")
    # 不应该有 3+ 连续换行
    assert "\n\n\n\n" not in text


# === Test 4：EPUBExporter ===


def test_epub_exporter_has_required_files() -> None:
    """V0.30.6 B6：EPUBExporter 生成完整结构（含 mimetype/container/opf/ncx/nav/chapters）。"""
    exporter = EPUBExporter()
    chapters = [
        Chapter(chapter_num=1, title="第一章", content="第一段。"),
        Chapter(chapter_num=2, title="第二章", content="第二段。"),
    ]
    metadata = BookMetadata(title="测试书", author="测试作者")
    data = exporter.export_chapters(chapters, metadata)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "mimetype" in names
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names
        assert "OEBPS/toc.ncx" in names
        assert "OEBPS/nav.xhtml" in names
        assert "OEBPS/chapter_001.xhtml" in names
        assert "OEBPS/chapter_002.xhtml" in names


def test_epub_mimetype_is_uncompressed() -> None:
    """V0.30.6 B6：EPUB mimetype 必须无压缩（EPUB 规范要求）。"""
    exporter = EPUBExporter()
    chapters = [Chapter(chapter_num=1, title="t", content="c")]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED  # 0 = no compression
        assert zf.read("mimetype").decode("ascii") == "application/epub+zip"


def test_epub_container_xml_points_to_opf() -> None:
    """V0.30.6 B6：META-INF/container.xml 正确指向 content.opf。"""
    exporter = EPUBExporter()
    chapters = [Chapter(chapter_num=1, title="t", content="c")]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        container = zf.read("META-INF/container.xml").decode("utf-8")
        assert 'full-path="OEBPS/content.opf"' in container


def test_epub_opf_has_metadata_and_spine() -> None:
    """V0.30.6 B6：content.opf 含 metadata + manifest + spine。"""
    exporter = EPUBExporter()
    chapters = [Chapter(chapter_num=1, title="第一章", content="c")]
    metadata = BookMetadata(title="我的书", author="我", language="zh-CN")
    data = exporter.export_chapters(chapters, metadata)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:title>我的书</dc:title>" in opf
        assert "<dc:creator>我</dc:creator>" in opf
        assert 'xmlns="http://www.idpf.org/2007/opf"' in opf
        assert "<spine" in opf
        assert "<manifest" in opf
        assert 'href="chapter_001.xhtml"' in opf


def test_epub_chapter_xhtml_valid() -> None:
    """V0.30.6 B6：每章生成有效 XHTML（含标题 + 段落）。"""
    exporter = EPUBExporter()
    chapters = [Chapter(chapter_num=1, title="测试章", content="这是第一段。\n\n这是第二段。")]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xhtml = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
        assert "<?xml version" in xhtml
        assert "DOCTYPE html" in xhtml
        assert "测试章" in xhtml
        assert "这是第一段。" in xhtml
        assert "这是第二段。" in xhtml


def test_epub_xml_escapes_special_chars() -> None:
    """V0.30.6 B6：EPUB 正确转义 XML 特殊字符（防止文件损坏）。"""
    exporter = EPUBExporter()
    chapters = [Chapter(chapter_num=1, title='Tom & Jerry "test" <book>', content="<>&\"'")]
    metadata = BookMetadata(title="A & B")
    data = exporter.export_chapters(chapters, metadata)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # toc.ncx 含 chapter title（应正确转义）
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
        assert "Tom &amp; Jerry" in ncx
        assert "&quot;test&quot;" in ncx
        assert "&lt;book&gt;" in ncx
        # opf 含 book title
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "A &amp; B" in opf
        # chapter xhtml 含 content（应转义）
        xhtml = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
        assert "&lt;&gt;" in xhtml
        assert "&amp;" in xhtml


def test_epub_ncx_includes_all_chapters() -> None:
    """V0.30.6 B6：toc.ncx 含所有章节的 navPoint。"""
    exporter = EPUBExporter()
    chapters = [
        Chapter(chapter_num=1, title="ch1", content="c1"),
        Chapter(chapter_num=2, title="ch2", content="c2"),
        Chapter(chapter_num=3, title="ch3", content="c3"),
    ]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
        assert 'playOrder="1"' in ncx
        assert 'playOrder="2"' in ncx
        assert 'playOrder="3"' in ncx
        assert "ch1" in ncx
        assert "ch2" in ncx
        assert "ch3" in ncx


def test_epub_format_chapter_returns_xhtml() -> None:
    """V0.30.6 B6：单章 _format_chapter 返回 XHTML。"""
    exporter = EPUBExporter()
    ch = Chapter(chapter_num=1, title="t", content="content")
    output = exporter._format_chapter(ch)
    # _format_chapter 返回 str（与 _chapter_to_xhtml 一致）
    if isinstance(output, bytes):
        output = output.decode("utf-8")
    assert "DOCTYPE html" in output
    assert "t" in output


# === Test 5：工厂函数 ===


def test_get_exporter_md() -> None:
    """V0.30.6 B6：get_exporter("md") 返回 MarkdownExporter。"""
    exp = get_exporter("md")
    assert isinstance(exp, MarkdownExporter)


def test_get_exporter_markdown_alias() -> None:
    """V0.30.6 B6：get_exporter("markdown") 是 md 的别名。"""
    assert isinstance(get_exporter("markdown"), MarkdownExporter)


def test_get_exporter_txt() -> None:
    """V0.30.6 B6：get_exporter("txt") 返回 TXTExporter。"""
    exp = get_exporter("txt")
    assert isinstance(exp, TXTExporter)


def test_get_exporter_epub() -> None:
    """V0.30.6 B6：get_exporter("epub") 返回 EPUBExporter。"""
    exp = get_exporter("epub")
    assert isinstance(exp, EPUBExporter)


def test_get_exporter_invalid_raises() -> None:
    """V0.30.6 B6：get_exporter("invalid") 抛 ValueError。"""
    with pytest.raises(ValueError, match="Unsupported format"):
        get_exporter("invalid_format")


# === Test 6：便捷函数 ===


def test_export_chapter_file_function() -> None:
    """V0.30.6 B6：export_chapter_file() 从 md 文件直接导出。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("# 第3章 第三个\n\ncontent here")
        path = Path(f.name)
    try:
        output = export_chapter_file(path, "md")
        text = output.decode("utf-8")
        assert "# 第3章 第三个" in text
    finally:
        path.unlink()


# === Test 7：边界情况 ===


def test_chapter_with_empty_content() -> None:
    """V0.30.6 B6：空内容章节不应崩溃。"""
    exporter = MarkdownExporter()
    ch = Chapter(chapter_num=1, title="空章", content="")
    output = exporter.export_chapter(ch)
    text = output.decode("utf-8")
    assert "# 第1章 空章" in text


def test_chapter_with_only_newlines() -> None:
    """V0.30.6 B6：仅换行的内容不应崩溃。"""
    exporter = TXTExporter()
    ch = Chapter(chapter_num=1, title="test", content="\n\n\n")
    output = exporter.export_chapter(ch)
    text = output.decode("utf-8")
    assert "第1章 test" in text


def test_epub_with_unicode_content() -> None:
    """V0.30.6 B6：EPUB 正确处理中文 Unicode。"""
    exporter = EPUBExporter()
    chapters = [
        Chapter(chapter_num=1, title="中文标题：测试", content="这是中文内容，包含标点：，。！？")
    ]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xhtml = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
        assert "中文标题" in xhtml
        assert "中文内容" in xhtml


def test_epub_with_very_long_chapter() -> None:
    """V0.30.6 B6：超长章节（10K+ 字符）正确导出。"""
    exporter = EPUBExporter()
    long_content = "这是测试段落。" * 1000  # 10K+ 字符
    chapters = [Chapter(chapter_num=1, title="长章", content=long_content)]
    data = exporter.export_chapters(chapters)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xhtml = zf.read("OEBPS/chapter_001.xhtml").decode("utf-8")
        assert xhtml.count("测试段落") == 1000


# === Test 8：Web 端点 ===


def test_api_chapter_export_endpoint_md(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/chapter/{n}/export?format=md 返回 markdown 文件。"""
    # 设置测试项目
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    prose_dir = project_root / "正文"
    prose_dir.mkdir()
    # 关键：用 project.chapter_prose() 的命名（零填充 + 无空格）
    (prose_dir / "第001章.md").write_text("# 第1章 测试\n\n这是测试内容。", encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/chapter/1/export?format=md&project_root={project_root}")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "# 第1章 测试" in response.text


def test_api_chapter_export_endpoint_txt(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/chapter/{n}/export?format=txt 返回纯文本。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    prose_dir = project_root / "正文"
    prose_dir.mkdir()
    (prose_dir / "第001章.md").write_text("# 第1章 测试\n\n**这是粗体**内容。", encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/chapter/1/export?format=txt&project_root={project_root}")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "**粗体**" not in response.text
        assert "粗体" in response.text


def test_api_chapter_export_endpoint_epub(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/chapter/{n}/export?format=epub 返回 epub 文件。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    prose_dir = project_root / "正文"
    prose_dir.mkdir()
    (prose_dir / "第001章.md").write_text("# 第1章 测试\n\n这是内容。", encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/chapter/1/export?format=epub&project_root={project_root}")
        assert response.status_code == 200
        assert "application/epub+zip" in response.headers["content-type"]
        # 验证是合法 zip
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert "mimetype" in zf.namelist()


def test_api_chapter_export_invalid_format(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/chapter/{n}/export?format=invalid 返回 400。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    prose_dir = project_root / "正文"
    prose_dir.mkdir()
    (prose_dir / "第001章.md").write_text("# 第1章 测试\n\n内容", encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/chapter/1/export?format=pdf&project_root={project_root}")
        assert response.status_code == 400


def test_api_chapter_export_not_found(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/chapter/999/export 章节不存在返回 404。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    (project_root / "正文").mkdir()

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/chapter/999/export?format=md&project_root={project_root}")
        assert response.status_code == 404


def test_api_export_project_epub(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/export?format=epub 导出整本书。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    prose_dir = project_root / "正文"
    prose_dir.mkdir()
    # 用 project.chapter_prose() 的命名
    (prose_dir / "第001章.md").write_text("# 第1章 第一章\n\nc1", encoding="utf-8")
    (prose_dir / "第002章.md").write_text("# 第2章 第二章\n\nc2", encoding="utf-8")

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            f"/api/export?format=epub&project_root={project_root}&title=MyBook&author=Me"
        )
        assert response.status_code == 200
        assert "application/epub+zip" in response.headers["content-type"]
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            assert "OEBPS/chapter_001.xhtml" in zf.namelist()
            assert "OEBPS/chapter_002.xhtml" in zf.namelist()
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
            assert "MyBook" in opf


def test_api_export_project_no_chapters(tmp_path: Path) -> None:
    """V0.30.6 B6：/api/export 项目无章节返回 404。"""
    project_root = tmp_path
    (project_root / "_tracking-state.json").write_text("{}", encoding="utf-8")
    (project_root / "正文").mkdir()

    app = create_app()
    with TestClient(app) as client:
        response = client.get(f"/api/export?format=epub&project_root={project_root}&title=Empty")
        assert response.status_code == 404
