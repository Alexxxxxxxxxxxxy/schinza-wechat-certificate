# CSV Digest + Video Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill the CSV 摘要 column (list digest → og:description → first 80 chars of body) and split 视频 into 视频路径 / 视频链接; batch CSV stays one file.

**Architecture:** Add `resolve_csv_digest` and split video helpers in `app/article_reader.py`. Parse HTML writes `og_description`. `batch_export_articles` copies `digest`/`author` from the history row before `article_to_csv_row`.

**Tech Stack:** Python 3.11+, stdlib `unittest` (no pytest).

**Spec:** `docs/superpowers/specs/2026-08-21-csv-digest-and-video-columns-design.md`

## Global Constraints

- Batch CSV remains one file, one row per article.
- Digest order: history `digest` → page `og:description` → `body_text` first 80 chars.
- Columns: `标题, 链接, 发布时间, 作者, 摘要, 正文, 视频路径, 视频链接, 阅读量, 在看数, 评论数`
- Downloaded items only in 视频路径; leftover URLs only in 视频链接; join with ` | `.
- Do not change Markdown / Word / TXT / JSON / list export.
- Do not change video download logic except reading `local_path` already set.
- Tests: `python -m unittest tests.test_csv_export -v`

## File map

| File | Role |
|---|---|
| `app/article_reader.py` | Helpers, parse, CSV row, batch merge |
| `tests/test_csv_export.py` | Create — unittest |

`tests/` may be gitignored on some machines; `git add -f` if needed.

---

### Task 1: Digest resolver + CSV columns

**Files:**
- Modify: `app/article_reader.py`
- Test: `tests/test_csv_export.py`

**Interfaces:**
- Consumes: `article_to_csv_row`, `CSV_COLUMNS`, `parse_wechat_article_html`
- Produces:
  - `DIGEST_FALLBACK_CHARS = 80`
  - `resolve_csv_digest(*, history_digest: str, og_description: str, body_text: str) -> str`
  - `format_csv_video_columns(videos: list) -> tuple[str, str]`  # (paths, urls)
  - `CSV_COLUMNS` as specified
  - `parse_wechat_article_html` sets `og_description` from `meta[property=og:description]`
  - `article_to_csv_row` uses `resolve_csv_digest` with `art["digest"]`, `art["og_description"]`, `art["body_text"]`

- [ ] **Step 1: Write failing tests** in `tests/test_csv_export.py`:

```python
import unittest
from app.article_reader import (
    CSV_COLUMNS,
    article_to_csv_row,
    format_csv_video_columns,
    parse_wechat_article_html,
    resolve_csv_digest,
)


class ResolveDigestTests(unittest.TestCase):
    def test_prefers_history_digest(self):
        self.assertEqual(
            resolve_csv_digest(
                history_digest="列表摘要",
                og_description="页面描述",
                body_text="正文" * 40,
            ),
            "列表摘要",
        )

    def test_falls_back_to_og(self):
        self.assertEqual(
            resolve_csv_digest(
                history_digest="  ",
                og_description="页面描述",
                body_text="正文很多字",
            ),
            "页面描述",
        )

    def test_falls_back_to_body_80(self):
        body = "甲" * 100
        got = resolve_csv_digest(
            history_digest="", og_description="", body_text=body
        )
        self.assertEqual(got, "甲" * 80)


class CsvRowTests(unittest.TestCase):
    def test_columns_and_video_split(self):
        self.assertEqual(
            CSV_COLUMNS,
            (
                "标题", "链接", "发布时间", "作者", "摘要", "正文",
                "视频路径", "视频链接", "阅读量", "在看数", "评论数",
            ),
        )
        paths, urls = format_csv_video_columns(
            [
                {"local_path": r"D:\v\a.mp4", "url": "https://cdn/a.mp4"},
                {"url": "https://v.qq.com/x/page/x.html"},
            ]
        )
        self.assertEqual(paths, r"D:\v\a.mp4")
        self.assertEqual(urls, "https://v.qq.com/x/page/x.html")
        row = article_to_csv_row(
            {
                "title": "t",
                "digest": "d",
                "og_description": "og",
                "body_text": "正文",
                "videos": [
                    {"local_path": "C:/a.mp4", "url": "https://x/a.mp4"},
                    {"url": "https://v.qq.com/x"},
                ],
                "stats": {"read_num": 1, "like_num": 2, "comment_count": 3},
            }
        )
        self.assertEqual(row["摘要"], "d")
        self.assertEqual(row["视频路径"], "C:/a.mp4")
        self.assertEqual(row["视频链接"], "https://v.qq.com/x")
        self.assertNotIn("视频", row)

    def test_parse_sets_og_description(self):
        html = (
            '<html><meta property="og:description" content="OG摘要">'
            '<div id="js_content"><p>正文段落足够长用来当正文</p></div></html>'
        )
        parsed = parse_wechat_article_html(html)
        self.assertEqual(parsed.get("og_description"), "OG摘要")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2:** `python -m unittest tests.test_csv_export -v` — expect FAIL (missing helpers / old columns).

- [ ] **Step 3: Implement**

```python
DIGEST_FALLBACK_CHARS = 80


