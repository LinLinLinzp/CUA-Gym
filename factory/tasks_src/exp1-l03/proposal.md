# 任务说明：升级复盘准备（escalation-review-prep）

- **任务标识与版本**：`cua-hard/escalation-review-prep`，v0.1.0（exp1 杠杆批次，主杠杆 L03 隐藏数据）。
- **场景**：产业运营 / SaaS 客服升级复盘。外勤服务管理 SaaS 公司 Acme Fieldwork 的客服负责人 Dana Whitfield，为周五（11/20）与研发的升级复盘准备三个 Jira bug 的真实客户影响面。
- **涉及站点**：Zendesk（工单、标签；主站点）、Slack（#support-escalations 中 Tomás 的请求及线程修订）、Jira（FLD 项目 bug 评论与优先级），外加本地账单导出 CSV 与本地交付文件。三站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：三站初始数据（root-only 种子）；`/workspace/input/billing_accounts.csv`（24 个账户，列 account_id,account_name,billing_domain,plan,arr_usd,status）。
- **输出**：Zendesk 工单标签（fld-412 / fld-398 / fld-447）、Jira 三条评论与两处优先级变更、Slack 线程回复；`/workspace/output/escalation_review.csv`（17 行）。

## 主杠杆：L03 隐藏数据

- Zendesk 共 143 张工单（109 张噪声，分布在 Tier 1 / Tier 2 / Billing），29 张在 Engineering Escalations 分组，其中 17 张为目标。
- 默认视图为“Your unsolved tickets”（只显示分配给 Dana 且未解决的），首屏仅能看到 2 张目标（3220、3230）。
- 8/17（47%）目标为 solved 或 hold：solved 只出现在“Recently solved tickets”（81 行，按更新时间倒序，3166、3141 排在第 31、45 行），hold 分配给 Wen，只在“All unsolved”中；另有 new 且未分配的 3241 只在 Unassigned/New 视图。
- 视图不能按分组筛选；判断是否升级、升级到哪个 bug 只能打开工单展开“Show more”看“Jira issue”自定义字段；搜索不覆盖自定义字段，且各人的升级备注措辞不同（“Escalating to Engineering”“Sending this over to the platform team”“Routing to eng”等），任何单一搜索或视图都不能恰好列出目标。
- Jira bug 描述只链接了最初的一张工单（412→#3141、398→#3166、447→#3210）。
- 只处理首屏/未解决可见部分、其余全部正确的 visible_only 夹具约 0.33，主杠杆决定了大部分分数。

## 主要约束（≥4 类）

1. **对象筛选**：Engineering Escalations 分组 + Jira issue 字段 ∈ {FLD-412, FLD-398, FLD-447}，任意状态。
2. **时间窗口**：opened since September 1（PT）。3140 创建于 8/31 23:40 PT（UTC 已是 9/1），不计入；3125 为 8 月的 FLD-412。
3. **跨站字段匹配**：按请求人邮箱域名对 billing_domain 取账户；Zendesk 组织“Brightline”对应 Brightline Electric（ACC-1004），不是 Brightline Solar（ACC-1016）；Summit Roofing 的请求人无组织，且账单中另有已流失的 Summit Roofing & Gutters。
4. **金额与去重**：同一账户多张工单只计一次 ARR（Copperline、Redwood、Keystone）；≥150,000 才升 Highest，FLD-398 为 144,500 应保持 High。
5. **版本冲突**：Tomás 原消息列的是 FLD-431，线程中 Wen 说明已在 4.18 修复、4.18 之后的问题为 FLD-447，Tomás 改为做 FLD-447、431 的工单不动。
6. **更正信息 / 第二来源**：3200 的 Jira 字段仍为 FLD-412，但 Wen 的内部备注和 FLD-398 上的 Jira 评论说明它属于 FLD-398。
7. **重复与已处理**：3168 已合并进 3166（closed），不另计；Diego 已给 3220、3222 打过 fld-412。
8. **保护非目标**：FLD-431/405/422/388 的升级工单、标题相似但未升级的 Tier 1 工单（3144、3213、3226、3234）不得打标签；工单其他字段不改；FLD-431 不评论、不改优先级。

## 期望结果

| Bug | 工单 | 账户数 | ARR | 优先级 |
|---|---|---|---|---|
| FLD-412 | 3141、3157、3183、3220、3222、3233 | 5 | 287,000 | High → Highest |
| FLD-398 | 3166、3177、3186、3200、3236 | 5 | 144,500 | High（不变） |
| FLD-447 | 3204、3208、3210、3218、3230、3241 | 5 | 158,400 | Medium → Highest |

## 浏览器的必要性

工单状态、分组与折叠的自定义字段只能在 Zendesk 页面中逐张查看；打标签、Jira 评论与优先级、Slack 线程回复都只能通过页面完成。账单导出只在本地 CSV 中，ARR 汇总与交付 CSV 依赖 CLI，二者形成真实数据依赖。

## 环境复现

- 与参考题相同的单容器多站运行时：sitehost + 浏览器守护进程，启动时三站各开一个标签页。
- 时钟固定为 2026-11-18 09:20（America/Los_Angeles）并实时前进；浏览器时区为 America/Los_Angeles，工单创建时间按本地时区显示。
- 每个 trial 为新容器，从种子重新初始化。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，无法直接读状态或种子。
- sitehost 只接受带随机密钥头的请求；参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：13 个程序化检查点、加权部分分，标签/评论/CSV 按目标逐个计分；“不得做”类检查（Z5、Z6、J5）乘以覆盖率，空操作得 0。不调用 gate/cap。

夹具预期：golden=1.0、nop=0.0、naive≈0.09、visible_only≈0.33、slip_superseded≈0.61、slip_retriage≈0.74、slip_hold≈0.62、slip_brightline≈0.92、slip_window≈0.78。

## 自测与证据

- 已完成：world.py 确定性生成（两次输出逐字节一致）；本地参考打分模拟验证夹具区间；ui_probe 实测 Zendesk 加标签、Jira 评论与改优先级、Slack 线程回复均写入服务端状态。
- 待完成：独立 verifier 编写与 selfcheck、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
