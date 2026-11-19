# 任务说明：太浩湖团建报销收尾（tahoe-offsite-closeout）

- **任务标识与版本**：`cua-hard/tahoe-offsite-closeout`，v0.1.0（exp1 杠杆实验批次，slot `exp1-l02`）。
- **场景**：组织办公 / 团建差旅报销审核。Fernbrook Labs 的运营兼财务 Nadia Brooks 受财务总监 Owen 委托，审批上周太浩湖团建的报销报告。
- **主杠杆**：L02 非文本证据。决定性的金额、日期、卡号、确认码只存在于回执图片（Expensify 费用回执、Gmail 附件、Airbnb 房东发来的照片）中，站点文本中没有副本；多份报告的手填金额/日期与回执图片不一致。
- **涉及站点**：Expensify（主站：审批、改金额、关闭可报销、上传回执、驳回）、Gmail（Owen 的规则与更正、员工补交的回执、回复总额）、Airbnb（房东对话：现金收据照片、维修报价图、待回复的追问）。三站均为 CUA-Gym-Hub mock，离线提供。
- **输入**：三站初始数据与 `seed/files/<site>/` 下的回执图片（通过站点文件字段引用，打开即下载到 `/workspace/downloads`）。
- **输出**：Expensify 费用与报告状态、Airbnb 新消息、Gmail 回复等服务端持久化状态；`/workspace/output/offsite_closeout.csv`。

## 故事与正确处理

7 份团建报告提交给 Nadia 审批（另有 Tariq 的非团建午餐报告同样待她审批，作为非目标）：

| 报告 | 员工 | 处理 | 图片中的决定性事实 |
|---|---|---|---|
| 78410231 | Daniela | 批准，可报销 229.00 | 房东维修费手填 180，回执是 Venmo 截图 $165；Safeway 回执卡号 AMEX 1009 → 关闭可报销 |
| 78410244 | Kofi | 批准，430.35 | 晚餐手填整单 396.40，小票分单显示他的 VISA 7731 只付 $160；Uber 缺回执，邮件里两张截图只有 IMG_4471 是对的 |
| 78410257 | Leo | 批准，568.78 | 报告上的 Hertz 回执是估价 $342.18，邮件附件里的最终发票为 $324.18 |
| 78410263 | Ingrid | 批准，127.55 | 皮划艇租赁回执 AMEX 1009 → 不可报销；Fire Sign Cafe 是个人 AMEX 3005 → 保持可报销 |
| 78410278 | Tariq | 批准，367.90 | 付给房东的现金手填 120、无回执；Airbnb 对话里房东的收据照片为 $60+$35=$95 |
| 78410282 | Mei | 驳回 | Sunnyside 晚餐手填 11/5，回执日期 10/23/2026（不在团建期） |
| 78410296 | Priya | 驳回 | 返程机票回执与她 10 月已报销报告中的是同一张往返电子客票（HQ4T7N） |

合计可报销 1723.58，回复到 Owen 的邮件线程；在 Airbnb 告诉房东 Daniela 已于 11/7 通过 Venmo 支付 $165。

## 主要约束（≥4 类）

1. **对象筛选**：只处理团建报告；Tariq 的 Halvorsen Freight 午餐报告同样待审批但不在范围内，Grace 的里程报告已批准，Priya 的旧报告已报销。
2. **跨站字段对应**：员工邮件附件、Airbnb 房东照片要对到 Expensify 的具体费用；分单小票上的持卡人与卡号要对到报销人。
3. **金额计算**：以回执为准改金额；分摊账单只认本人卡部分；公司卡费用保留但不可报销；汇总只加可报销金额（报告 total 含公司卡费用）。
4. **时间窗口**：初始规则只认 11/4–11/6，同线程更正纳入 11/3、11/7 旅行日；Mei 的回执日期落在窗口外。
5. **重复处理**：Priya 的返程机票已在 10 月报告中报销。
6. **权限与状态**：只能批准状态为 submitted 且提交给 Nadia 的报告；驳回不得删除费用。
7. **交付格式**：CSV 固定列与取值、Gmail 线程回复、Airbnb 消息。
8. **保护非目标**：非团建报告、已正确的费用（如 Leo 的 186.40 分单、个人卡费用）不得改动。

