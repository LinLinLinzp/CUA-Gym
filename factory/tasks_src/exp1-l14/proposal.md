# 任务说明：热修复发布与动态跟进（hotfix-release-followups）

- **任务标识与版本**：`cua-hard/hotfix-release-followups`，v0.1.0（exp1 杠杆批次，主杠杆 L14 动态世界）。
- **场景**：数字技术 / 发布管理与热修复。Brightloop 的发布经理 Dana Whitfield 上午被供应商评审会占住，把 checkout-web 4.12.1 热修复的后半程交给代理：定范围、按 QA 结论合并、建 release、补回滚计划、等 SRE 批准后公告。
- **涉及站点**：Jira（CHK 工单、状态流转、标签、子任务）、GitLab（MR、CI/CD 流水线、Release、Wiki 回滚手册）、Slack（范围线程、QA/工程/SRE 的动态回复、#releases 公告），外加本地 CSV（生产部署历史）与本地交付文件。三站均为 CUA-Gym-Hub mock，以真实域名离线提供。
- **输入**：三站初始数据；`/workspace/input/deploy_history.csv`（各环境、各服务的部署记录，含镜像 digest 与状态）。
- **输出**：Jira 标签/状态/子任务、GitLab MR 合并状态、Release 与 Wiki 修改、Slack 公告等服务端持久化状态；`/workspace/output/release_manifest.csv`。

## 动态世界（L14，主难度来源）

`triggers.json` 声明 8 个触发器，全部向 Slack `#checkout-release` 追加固定 messageId 的消息（时间戳为触发时刻的任务时钟）：

| 触发器 | 条件 | 反应 |
|---|---|---|
| trg_qa_412 / trg_qa_423 | Jira CHK-412 / CHK-423 变为 In Review | Marta：QA 通过，可合并 |
| trg_qa_415 | CHK-415 变为 In Review | Marta：QA 不通过（小写过期码仍被接受），不能进 4.12.1 |
| trg_qa_419 / trg_qa_421 | CHK-419 / CHK-421 变为 In Review | Marta：流水线红无法测 / 不在范围 |
| trg_ines_flag | GitLab !15 被合并 | Ines：修复被 klarna_redirect_v2 开关遮蔽，要求在 CHK-430 加“部署后开启开关”步骤，且回滚前须关闭开关 |
| trg_sam_rollback | checkout-web 出现 tag 含 4.12.1 的 release | Sam：批准前需要在 Wiki “Rollback runbook” 补 4.12.1 段落（回滚到生产当前实际运行的 tag+digest，以及需关闭的开关） |
| trg_sam_approve | Rollback runbook 内容含 4.12.1 | Sam：批准生产部署，可以公告 |

核心检查 K1–K6（56/100）全部依赖这些后续消息：不推进就收不到，收到后不处理也拿不到分。golden 终态包含其中 6 条消息及其处理结果。

## 主要约束（≥4 类）

1. **对象筛选**：范围 = 标签 hotfix-4.12.1 的 CHK 工单 + Slack 线程追加的 CHK-423；CHK-426（hotfix-4.12.2）、CHK-402（hotfix-4.12.0，同为 Apple Pay）不在范围。
2. **跨站字段对应**：工单 → MR（目标分支 release/4.12）→ 分支的最新流水线；MR 详情页不显示分支，需从 MR 列表与 CI/CD 页对应。
3. **状态/权限**：Jira 工作流（In Review 才能触发 QA）；只合并 QA 通过的 MR；公告须在 SRE 批准之后。
4. **时间与版本**：以“最新”流水线为准（CHK-415 旧失败新成功，CHK-419 旧成功新失败）；回滚目标取部署历史中生产当前实际运行的镜像（11/14 重建版，11/17 那次已回滚）。
5. **重复/近似实体**：!10 与 !11 标题完全相同，仅目标分支不同；v4.12.0 有三个 digest。
6. **例外**：QA 驳回 CHK-415；Klarna 修复需开关步骤。
7. **保护非目标**：!14（CHK-421）错误指向 release/4.12，不得合并；!11 留给 Ravi。
8. **交付格式**：release_manifest.csv 固定表头与取值。

## 陷阱（均可从可见材料中解出）

- Lena 在置顶范围消息的线程里追加 CHK-423，并需要补标签（S2）。
- Theo 在 CHK-419 的评论称“CI should be green shortly”，实际最新流水线 #4831 失败（S3）。
- !11 与 !10 同名（S1/S4）；!14 指向 release/4.12 但属 4.13（S4）。
- QA 对 CHK-415 的否决只在推进后到达（K1）。
- Ines 的开关请求在合并后到达，且涉及两个站点（Jira 子任务 + Wiki 回滚段落）（K3/K5）。
- 回滚 digest 只能从本地 CSV 得出，且有首发版、已回滚版、staging 版等干扰（K4）。
- CHK-417 早已合并并通过 QA，仍需写入 release、公告与 Done（S5–S7）。

## 浏览器的必要性

工单流转、MR 合并、Release 创建、Wiki 编辑与 Slack 发言只能通过页面完成；模型通过浏览器 MCP 工具（截图 + 坐标/键盘）操作，看不到 DOM、接口或状态文件。本地 deploy_history.csv 决定回滚 digest，清单由 CLI 写出，构成真实的 CLI 依赖（tool_type=2）。操作为常规表单、下拉与文本编辑（operation_difficulty=2：多步流转与跨页中间状态，无拖拽）。

## 环境复现

- 同工厂统一镜像：sitehost + 浏览器守护进程，三站各开一个标签页；每个 trial 新容器，从种子初始化。
- 时钟固定为 2026-11-18 09:30（America/New_York）并实时前进；触发消息延迟 20–40 秒到达，写入后浏览器刷新对应站点标签页。
- `cua/triggers.json` 由 package.py 从 world 输出复制；oracle 写 golden 状态时不经过触发器，golden 已内含触发消息。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，直接请求站点端口会被拒绝。
- 参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：14 个程序化检查点，加权部分分，core=true 的 K1–K6 共 56 分。“不得做”类检查以完成至少一次合并为前提，空操作为 0。夹具预期：golden=1.0、nop=0.0、naive≈0.10、slip_qa415≈0.92、slip_flag≈0.84、slip_digest≈0.92。

## 自测与证据

- 已完成：world.py 确定性生成种子/golden/夹具；instruction 通过 style_lint；ui_probe 实测各类写操作与触发器（见下方记录）。
- ui_probe 实测（2026-11-18，打包草稿 `output/harbor/tasks/exp1-l14`）：Jira 状态下拉 In Progress→In Review、标签回车添加与 × 删除、新建子任务均落入 jira issues；GitLab MR 详情点 Merge（!15→merged）、Releases 新建 v4.12.1（id=6，projectId=1）、Wiki 编辑 Rollback runbook 并保存均落入 gitlab 状态；Slack #releases 发消息落入 messages（时间戳为任务时钟）。触发器 trg_qa_412（30s）、trg_ines_flag、trg_sam_rollback、trg_sam_approve 依次触发并写入 #checkout-release，触发后的刷新未覆盖已有写入；Lena 的线程可在 Slack 中展开阅读。UI 限制：MR 详情页的“Pipeline passed”提示为静态文案，题面以 CI/CD 页最新流水线为准；MR 列表的 Open/Merged 标签页不筛选，但每条 MR 以颜色、详情页以徽标显示状态。
- 待完成：verifier 编写与 selfcheck、Harbor oracle/nop 运行、平台 Qwen×5 / Opus×2 评测。
