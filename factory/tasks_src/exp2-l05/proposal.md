# 任务说明：结算税额取整回滚（checkout-rounding-rollback）

- **任务标识与版本**：`cua-hard/checkout-rounding-rollback`，v0.1.0（exp2 杠杆批次，主杠杆 L05 多跳依赖）。
- **场景**：数字技术 / 线上故障值班溯源与回滚。电商公司 Acme Commerce 的 checkout 值班 SRE Sam Okafor 06:52 被 Sentry 问题 CHECKOUT-API-3QK 呼起，09:00–12:00 被困在 DR 演练中，把事故交给代理处理。
- **涉及站点**：Sentry（主站点：问题、事件、分派与评论）、GitHub（提交、PR、新建回滚 PR 与 reviewer）、Linear（工单状态与评论）、Slack（团队的回滚约定与线程回复），外加本地部署记录 CSV 与本地交付 JSON。四站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：四站初始数据（root-only 种子）；`/workspace/input/deploys.csv`（30 行，列 deployed_at,service,environment,release,git_sha,deployed_by,status，时间为 UTC）。
- **输出**：GitHub checkout-api 新 PR（revert-1287-line-rounding → main，reviewer Priya，不合并）；Linear PAY-431 改回 In Progress 并评论 PR 号；Sentry 3QK 分派给 Priya 并评论工单号与 PR 号；Slack #ledger-rollouts 线程回复 PR 号；`/workspace/output/incident_trace.json`。

## 主杠杆：L05 多跳依赖

链条共 6 跳，每一跳的标识只出现在上一跳的输出里：

1. **Sentry → release**：3QK 的事件 highlights/tags 中 release = checkout-api@4.31.0、environment = production。Sentry 的 Releases 页面不显示 SHA。
2. **release → SHA（本地 CSV）**：deploys.csv 中 checkout-api / production / checkout-api@4.31.0 的行给出 `4be1c07a93d2f1e86b0c5d7a2e49f310c8ab65d1`。近似行有：checkout-api@4.31.0 staging（同 SHA）、4.31.0-rc.1 staging（#1285）、checkout-web@4.31.0 production（web #882）、最新的 checkout-api@4.31.1 staging（`4be1c70e…`，前缀相近，#1291）。
3. **SHA → PR**：GitHub checkout-api 的 Commits 页面只显示 7 位短 SHA，4be1c07 的提交信息为 “Merge pull request #1287 from acme-commerce/tk/pay-412-line-rounding-v2”。仓库里还有 #1279（首次尝试）、#1283（回滚 #1279）、#1291（KRW 跟进）等相似的合并提交。
4. **PR → 工单**：#1287 写的是 “Closes PAY-412”，作者 Tomasz。Linear 中 PAY-412 已 Canceled，Helen 的评论说明它是 PAY-431 的重复、Priya 负责重新上线。
5. **工单 → 频道**：PAY-412 的描述说讨论在 #payments；PAY-431 的描述写明 “Rollout and rollback calls for this change are made in #ledger-rollouts, not #payments.”
6. **频道 → 计划 → 新 PR 号**：#ledger-rollouts 置顶消息的计划是关掉 `tax_line_rounding_v2` flag。线程中 Marco 指出该 flag 只有 checkout-web 读取；Priya 随后更正：从“正在报错的 release 所含 PR”的回滚分支开 PR（只有 revert-1287 与 revert-1291 两个候选，选哪个取决于第 2–3 跳），reviewer 加她、不合并，PAY-431 改回 In Progress，Sentry 分派给她，并把 PR 号贴回线程。Helen 补充：Sentry 问题保持 unresolved。新 PR 的编号（UI 自动分配，预期 #1294）只有在 GitHub 开出 PR 后才知道，之后还要写回 Linear、Sentry、Slack 与 JSON。

G1、L2、K1、O2 直接依赖链条（标为 core）。wrong_hop 夹具（其余全对，只在第 2 跳取了最新的 4.31.1 行）约 0.35，说明主杠杆决定了大部分分数。

## 主要约束（≥4 类）