## 陷阱（≥3）

- **被取代的信息**：Owen 的第一封邮件只认 11/4–11/6（11/13 更正）；Leo 报告上的 Hertz 估价被邮件中的最终发票取代。
- **近似实体**：个人 AMEX 3005 与公司 AMEX 1009；Kofi 的两张 Uber 截图；房东维修报价 $180 与实际 Venmo 支付 $165；“Halvorsen Freight” 报告与员工 Ingrid Halvorsen。
- **仅在第二来源中的事实**：Tariq 的现金收据只在 Airbnb；Kofi 的 Uber 回执与 Leo 的最终发票只在 Gmail 附件。
- **看似合理的非目标**：Mei 手填日期在窗口内；Priya 手填金额是半程票价，看起来不像重复。
- **已处理项**：Grace 报告已批准、Priya 旧报告已报销。

## 浏览器的必要性

审批、改金额、切换可报销、上传回执、驳回只能在 Expensify 页面完成；Airbnb 消息和 Gmail 回复也只能通过页面发出。Expensify 报告页只显示 150×120 的回执缩略图，Gmail 附件同样只有缩略图，因此需要点开下载到 `/workspace/downloads` 后用 CLI 查看图片原文（Airbnb 照片可在页面弹窗中放大），再把 Kofi 的回执从下载目录上传回 Expensify。CSV 由 CLI 写出，形成真实的数据依赖。

## 环境复现

- 与工厂统一运行时相同：sitehost + 浏览器守护进程，启动时三站各开一个标签页；每个 trial 新容器，从种子重新初始化。
- 时钟：2026-11-16 09:30 UTC（周一）。时区取 UTC，避免 Expensify 用 `new Date('YYYY-MM-DD')` 显示日期时的跨日偏移。
- 种子中的回执 URL 形如 `/files/__SID__/<name>`，入口脚本替换 SID 并把 `seed/files/<site>/` 拷入文件目录。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，看不到状态文件与种子图片原件，只能通过站点下载。
- sitehost 只接受带随机密钥头的请求；参考解通过 oracle 令牌写入 golden 状态。

## 评分方式

见 `rubric.json`：13 个程序化检查点，加权部分分，满分 100。除 X8（批准）与 X10（保护非目标）外，其余检查点（合计 86 权重）的正确答案都只能从图片中读出，L02 决定了大部分分数。“不得改动”类检查以至少改对一处金额为前提，空操作得 0。

预期夹具得分：golden=1.0、nop=0.0、naive≈0.08、slip_hertz≈0.84、slip_amex3005≈0.87、slip_host_cash≈0.84、slip_duplicate≈0.84。

## 自测与证据

- 已完成：`world.py` 生成种子/图片/golden/变体；种子文本中检索不到任何决定性数字（165、160.00、324.18、95、3005、7731、10/23、HQ4T7N 及对应分值），证据只在图片里。
- `ui_probe.py` 浏览器实测（均已在服务端状态中确认，记录形状与 golden 一致，仅时间戳与 SID 不同）：
  - Expensify：费用弹窗改金额（exp_1012 → 16500，报告 total 重算）、关闭 Reimbursable（exp_1013）、上传回执（exp_1022 → `/files/<sid>/<8hex>_IMG_4471.png`，hasReceipt=true）、批准（rpt_101 approved + “Report approved” 评论）、填理由驳回（rpt_106 open/isRetracted + “Report rejected: …” 评论，费用保留）；“View Receipt” 下载到 `/workspace/downloads`。
  - Gmail：附件卡片点击下载到 `/workspace/downloads/IMG_4471.png`；在 t_owen 线程内回复，生成 folder=sent、to=owen@fernbrook.io、subject “Re: Tahoe offsite close-out” 的邮件。
  - Airbnb：conv_201 中房东收据与维修报价照片在对话内清晰可读；发送消息生成 senderId=user_001 的新消息，unreadCount 归零。
- 运行时修复（共享）：`factory/runtime/browser/browserd.py` 中 target=_blank 指向文件的链接会留下空白弹窗并使截图超时，现于下载完成后关闭由源页打开的空白弹窗并切回源页。
- 待完成：verifier 编写后的 fixture 自测、本地 oracle/nop 运行、平台 Qwen×5 / Opus×2 评测。
