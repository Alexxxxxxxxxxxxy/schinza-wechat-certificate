# 多账号排队拉取 + getmsg 风控缓解

日期：2026-08-18  
状态：待用户确认后写实现计划  
范围：历史列表（`getmsg`）单号变稳 + 多个有效凭证公众号排队批量拉取

## 背景

Schinza 用短时会话凭证请求 `https://mp.weixin.qq.com/mp/profile_ext?action=getmsg` 翻页拉历史。当前只支持下拉选一个号。翻页间隔约 1.5 秒，凭证里的 `devicetype` / `clientversion` 为空，UA 写死。微信很快返回 `unknownerror` / 操作频繁，整次拉取中断。

本次不做真并行。真并行会提高同一出口 IP 被判异常的概率。

## 目标

1. 单号 `getmsg` 更不容易被风控打断；被打断时保留已拉到的文章。
2. 一次勾选多个「凭证仍有效」的公众号，按队列逐个拉同一时间范围。
3. 某个号被风控：该号立刻停，已有文章保留，继续下一个号。
4. 结果按公众号分组展示。

非目标：真并行、跨号合并导出、正文/互动导出的风控改造、完整 Cookie 头回放、官方素材 API。

## 决策摘要

| 项 | 选择 |
|---|---|
| 并发 | 逐个排队，号与号之间歇一会儿 |
| 单号风控 | 立刻停该号，保留部分结果，继续下一个 |
| 勾选 | 默认全选有效号，可取消部分 |
| 结果 | 按公众号分组；点一组看该号文章 |
| 指纹 | 抓包补 UA / 设备字段 / 少量关键 Cookie；旧凭证走默认 UA |

## 架构

三块，现有单号按钮继续可用。

```
MITM 抓包 ──写入── credentials(+指纹)
                      │
                      ▼
              fetch_history_days（更慢、带指纹）
                      ▲
                      │
              fetch_history_batch（排队编排）
                      │
                      ▼
              历史文章页（勾选 + 分组结果）
```

1. **抓包补全指纹** — 完整 `__biz / uin / key` 写入时，带上同一次请求的客户端指纹。
2. **单号拉取变稳** — `fetch_history_days` 使用指纹 + 更慢翻页；风控停号不重试。
3. **批量编排** — 新函数按勾选顺序一个一个调用单号拉取；号间间隔；取消停整批。

界面仍在「历史文章」页，不新开标签。

## 凭证与抓包

在已有 `credentials` 上增加可选字段（缺省兼容旧数据）：

| 字段 | 来源 | 用途 |
|---|---|---|
| `user_agent` | 请求 `User-Agent` | 拉历史时回放 |
| `devicetype` | URL query | `getmsg` 参数 |
| `clientversion` | URL query | `getmsg` 参数 |
| `wxtoken` | URL query（已有，继续收） | `getmsg` 参数 |
| `slave_sid` | Cookie | 仅当存在时写入并回放 |
| `data_ticket` | Cookie | 仅当存在时写入并回放 |

继续保存：`pass_ticket`、`wxuin`（来自 `uin`）。

不保存、不回放：整份 `Cookie` 头、其它域名 Cookie、请求体。

`app/credentials.py` 的可选键扩展为上述字段。`app/mitm_addon.py` 在 `_save` 前从当前 flow 合并这些值。`AccountStore.apply_credentials` 原样写入，无需改 TTL（仍 30 分钟）。

续约成功后新指纹覆盖旧字段。没有新字段的旧账号仍能拉，UA 退回当前写死的 Windows 微信串。

## 单号节奏与风控

`fetch_history_days` 新默认（单号按钮和批量内每个号共用）：

| 参数 | 现在 | 改为 |
|---|---|---|
| 页间隔 `sleep_s` | 1.5s | 3.4s |
| 抖动 `sleep_jitter` | 0.6 | 0.32（实际约 2.8～4.5s） |
| 冷却周期 `cooldown_every` | 5 页 | 4 页 |
| 周期额外 `cooldown_extra_s` | 4s | 10s（约 8～12s 量级，可略抖） |
| 每页 `count` | 10 | 8 |

识别为风控的错误（沿用并收紧 `errors.wechat_error_hint` / `_rate_limit_hint`）：

- `unknownerror`
- `freq` / 频繁 / 操作频繁
- 文案中的「风控」

行为：

