"""文件解析器：把 .md/.pdf/.docx/.xlsx 统一抽取为纯文本。"""
from pathlib import Path


def parse_md(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_pdf(path: Path) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    try:
        parts = []
        for page in doc:
            parts.append(page.get_text())
        return "\n".join(parts)
    finally:
        doc.close()


def parse_docx(path: Path) -> str:
    from docx import Document
    doc = Document(str(path))
    parts = []
    for p in doc.paragraphs:
        if p.text.strip():
            parts.append(p.text)
    for table in doc.tables:
        parts.append("")  # 空行分隔表格
        for row in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
            parts.append(" | ".join(cells))
    return "\n".join(parts)


def parse_xlsx(path: Path) -> str:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), data_only=True, read_only=True)
    parts = []
    try:
        for ws in wb.worksheets:
            parts.append(f"【工作表：{ws.title}】")
            for row in ws.iter_rows(values_only=True):
                cells = ["" if c is None else str(c).strip() for c in row]
                if any(cells):
                    parts.append(" | ".join(cells))
    finally:
        wb.close()
    return "\n".join(parts)


def parse_file(path: str | Path) -> tuple[str, str]:
    """解析单个文件，返回 (文本内容, 扩展名)。"""
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".md":
        return parse_md(p), "md"
    if ext == ".pdf":
        return parse_pdf(p), "pdf"
    if ext == ".docx":
        return parse_docx(p), "docx"
    if ext == ".xlsx":
        return parse_xlsx(p), "xlsx"
    # 其他文本类直接读
    try:
        return p.read_text(encoding="utf-8", errors="replace"), ext.lstrip(".")
    except Exception:
        return "", ext.lstrip(".")


SUPPORTED_EXTS = {".md", ".pdf", ".docx", ".xlsx", ".txt"}