1. **对象筛选**：按 service + environment + release 三列精确匹配部署行，而不是按时间取最新行。
2. **跨站字段匹配**：完整 SHA ↔ 短 SHA ↔ 合并提交信息里的 PR 号 ↔ PR 描述里的工单号 ↔ Linear 中的重定向 ↔ Slack 频道。
3. **更正 / 失效信息**：PAY-412 已取消，应以 PAY-431 为准；置顶消息的 flag 方案已被线程推翻；#payments 中 11 月 10 日 Tomasz 的“下次照做并找我 review、绿了就合并”属于旧计划。
4. **权限 / 状态**：回滚 PR 必须保持 open（由 Priya 合并）；Sentry 问题保持 unresolved；PAY-431 从 Done 改为 In Progress。
5. **人员选择**：reviewer 与 Sentry 经办人是工单负责人 Priya，不是 PR 作者或 PAY-412 经办人 Tomasz。
6. **保护非目标**：PAY-412 不改；已有 PR 不动；不在 #payments 发消息；不另开其他 PR。
7. **交付格式**：JSON 对象的 7 个键，SHA 为完整 40 位，PR 号为整数。

## 陷阱

| # | 陷阱 | 正确做法 | 检查点 |
|---|---|---|---|
| T1 | deploys.csv 中最新的 checkout-api 行（4.31.1 staging，SHA 前缀 4be1c）以及 web、rc、staging 行 | 按 production + checkout-api@4.31.0 精确匹配 | G1、O2、wrong_hop |
| T2 | #1279/#1283/#1291 的相似合并提交与 revert-1279、revert-1291 分支 | 按完整 SHA 找到 #1287 → revert-1287-line-rounding | G1、G4 |
| T3 | PR 写的是 Closes PAY-412（已取消的重复工单） | 转到 PAY-431 与 Priya | L1、L2、L3、S2、O3 |
| T4 | 置顶 flag 方案已被线程更正；#payments 有旧的回滚计划 | 按 th_pay431 中 Priya 的更正执行 | K1、K2、flag_plan |
| T5 | reviewer 选 PR 作者 Tomasz | reviewer 为 Priya | G2、S1 |
| T6 | 回滚后顺手合并 PR / resolve Sentry | 保持 open 与 unresolved | G3、S3 |

## 浏览器的必要性

Sentry 事件的 release、GitHub 提交与 PR 内容、Linear 工单及评论、Slack 线程都只能在页面中查看；开 PR、加 reviewer、改状态、分派、评论、线程回复都只能通过页面完成。release 到 SHA 的映射只在本地 CSV 中，需要用 CLI 过滤；交付 JSON 也写在本地，二者构成真实的数据依赖。

## 环境复现

- 与参考题相同的单容器多站运行时：sitehost + 浏览器守护进程，启动时四站各开一个标签页。
- 时钟固定为 2026-11-18 09:40（America/Los_Angeles）并实时前进；CSV 与站点数据中的时间为 UTC。
- 每个 trial 为新容器，从种子重新初始化。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，无法直接读取状态或种子。
- sitehost 只接受带随机密钥头的请求；参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：16 个程序化检查点，加权部分分。依赖新 PR 编号 N 的检查以 GitHub 当前状态中 compareBranch = revert-1287-line-rounding 的新 PR 的实际编号为准。“不得做”类检查（G3、G4、L3、S3、K2）只在相关工作已完成时计分，空操作得 0。不调用 gate/cap。

夹具预期：golden=1.0、nop=0.0、naive≈0.10、wrong_hop≈0.35、flag_plan≈0.29、slip_reviewer≈0.92、slip_dup_ticket≈0.75、slip_resolved≈0.94、slip_merged≈0.94。

## 自测与证据

- 已完成：world.py 确定性生成；本地参考打分模拟验证夹具区间；ui_probe 实测 GitHub 开 PR 与加 reviewer、Linear 改状态与评论、Sentry 分派与评论、Slack 线程回复均写入服务端状态。
- 待完成：独立 verifier 编写与 selfcheck、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
