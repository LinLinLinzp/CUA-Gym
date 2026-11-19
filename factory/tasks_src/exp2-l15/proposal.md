# 任务草案：发布周状态核查（exp2-l15，暂定 `cua-hard/launch-week-status-audit`）

> **状态：阻塞。** YouTube mock 没有视频可见性 / 定时发布 / 首映 / 草稿的概念，也没有 Studio 内容页（`TODO.md` 将 Studio 列为 out of scope；`visibility` 只在上传时写入，任何页面都不读取）。主杠杆 L15 必须靠 YouTube 上的“真实状态”来判定，无法用现有 UI 诚实实现。所需增量见 `gaps.json`。补齐后按本草案编写 world.py / instruction.md / rubric.json / spec.json，并用 ui_probe 走一遍每类写操作。

- **场景**：文化内容 / 频道运营。独立纪录片频道 *Tidewater Stories*（YouTube）做 “Harbor Lights” 系列发布周，频道经理 Priya 外出前把收尾工作交给助理。
- **站点**：YouTube（主，真实状态的唯一来源 + 一处可见性修改 + 发布周播放列表）、Notion（Launch Week 追踪数据库）、X（推广帖）、Slack（#launch 团队状态、置顶发布计划及其线程修订）。tool_type=2：本地 `/workspace/input/promo_copy.csv`（每集推广文案与短链，含一行已作废的旧文案）→ 输出 `/workspace/output/launch_audit.csv`。
- **时钟**：2026-11-19 10:00 America/Los_Angeles（周四）。

## 主杠杆 L15（核心检查点，约占 60% 权重）

种子中 8 集“看起来都发了”（Notion 状态 = Published、Slack 有人说 “ep X is up”、YouTube 通知里有 “uploaded”）：

| 集 | YouTube 真实状态 | 诱导信号 | 正确处理 |
|---|---|---|---|
| E1 | Public（11/16 发布） | — | Notion=Live；发 X；进播放列表 |
| E2 | Public（11/17） | X 上已有一条推广帖（已处理） | Notion=Live；**不重复发帖** |
| E3 | Scheduled 11/21 09:00 | 缩略图出现在自己的频道 Studio 列表、Slack 说 “E3 done” | Notion=Scheduled + 日期；不发帖 |
| E4 | Unlisted | Notion 链接可直接打开播放 | Slack 线程修订：E4 本应上线时公开 → 改为 Public 后 Live、发帖 |
| E5 | Upcoming Premiere 11/19 18:00 | 观看页存在、首映等待室 | Notion=Premiere；不发“已上线”帖 |
| E6 | Private | 团队审片用，Notion 写 Published | Notion=Private；不发帖 |
| E7 | Draft（详情未完成） | 上传通知 “uploaded” | Notion=Draft；不发帖 |
| E8 | Public，但标题与 E1 近似（预告片 “Harbor Lights — Trailer”） | 易与正片混淆 | 不是追踪对象，不改 |

另有 E9：置顶计划中写“E9 定时 11/18 20:00”，按时钟已过 → 实际已 Public（反向错觉：Notion 写 Scheduled 其实已上线），应改 Live 并推广。

## 其它约束（≥4 类）

时间窗口（定时/首映时间与“现在”的比较、太平洋时区）；跨站匹配（Notion 行 ↔ YouTube 视频 ID ↔ CSV 文案）；重复（E2 已推广）；版本修订（Slack 置顶计划的线程回复改了 E4 的可见性与推广文案、CSV 中作废旧文案行）；保护非目标（E3/E5/E6/E7 不得被改为公开，预告片与其它频道视频不动）；交付格式（CSV 列 episode,video_id,true_status,promoted）。

## 预期检查点（约 16 个）

核心（core）：Notion 各行状态 E3/E4/E5/E6/E7/E9 正确；X 只推广 E1/E4/E9 且使用修订后文案与正确短链；YouTube E4 visibility=public 且 E3 publishAt 未变、E5/E6/E7 未被公开。
非核心：E2 无重复帖；Slack #launch 状态消息列出真实上线集数与待上线时间；播放列表含且仅含已上线正片；launch_audit.csv 逐行正确。

## 变体预期

golden 1.0；nop 0.0；naive（信 Notion/Slack 表面状态、全发帖）≤0.35；slip_premiere、slip_unlisted_fix、slip_dup_tweet 各 0.55–0.95。