- 立刻结束该号，`ok=False`，`error` 带风控说明，`articles` 为已拉 + sightings 合并结果。
- 增加 `stopped_reason`: `rate_limited` | `expired` | `network` | `cancelled` | `completed`，供 UI 分组标签使用。
- 风控**不重试**（避免越拉越封）。
- 超时 / 连接错误仍按现有次数重试；SSL 错误不重试。
- 拉历史仍 `trust_env=False`，直连微信，不走本机 MITM。

## 批量编排

新增 `app/history_batch.py`（或 `history_client.fetch_history_batch`，优先独立模块以免 `history_client` 再膨胀）：

输入：

- 勾选账号列表（id、name、credentials）
- 与单号相同的时间范围（`days` 或 `start_ts`/`end_ts`）
- `on_progress(account_index, account_total, account_name, page_msg)`
- `should_cancel()`

规则：

1. 只拉勾选且 `store.is_active` 且 `__biz/uin/key` 齐全的号；过期号写入结果组，状态 `expired`，不发请求。
2. 按勾选顺序串行调用 `fetch_history_days`。
3. 号与号之间睡眠 6～10 秒（随机）。上一号 `stopped_reason == rate_limited` 时再加约 15 秒。
4. 取消：当前号通过已有 `should_cancel` 停；后续号标记 `cancelled`，不再请求。
5. 每号结果独立：`articles`、`pages`、`ok`、`error`、`stopped_reason`。

整批返回：

```
{
  "ok": true,          # 编排器正常跑完队列即为 true（含全部跳过/取消）；未预期异常才为 false
  "cancelled": false,
  "groups": [ { account_id, name, articles, pages, status, error, stopped_reason } ],
  "summary": { "completed": n, "rate_limited": n, "expired": n, "failed": n, "cancelled": n, "articles": n }
}
```

`status`：`completed` | `rate_limited` | `expired` | `failed` | `cancelled`。

## 界面（历史文章页）

保留现有「选一个号 + 拉取」。同一页增加：

- 有效凭证勾选列表：进入/刷新时默认全选有效号；「全选有效」「清空」。
- 过期号出现在列表但禁用勾选，旁注「请续约」。
- 「批量拉取」：时间范围与现有下拉共用。
- 进行中状态行：`3/12 「某某公众号」第 2 页…`。按钮改为「取消」，取消后当前号停、后面不开始。
- 结果区上方为分组条：公众号名、篇数、状态文案（完成 / 被风控跳过 / 凭证过期 / 失败 / 已取消）。风控组用警告色（橙），过期用灰色，不弹多对话框。
- 点某一组：下方文章列表只显示该组。导出（复制列表 / 导出列表 / 批量导出正文）只针对当前看到的列表。
- 整批结束状态行汇总：`完成 8 · 风控跳过 3 · 过期 1 · 共 142 篇`。

单号拉取结果展示逻辑保持，仅翻页变慢。

## 错误提示

| 情况 | UI |
|---|---|
| 风控 | 该组橙标「被风控跳过，已保留 N 篇」；整批继续 |
| 凭证过期 / 缺字段 | 该组灰标，提示续约 |
| 网络 / SSL | 该组失败并写原因，继续下一个（不标作风控） |
| 用户取消 | 当前组「已取消」；未开始的组「已取消」 |

## 验收

手动验收，不新加测试框架。

1. 单号拉取可用，间隔明显长于现在。
2. ≥3 个有效号：默认全选 → 批量拉 → 按号分组 → 能点进一组看文章并导出该组。
3. 中途取消：当前号停，后续号未发请求。
4. 撞上风控：该号停、已有文章在组里，下一个号继续。
5. 无指纹旧凭证仍能单号/批量拉（默认 UA）。
6. 抓包续约后，该号 `credentials` 含 `user_agent` 或 `clientversion` 等新字段（有则必须出现）。
7. 批量进行中，历史拉取仍直连，不走系统代理。

## 文件影响（预期）

- `app/mitm_addon.py` — 抓指纹
- `app/credentials.py` — 可选键
- `app/history_client.py` — 默认节奏、指纹请求头、`stopped_reason`
- `app/history_batch.py` — 新建，排队编排
- `app/ui.py` — 勾选、批量按钮、分组结果
- `app/errors.py` — 仅当提示文案需要更清楚时小改

不改同步服务器上传、批量导入抓包流程。
