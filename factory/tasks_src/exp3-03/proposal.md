# 任务说明：Harbor 迭代交接

- **任务标识与版本**：`cua-hard/harbor-iteration-handoff`，v0.1.1，实验槽位 exp3-03。
- **场景**：组织办公 / 产品迭代交接。Harbor 结账产品负责人 Priya 正与客服开会，请交付协调员 Alex 接手第 24 轮。
- **涉及站点**：Mattermost 的生产交接原始讨论说明例单、QA 例外和证据截止；ClickUp 生产任务的历史活动说明状态和 Sprint 归属；Microsoft Excel for the web 的证据及客服实时账册分别作为输入和交付。
- **输入**：三个网站的网页可见数据。
- **输出**：ClickUp 原任务的状态与 Sprint 归属，以及实时 Excel 账册的 Disposition 和 Sprint Ledger。

## 主要约束

1. **L16 隐含意图**：Mattermost 给出三张生产例单和业务情形，ClickUp 活动给出每种情形的实际状态与 Sprint 操作，Excel 的 H23 Posted 保留对应交接措辞。较晚发出的沙盒走查采用另一组状态、账册措辞和滚动范围。12 项业务检查 90 分均取决于对生产惯例的还原。
2. **范围与去重**：仅处理 Checkout Delivery 中对应 H24 Handoff 待填写行的任务。HBR-207 已于当天交接。HBR-182 虽在 Harbor 24，当前交接表没有该任务。
3. **跨站字段对应**：通过 Checkout Key 对应，HBR-920 与 HBR-205 标题相同但前者归属 Checkout Sandbox。
4. **时间窗口和例外**：以 2026-11-18 09:00 UTC（含）为截止。HBR-202 在截止时通过且只有建议信息；HBR-205 在截止前重新打开验收阻塞；HBR-206 截止后才通过。
5. **保护原始数据**：保留 Sprint 生命周期和任务原位置、原记录、历史旁证、QA 证据及其他账册行。

## 浏览器的必要性

任务需要单任务状态与 Sprint 选择控件以及实时工作簿单元格提交。标签为 operation_difficulty=2、tool_type=1、difficulty=2。避开 ClickUp 整体 Sprint 完成、批量编辑、文档、计时器和工时提交路径。

## 环境复现

固定时钟 2026-11-18 10:00 UTC。三个网站以各自品牌域名离线运行。世界由 world.py 生成，初始和终态分别写到 seed 和 golden，变体保留双方快照。

## 安全边界

草稿打包通过顶层 hide_browser_debug=true 隐藏浏览器调试接口。交接材料全部是模拟站点内的业务记录。

## 评分方式

rubric.json 定义 15 项二元检查，总计 100 分。范围保护以两个站点各有正确业务结果为前提。按规则推导的夹具分数为 golden=1.00，nop=0.00，naive=0.00，slip_reopened=0.85，slip_cutoff=0.85，slip_duplicate=0.76。独立 verifier 已实测全部 15 个检查点。

## 自测与证据

- `style_lint.py` 通过。使用 `package.py exp3-03 --skip-selfcheck` 打包，并在独立容器中执行 `ui_probe.py start / act / diff / state / stop`。安装依赖时使用 npm 官方注册表及本机 CA 配置。
- **ClickUp**：按键搜索可找到 HBR-182，Activity 显示 Priya 将它改为 Ready to Resume 并从 Harbor 23 转入 Harbor 24。通过任务详情的状态选择器分别将 HBR-201 改为 Accepted、HBR-203 改为 Ready to Resume、HBR-205 改为 QA Hold。通过 HBR-203 的 Sprints 选择器转入 Harbor 25。服务端记录出现三个 `status_changed`，HBR-201 写入 `dateClosed` 和 `closedBy=alex`，HBR-203 写入成对的 `sprint_removed`、`sprint_added` 和追加后的 `sprintHistory`。`sprints` 及此次探针未操作的任务不变。初始化时合并了 mock 默认工时配置，该配置不计分。
- **Excel**：从首页打开 Harbor Release Register，确认 H24 Evidence 的时间、结果和备注及 H23 Posted 的三个例单可见。通过网格提交 H24 Handoff 的 C2=Held 和 D2=Harbor 24。服务端保存两个字符串常量及对应 `cell.edit`，切换工作表后返回仍可见。除 C2、D2 外的单元格不变。打开工作簿和选中工作表分别留下 `workbook.open` 和 `sheet.select`。
- **Mattermost**：点击 Harbor Delivery 并展开置顶消息下的 2 条回复，确认生产更正、较晚的沙盒记录和本轮截止时间同屏可读。服务端仅出现频道已读相关的 `channelMembers` 及 `activityLog` 变化，交接原帖和回复保持不变。
- Harbor Oracle 实测 1.00，NOP 及三站 reset 后均为 0.00。六套夹具实测符合上述分数。
