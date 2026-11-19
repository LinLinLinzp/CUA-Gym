# 任务说明：Harborlight 验证重试（harborlight-validation-retry）

- **任务标识与版本**：`cua-hard/harborlight-validation-retry`，v0.1.2，实验槽位 exp3-06。
- **场景**：数字技术 / 发布验证。发布协调员 Priya Das 委托 Jules Moreno 完成 Harborlight 的离线样本清单验证，供 QA 核对收据。
- **涉及站点**：Mattermost 提供有效批次，Microsoft Excel for the web 提供审批对应关系，Bitbucket 执行原运行上的失败步骤重试，ClickUp 保存证据。
- **输入**：四站种子。任务时钟为 2026-11-18 10:20（America/New_York）。
- **输出**：Bitbucket 原构建中的重试组和新增尝试，以及 ClickUp 既有工作项中的一条评论。

## 主要约束（≥4 类）

1. **信息修订**：Priya 的根帖引用预览批次 HBL-7116-O，QA 回复确认实际批次 HBL-7116-Q。
2. **跨站字段对应**：在 November Release Register 的 Batch Intake 中把实际批次匹配到 RV-6429，再到 Retry Approvals 查找 Approved 行和目标仓库、分支、完整提交哈希、流水线、步骤、ClickUp 工作项。
3. **历史运行筛选**：manifest-validator 中 #482 和 #487 同分支且共享相同七位短哈希。运行摘要的提交链接页显示完整哈希。#482 为 `5e77be6ef6a39321d173d39f6dcee788bbf8913c`，#487 为 `5e77be629c2cd6d94d0e116b55707f277cf0b502`。#484 使用正确提交、错误分支，预览仓库也有同号构建。这几条历史记录的流水线名与失败步骤名均相同。
4. **执行权限与次数**：只允许对 #482 的 Validate manifest bundle 重试一次。成功步骤、其他运行、配置和源文件都应保留。
5. **交付格式与目标**：只在 rv-73mqd 留活动评论，含批次、定位第 2 次尝试的链接、步骤、结果和新日志收据。审计副本名称近似；第一次尝试的占位收据格式相同。

## 浏览器的必要性

L05 多跳依赖为主要难点。线程确认批次 → Batch Intake 的审批键 → Retry Approvals 的完整运行标识与收件工作项 → Bitbucket 的历史运行和完整提交详情 → 原生失败步骤重试生成第 2 次尝试及独有收据 → ClickUp 归档。评分检查实际重试及评论中的对应证据。无 CLI 依赖，网页复合操作级别为 2，总难度为 2。

## 环境复现

- 使用四个固定品牌源与隔离会话。标签页预先打开，所有现场数据由 `world.py` 确定性生成。
- `spec.json` 的 `hide_browser_debug` 为 true。QA 使用 `package.py --skip-selfcheck` 与 `ui_probe.py`。
- 验证流水线只处理离线样本清单。题目不要求部署、启动新构建、改动代码或改动配置。

## 评分方式

见 `rubric.json`，11 项共 100 权重。黄金 1.00、空操作 0.00、粗略执行 0.00、误取旧收据 0.80、误发审计副本 0.66。读操作引起的 Excel 打开时间、当前工作表或 Mattermost 阅读游标不属于业务内容变化。

## 自测与证据

- 已用 `package.py exp3-06 --skip-selfcheck` 打包，通过 `ui_probe.py start / act / diff / state / stop` 在隔离容器验证。Mattermost 的 1 reply 打开 Amira 的确认；Excel 从首页打开登记表，在 Batch Intake 第 9 行看到 HBL-7116-Q 对应 RV-6429，在 Retry Approvals 第 9 行查看对应数据。选中 E9 后公式栏显示完整 SHA，横向滚动可看到 H9 的 ClickUp URL。Excel 的实际附带写入是 `workbook.open` 和 `sheet.select`，单元格和工作表内容不变。
- 在 Bitbucket 中通过 Run summary 的短 SHA 链接查看完整 SHA，再在 #482 选择并确认 **Rerun failed steps**。浏览器停留在原构建，URL 带 `step=step-manifest-validator-482-validate&attempt=2`。界面显示 **Attempt 2 · Successful** 和 `Validation receipt: MV-482-Z9K2`。服务端仅 `pipelineRuns` 变化，新增重试组指向唯一失败步骤，新尝试的 retryId 与该组匹配，原成功步骤、原失败尝试和另 51 条运行均未变化。
- 在 ClickUp 的 `/t/rv-73mqd` 用 Activity 的 **Send** 提交单行证据。服务端恰新增一条 `parentType=task`、`parentId=rv-73mqd`、`replyToId=null` 的评论，正文保存完整尝试 URL 及收据，初始评论和工作项字段不变。ClickUp 另外按默认值补齐了 timesheetSettings.approvers 的内置键，这属于初始化合并。首次探针的输入换行触发了提前提交，最终在全新容器中用单行完整内容验证。
- v0.1.1 修正评论结果与第 2 次尝试的关联，接受 succeeded 等等价措辞，并检查获批历史运行的原始变量。保留 v0.1.0 的浏览器操作记录，任务步骤和种子数据不变。未运行求解器、模型或预筛。
