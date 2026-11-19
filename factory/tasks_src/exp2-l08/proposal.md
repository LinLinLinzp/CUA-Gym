# 任务说明：峰会议程重排（summit-run-of-show）

- **任务标识与版本**：`cua-hard/summit-run-of-show`，v0.1.0（exp2 杠杆批次，主杠杆 L08 高级操作 / 拖放排序）。
- **场景**：组织办公 / 会议议程排期。自由职业活动统筹 Rosa Delgado 为 Northlight Product Summit（2026-12-03/04，伦敦 Brunel Rooms，Thames Hall 与 Mercer Room 两个会场）整理最终 run of show，AV 团队（Sam Okoro）周五直接按 Trello 列表从上到下生成 cue sheet。
- **涉及站点**：Trello（主站点，run-of-show 看板，每个“日期·会场”一个列表）、Yahoo Mail（场馆确认、讲者变更、Marcus 的决定）、Google Calendar（“Northlight Summit — rooms”场馆确认预订，系统记录），外加本地注册导出 CSV 与本地交付文件。
- **输入**：三站初始数据（root-only 种子）；`/workspace/input/registrations_export.csv`（27 行，列 event_code,session_code,session_title,speaker,format,status,interested；含 NLS26 峰会 21 行与 NPD27 合作伙伴日 6 行，按 interested 倒序）。
- **输出**：Trello 看板列表成员与顺序、日历 4 个事件的改动、4 封讲者确认邮件；`/workspace/output/run_of_show.csv`（18 行）。

## 主杠杆：L08 高级操作（拖放排序）

- 看板由 v2 草稿生成，四个日期·会场列表中有 5 张卡片会场错误、3 对顺序颠倒；邮件变更又带来 3 次跨列表移动与 2 次插入到列表中间/顶部的位置要求（Tomás 插到第 2 位、Priya 与 Bartek 置顶、Arjun 插到第 2 位）。
- Trello mock 的卡片 Move 对话框只能追加到目标列表末尾，没有位置选择；列表“Sort by”只能按标题字母或创建时间排序，createdAt 与时段无关、标题也不以时间开头，四个期望顺序都不等于这两种排序结果。正确结果实际只能通过拖放（@hello-pangea/dnd，跨列表 MOVE_CARD 按落点 index 插入）完成；反复移出再移回也能凑出顺序，但需要大量额外往返，同样要求精确规划顺序。
- 评分直接检查四个列表的 cardIds 顺序：成员比例 × 顺序因子（正确成员相对顺序必须与期望一致，否则 0）；四项共 48 分。判断全对但只追加不排序的 append_only 夹具约 0.49，主杠杆决定了大部分分数。

## 主要约束（≥4 类）

1. **跨站字段匹配**：卡片描述里的“Draft v2 slot”过期；每场的会场与时间以日历确认预订为准（Gemma 邮件声明日历为最终版，Marcus 要求看板与日历一致）。
2. **版本冲突 / 更正信息**：Priya 最初提议与 Clara 互换，Marcus 在线程回复中改为与 Tomás 互换（Priya→周五 10:00 Mercer，Tomás→周四 10:00 Thames）。
3. **第二来源 + 对象筛选**：Inés 退出后，Marcus 要求按注册导出中“兴趣人数更多”的候补演讲填补；必须只看 NLS26 行（Arjun 71 > Kirsten 58），NPD27 中 Kirsten 的同名演讲 96 与看板上的“Waitlist #1”都指向错误答案。
4. **时间与容量**：Mercer 周四 09:00 新开放；Bartek 获批改到 09:00–09:45，原 14:00 空出；所有时间为伦敦时间（12 月 GMT）。
5. **例外 / 已处理**：Nadia 与 Olu 互换的请求被 Marcus 拒绝；Ben Carver 11/5 已退出并已移到 Pulled、已回复。
6. **保护非目标**：Production & logistics 列表、Partner Day 看板（含同名近似卡片）、Admin 看板、其余 44 个日历事件不得改动。
7. **交付格式**：CSV 列 day,room,start,end,session,speaker，日期 YYYY-MM-DD，24 小时制 HH:MM。

## 期望结果

