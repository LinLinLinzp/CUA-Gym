# 任务说明：末班电车之后（after-the-last-tram）

- **任务标识与版本** `cua-hard/after-the-last-tram`，v0.1.2。
- **场景** 文化内容 / 特刊发布核对。Platform Letter 主编 Mara Ellis 将特刊收尾交给发行制片 Inez Ward。
- **涉及站点** Substack 提供实际文章状态与发布操作，Microsoft Word for the web 提供有签字时刻的审批和禁发时刻，Mattermost 提供交接和原线程中的最终发行回执。
- **输入** 三站种子。审批记录为 Word 文档《After the Last Tram — signed release sheet》，旧制作单仍可查阅。
- **输出** Substack 正确预约的采访和已发布配送的照片文章，以及 Mattermost 原线程中的一条已发回复。

## 主要约束

1. **跨站对应和范围** 审批表的精确标题与副标题对应 Substack 三篇文章。照片版式样张沿用同一特刊标签，须保留其草稿。
2. **时间与更正** 11 月 19 日原预约为 18:30 CET，签字后改为 19:30 CET。浏览器按 UTC 显示，等价预约为11 月 19 日 18:30 UTC。
3. **授权与配送** 插画授权限公开网页。采访保持公开预约且启用届时配送。正式照片文章即时发布、付费订阅者可见，并配送到邮件和应用。
4. **交付与保护** 单条真实回复归入原线程。其内容反映持久化结果，保存和确认界面上的中间状态不足以宣布发布。保留原稿正文、标签、评论设置和其他记录。

## 浏览器的必要性

任务标签为 operation_difficulty=2、tool_type=1、difficulty=2。发布和改期各经编辑页、审核面板和最终提交，线程回复须通过编辑器发送。三站开在独立浏览器标签中，`hide_browser_debug=true`。

## 环境复现

环境使用工厂统一 sitehost 和浏览器，UTC 时间从 2026-11-18 15:00 开始。头像通过 worldkit 生成，文章缩略图使用 Substack 自带的离线城市照片。

## 安全边界

仅使用固定三个模拟站点，状态保存在隔离容器。任务不涉及外部真实订阅者或消息。

## 评分方式

见 rubric.json，11 项共 100 权重。L15「状态错觉」直接决定发布、预约、配送及事实回执分数。单凭最初的“全都上线”或按已选设置推断配送无法通过这些检查。独立 verifier 已通过全部六个夹具检查。

## 自测与证据

已用 `package.py exp3-02 --skip-selfcheck` 构建并用 `ui_probe.py start / act / diff / state / stop` 验证独立容器中的页面操作及服务端状态。

- **Word** 从文档库打开审批表，可在查看模式读取完整签字说明。服务端仅写入 `documentActivity`，对应 `doc-signed` 和 `usr-inez`。
- **Substack 发布与配送** 选择正式照片稿，在发布确认面板选择 Paid subscribers 并勾选邮件及应用配送，提交 Publish now。页面显示 Paid subscribers 和 Post published。服务端新增 `post.published`，原 `post-depot` 变为 `published`，且 `publishedAt=deliveryAt=2026-11-18T15:00:41.637Z`。样张与其他文章逐条保持初态。
- **Substack 改期** 在 Scheduled 打开采访，在确认面板将 UTC 时间从 17:30 改为 18:30 后提交 Schedule。页面保留 Scheduled 并显示 11 月 19 日 6:30 PM，服务端新增 `post.scheduled`，`post-night.scheduledAt=2026-11-19T18:30:00.000Z`，发布和配送时间仍为空。已上线的纯网页文章整条记录未变。
- **Mattermost 线程回复** 在 Editorial Desk 的原交接线程中输入一段话并发送。服务端仅新增一条 `thread.reply`，其 `rootId=post-tram-release`、`channelId=ch-editorial`、作者为 `usr-inez`。可见回复数由 2 增至 3，草稿被消耗，原消息逐条保持初态。探针第一次用直接键入换行，浏览器把各行当作单独发送。重新启动容器后用单段正文复验，得到上述单条回复结果。

本轮修复了 golden 回执的禁发状态表述，明确采访尚未发布，邮件和应用配送待预约执行。原表述使用 “has yet to appear on the web”，未通过 M3 对尚未发布的措辞识别。重跑隔离浏览器，将修订后的单段回执发送到同一线程，并用服务端快照运行独立 verifier，11 项全部通过，得分 1.00。夹具实测为 golden 1.00、nop 0.00、naive 0.08、slip_old_embargo 0.72、slip_web_only_delivery 0.85、slip_saved_without_sending 0.61。已完成正式打包。
