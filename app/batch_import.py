"""Parse batch-import files (CSV/TXT) with 公众号, 文章链接 columns."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

NAME_HEADERS = {
    "公众号",
    "公众号名称",
    "公众号账号",
    "账号",
    "名称",
    "昵称",
    "name",
    "account",
    "account_name",
    "nickname",
}
LINK_HEADERS = {"文章链接", "链接", "文章url", "url", "link", "article_url"}

BATCH_IMPORT_HINT = "CSV / TXT · 两列「公众号,文章链接」· 逗号或 Tab · 首行可为表头"
BATCH_IMPORT_EXAMPLE = "数模加油站,https://mp.weixin.qq.com/s/xxxxxxxx"
BATCH_IMPORT_HELP = (
    "文件格式：CSV 或 TXT（编码 UTF-8 或 GB18030）\n"
    "每行一个公众号，必须两列：公众号名称 + 该号任意一篇文章链接。\n"
    "分隔符用逗号或 Tab。首行如果是表头会自动跳过"
    "（公众号 / 名称 / name + 文章链接 / 链接 / url）。\n"
    "\n"
    "示例：\n"
    "公众号,文章链接\n"
    f"{BATCH_IMPORT_EXAMPLE}"
)


@dataclass(frozen=True)
class BatchRow:
    line: int
    name: str
    link: str


def _is_header(cells: list[str]) -> bool:
    first = (cells[0] if cells else "").strip().lower()
    second = (cells[1] if len(cells) > 1 else "").strip().lower()
    return first in NAME_HEADERS or second in LINK_HEADERS


def parse_batch_import(text: str) -> tuple[list[BatchRow], list[str]]:
    """Parse batch import text.

    Returns (rows, errors). Each line must have 公众号 + 文章链接 (comma or
    tab separated). A header row is detected and skipped automatically.
    Malformed lines are collected into errors with 1-based line numbers;
    valid lines are still returned.
    """
    raw = (text or "").lstrip("\ufeff")
    delim = "\t" if ("\t" in raw and "," not in raw) else ","
    reader = csv.reader(io.StringIO(raw), delimiter=delim)
    rows: list[BatchRow] = []
    errors: list[str] = []
    seen_header = False
    for raw_line, cells in enumerate(reader, start=1):
        if not cells or not any(c.strip() for c in cells):
            continue
        cells = [c.strip() for c in cells]
        if not seen_header:
            seen_header = True
            if _is_header(cells):
                continue
        if len(cells) < 2:
            errors.append(f"第 {raw_line} 行：列数不足，需要「公众号,文章链接」两列")
            continue
        name, link = cells[0], cells[1]
        if not name:
            errors.append(f"第 {raw_line} 行：公众号名称为空")
            continue
        if "mp.weixin.qq.com" not in link:
            errors.append(f"第 {raw_line} 行：文章链接不是微信公众号链接（{link[:40]}）")
            continue
        rows.append(BatchRow(line=raw_line, name=name, link=link))
    return rows, errors
