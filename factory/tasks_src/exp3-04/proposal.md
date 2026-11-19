# 任务说明：续约超时费对账

- **任务标识与版本**：`cua-hard/retainer-renewal-true-up`，v0.1.1。
- **场景**：专业事务 / 续约超时费对账。Birch & Vale Consulting 的 Maya 委托同事核完 Cedarline Foods 十月超时费，在账单审核前备妥草稿。
- **涉及站点**：Yahoo Mail 提供执行协议、预算估算及已签续约条款。Microsoft Excel for the web 提供已入账分钟与迟交审批记录，接收可复核计算和草稿编号。FreshBooks 提供实际已开票抵扣金额，接收两张未发送草稿。
- **输入**：三个站点的可见初始记录。
- **输出**：FreshBooks 中的两张未发送美元草稿，以及工作簿 October Retainer Close 中的计算结果和发票编号。

## 主要约束

1. **跨站字段对应**：仅对 Cedarline Foods 按 Period ID 核对，近名 Cedarline Foodservice 另有其发票与迟交工时。
2. **时间和版本**：十月共 31 天，前段 15 天，后段 16 天；10 月 16 日零时按太平洋日期进入已签订新方案，10 月 12 日报价未生效。
3. **重复和审批**：重复的 CF-782 只计首行，拒绝的 CF-795 排除，已入账 CF-763 已包含在 278 分钟内。
4. **数值精算 L12**：先向下取整额度，前段为 290 分钟，后段为 379 分钟；合计超时分别为 119、103 分钟。对各期超时按各自档次计算，档次金额合计后四舍五入到美分，得到 318.65、299.60。减去已开超时费 36.47、28.63，净额为 282.18、270.97。前段若先对各档金额取整，结果为 318.66。
5. **保护非目标数据**：保留基础费、其他月份和近名客户的账单，拒绝更正与重复记录无草稿号。

## 浏览器的必要性

在 FreshBooks 的标准发票草稿中使用自定义明细记录净差额。如此可以处理尚未导入 FreshBooks 的 Excel 迟交工时，同时不改写原有账单。Excel 的单元格写入和 FreshBooks 的发票表单保存构成复合操作。全部资料与交付均在网站，标签为 2 × 1 = 2。

## 环境复现

三个站点以目录中的品牌域名启动。冻结时钟为 2026-11-18 09:30（America/Los_Angeles）。服务端快照、基准终态和变体均由 world.py 生成。

## 安全边界

打包配置关闭浏览器调试入口。站点数据以独立容器隔离，评分使用服务端持久化快照。

## 评分方式

见 rubric.json，12 个客观检查共 100 分。其中发票净额和对账数值共 76 分。预期 golden=1、nop=0、naive≤0.35、slip_duplicate=0.62、slip_rounding=0.72。

## 自测与证据

- **打包与静态验证**：`style_lint.py` 通过，`package.py exp3-04 --skip-selfcheck` 成功生成草稿，运行配置为 `hide_browser_debug=true`。
- **FreshBooks**：在隔离容器中从 New Invoice 选择 Cedarline Foods，填写 Reference，添加 Custom line 并保存。服务端记录两条 `invoice.created`。INV-2084 对应 CF-2026-10A，金额 USD 282.18。INV-2085 对应 CF-2026-10B，金额 USD 270.97。两张均为 draft，`sentAt=null`，28 条旧发票保持原样。
- **Excel**：通过浏览器填写 Closeout D2:I3 和 Late Time H2/H3/H5/H6。服务端出现 16 条 `cell.edit`，全部单元格的值与黄金状态一致。重复行及拒绝更正行的引用留空，已入账行仍为 INV-2080。切换工作表会写入 `sheet.select` 及 `activeSheetId`，该浏览状态不影响评分。
- **Yahoo Mail**：搜索 Cedarline Foods 可找到已执行协议、旧估算、已签续约及近名客户邮件。已打开签署邮件，正文显示生效日期、分钟额度和两档费率。服务端邮件记录保持原样。
- **夹具抽查**：按检查点逐项核对五套生成状态，得分依次为 golden 1.00、nop 0.00、naive 0.05、slip_duplicate 0.62、slip_rounding 0.72。
- **范围**：Harbor Oracle 实测 1.00，NOP 及三站 reset 后均为 0.00。独立 verifier 和五套夹具均已验证。
