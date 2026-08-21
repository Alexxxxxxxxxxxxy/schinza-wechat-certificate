# 批量 CSV：补摘要 + 视频路径/链接分列

日期：2026-08-21  
状态：待用户确认 spec 后写实现计划  
范围：文章正文导出为 CSV（单篇与批量）

## 背景

批量导出 CSV 时会重新抓文章 HTML。`parse_wechat_article_html` 不写 `digest` / `author`，`batch_export_articles` 只从历史行回填标题和发布时间，不回填摘要。CSV「摘要」因此经常为空。现有「视频」列把本地路径和 URL 混在一格。

批量 CSV 已是多篇文章写入**同一个文件**（另存为选择路径）。本次保持该行为。

## 目标

1. 摘要按优先级填写，尽量不空。
2. 视频拆成「视频路径」「视频链接」两列。
3. 批量仍合并进一个 CSV。

非目标：改 Markdown / Word / TXT / JSON、列表导出、下载逻辑本身。

## 摘要填充顺序

对每一行，`resolve_csv_digest(parsed, history_row)`：

1. 历史列表 `digest`（去空白后非空则用）
2. 解析页的 `og:description`（在 `parse_wechat_article_html` 写入 `digest` 或单独字段）
3. `body_text` 压成单行后取前 80 个字符（不足则全取）

作者：历史行 `author` 非空则写入 parsed（解析结果为空时）。

## CSV 列

```
标题, 链接, 发布时间, 作者, 摘要, 正文, 视频路径, 视频链接, 阅读量, 在看数, 评论数
```

- **视频路径**：`videos[].local_path`，多条 ` | ` 连接；无本地下载则为空。
- **视频链接**：没有 `local_path` 但有 `url` 的项；多条 ` | ` 连接。已成功下载的条目只出现在路径列，不重复写进链接列。

勾选「下载视频」且下载成功时路径才有值。未勾选或失败：路径空，链接仍可有。

## 调用点

- `article_to_csv_row` / `CSV_COLUMNS`（`app/article_reader.py`）
- `parse_wechat_article_html`：写入 `og:description` 作为 digest 候选
- `batch_export_articles`：回填 `digest`、`author` 后再组行
- 单篇 `write_article_export(..., csv)` 走同一 `article_to_csv_row`

## 验收

1. 历史有 digest 的文章，批量 CSV 摘要列等于该 digest。
2. 历史无 digest、页面有 og:description，摘要为描述文案。
3. 两者都无，摘要为正文前约 80 字。
4. 勾选下载且下到 mp4：视频路径为本地绝对路径；视频链接不含该条。
5. 未勾选下载或仅有腾讯视频页：视频路径空，视频链接有 URL。
6. 批量 N 篇只产出 1 个 CSV，N 行数据 + 表头。