| 列表 | 顺序 |
|---|---|
| Thu 3 Dec · Thames Hall | Opening Keynote（Ama）09:00 → Accessible Data Visualisation（Tomás）10:00 → Pricing Experiments（Kowalski）11:15 → Roadmaps Are Promises（Achterberg）14:00 → Fireside（Iyer）15:30 |
| Thu 3 Dec · Mercer Room | Instrumenting Onboarding Funnels（Bartek）09:00 → Feature Flags as a Product Tool（Arjun）10:00 → Research Ops（Okonjo）11:15 → Product Analytics Office Hours（Mei Lin）15:30 |
| Fri 4 Dec · Thames Hall | Day Two Keynote 09:00 → Platform Thinking（Olu）10:00 → From Feature Factory（Clara）11:15 → Designing for Trust（Nadia）14:00 → Closing Panel 15:30 |
| Fri 4 Dec · Mercer Room | Scaling Design Systems（Priya）10:00 → Writing PRDs（Whitfield）11:15 → Migrating a Monolith（Menon）14:00 → Customer Interviews（Demir）15:30 |
| Waitlist | Postmortems Without Blame（Kirsten） |
| Pulled | Growth Loops 101（已有）、Edge Caching Deep Dive |

日历：evt_s02 → 12-04 10:00–10:45 Mercer；evt_s15 → 12-03 10:00–10:45 Thames；evt_s08 → 12-03 09:00–09:45 Mercer；evt_s06 改为 “Feature Flags as a Product Tool”（12-03 10:00 Mercer）。邮件：Priya、Tomás、Arjun、Bartek 各一封，含日期、开始时间与会场。

## 网站必要性

- Trello：唯一需要拖放排序的交付物，AV 依据它生成 cue sheet。
- Google Calendar：确认预订（系统记录）只在日历中，决定草稿中哪些卡片会场/顺序错误；同时需写回 4 个事件。
- Yahoo Mail：全部变更与 Marcus 的决定（含更正和拒绝）只在邮件线程里；须发 4 封确认邮件。
- CLI：注册导出只在本地 CSV 中，决定替补人选；最终 CSV 由 CLI 写出。

## 环境复现

- 单容器多站运行时：sitehost + 浏览器守护进程，启动时三站各开一个标签页。
- 时钟固定为 2026-11-18 09:15（Europe/London）并实时前进；浏览器时区 Europe/London（12 月与 UTC 一致，避开日历编辑框的时区换算问题）。
- 每个 trial 为新容器，从种子重新初始化。Trello 种子复用默认 id（board-1..3、list-1..9、card-1..14、u1..u4）完整覆盖默认数据。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，无法直接读状态或种子。
- sitehost 只接受带随机密钥头的请求；参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：16 个程序化检查点、加权部分分；B1–B4（列表成员×顺序）为 core 说明项，不调用 gate/cap。“不应改动”类（B6、C5）以完成对应工作为前提，空操作为 0。

夹具预期：golden=1.0、nop=0.0、naive≈0.23、append_only≈0.49、slip_swap_partner≈0.74、slip_replacement≈0.86、slip_declined≈0.86、slip_draft≈0.57。

## 自测与证据

- 已完成：world.py 确定性生成（两次输出逐字节一致）；本地参考打分模拟验证夹具区间（golden 1.0、nop 0.0、naive 0.227、append_only 0.490、slip_swap_partner 0.740、slip_replacement 0.858、slip_declined 0.856、slip_draft 0.566）。
- ui_probe 实测（打包草稿，容器内浏览器）：Trello 跨列表拖放（Waitlist → Thu Mercer 第 2 位，cardIds 精确插入并记 “moved this card from Waitlist to Thu 3 Dec · Mercer Room” 活动）与列表内拖放（卡片拖到列表顶部）均写入服务端状态；Google Calendar 编辑弹窗改日期与地点后 evt_s02 变为 2026-12-04T10:00Z–10:45Z、Mercer Room（伦敦=UTC，无偏移）；Yahoo Mail 新建邮件发送后进入 sent 并记 message.send 活动。
- 种子注意事项：Trello mock 会把种子深合并进默认数据且跳过 null，故 card-1…14 的 cover/dueDate/startDate 用空字符串表示“无”，避免默认封面（外链图片）与到期日泄漏；Google Calendar 周视图/议程/弹窗把事件 color 当作内联 CSS，只认十六进制，故事件颜色用 hex，日历颜色保留侧栏使用的 Tailwind 类名（月视图把事件 color 当类名，事件条会无底色，属 mock 既有问题，不影响默认周视图）。
- 待完成：独立 verifier 编写与 selfcheck、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