def resolve_csv_digest(
    *,
    history_digest: str = "",
    og_description: str = "",
    body_text: str = "",
) -> str:
    hist = (history_digest or "").strip()
    if hist:
        return hist
    og = (og_description or "").strip()
    if og:
        return og
    compact = re.sub(r"\s+", "", body_text or "")
    return compact[:DIGEST_FALLBACK_CHARS]


def format_csv_video_columns(videos: list) -> tuple[str, str]:
    paths: list[str] = []
    urls: list[str] = []
    for v in videos or []:
        if not isinstance(v, dict):
            continue
        lp = str(v.get("local_path") or "").strip()
        url = str(v.get("url") or "").strip()
        if lp:
            paths.append(lp)
        elif url:
            urls.append(url)
    return " | ".join(paths), " | ".join(urls)
```

In `parse_wechat_article_html`, always read og:description (not only when body is short):

```python
    og_description = ""
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        og_description = str(og_desc["content"]).strip()
    # keep existing short-body fallback using og_description
```

Add `"og_description": og_description` to the return dict.

Replace `CSV_COLUMNS` and `article_to_csv_row`:

```python
CSV_COLUMNS = (
    "标题", "链接", "发布时间", "作者", "摘要", "正文",
    "视频路径", "视频链接", "阅读量", "在看数", "评论数",
)

def article_to_csv_row(art: dict[str, Any]) -> dict[str, str]:
    paths, urls = format_csv_video_columns(list(art.get("videos") or []))
    return {
        "标题": str(art.get("title") or "(无标题)"),
        "链接": str(art.get("link") or ""),
        "发布时间": str(art.get("publish_at") or ""),
        "作者": str(art.get("author") or ""),
        "摘要": resolve_csv_digest(
            history_digest=str(art.get("digest") or ""),
            og_description=str(art.get("og_description") or ""),
            body_text=str(art.get("body_text") or ""),
        ),
        "正文": str(art.get("body_text") or "").strip(),
        "视频路径": paths,
        "视频链接": urls,
        "阅读量": str((art.get("stats") or {}).get("read_num") or ""),
        "在看数": str((art.get("stats") or {}).get("like_num") or ""),
        "评论数": str((art.get("stats") or {}).get("comment_count") or ""),
    }
```

- [ ] **Step 4:** `python -m unittest tests.test_csv_export -v` — PASS.

- [ ] **Step 5: Commit** `fix: CSV 摘要回填并拆分视频路径与链接列`

---

### Task 2: Batch export copies digest/author from history row

**Files:**
- Modify: `app/article_reader.py` (`batch_export_articles`)
- Test: `tests/test_csv_export.py` (add class)

**Interfaces:**
- Consumes: Task 1 helpers
- Produces: after fetch, if `not str(parsed.get("digest") or "").strip()` set from `row["digest"]`; if `not parsed.get("author")` set from `row["author"]`. Still one CSV file.

- [ ] **Step 1: Add test** that mocks `fetch_article` returning no digest, history row has digest/author, `batch_export_articles(..., fmt="csv")` writes one file whose 摘要/作者 match the row:

```python
import tempfile
from pathlib import Path
from app.article_reader import batch_export_articles


class BatchCsvMergeTests(unittest.TestCase):
    def test_one_file_uses_history_digest(self):
        def fake_fetch(url, cred=None):
            return {
                "title": "t",
                "link": url,
                "body_text": "x" * 10,
                "og_description": "",
                "videos": [],
            }

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            csv_path = out / "all.csv"
            result = batch_export_articles(
                [
                    {
                        "title": "t",
                        "link": "https://mp.weixin.qq.com/s/a",
                        "digest": "历史摘要",
                        "author": "张三",
                    }
                ],
                out_dir=out,
                fmt="csv",
                fetch_article=fake_fetch,
                csv_path=csv_path,
                download_videos=False,
                sleep_s=0,
            )
            self.assertTrue(csv_path.is_file())
            self.assertEqual(len(result.get("written") or []), 1)
            text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("历史摘要", text)
            self.assertIn("张三", text)
            self.assertIn("视频路径", text)
            self.assertNotIn(",视频,", text.replace("视频路径", "").replace("视频链接", ""))
```

(If the last assert is brittle, just assert header contains `视频路径` and `视频链接`.)

- [ ] **Step 2:** Run test — FAIL until merge is added.

- [ ] **Step 3:** In `batch_export_articles`, after title backfill:

```python
            if not str(parsed.get("digest") or "").strip() and row.get("digest"):
                parsed["digest"] = str(row.get("digest") or "").strip()
            if not str(parsed.get("author") or "").strip() and row.get("author"):
                parsed["author"] = str(row.get("author") or "").strip()
```

- [ ] **Step 4:** Tests PASS.

- [ ] **Step 5: Commit** `fix: 批量 CSV 回填历史摘要与作者`

---

### Task 3: Spec checklist

- [ ] Confirm batch still writes one CSV (`csv_path` / `导出文章.csv`).
- [ ] Run `python -m unittest tests.test_csv_export -v`
- [ ] No commit unless a gap was found.

## Self-review

Spec items map to Task 1 (digest order, columns, og) and Task 2 (history merge, one file). No placeholders.
