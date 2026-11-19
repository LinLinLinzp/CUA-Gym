# 任务说明：Halvorsen 价目表导入 Plateful（halvorsen-plateful-pricefile）

- **任务标识与版本**：`cua-hard/halvorsen-plateful-pricefile`，v0.1.0（exp2b 杠杆批次，槽位 exp2b-l13，主杠杆 L13 文件往返）。
- **场景**：组织办公 / 采购数据维护。波特兰四店烘焙咖啡集团 Fennwick Provisions 的运营分析师 Priya Raman 委托处理：把供应商 Halvorsen Mill & Pantry 的 2027 价目表转换成配方成本系统 Plateful 要求的格式，从旧 Yahoo 账户发给 Plateful 导入，并按运营总监 Dana 的要求维护 Airtable 物料主数据。
- **涉及站点（3 个，均必要）**：
  - Gmail（Priya 的工作邮箱）：Marta 11-13 发来的价目表 v1、11-16 同线程回复的 rev B（生效日改为 12-07、更正行追加在末尾），Dana 11-17 的装载规则，以及同姓的 Halvorsen Dairy Co-op 的价目表干扰邮件。**下载源**。
  - Yahoo Mail（fennwickbakery@yahoo.com，Plateful 唯一接受的发件账户）：Plateful 2025 年的 v2 模板（英制、MM/DD/YYYY、旧地址）与 2026-10-06 的 v3 通知（仅公制、ISO 日期、换算系数、专属导入地址 fennwick-7q2k@imports.plateful.app），以及 8 月发往旧地址的历史导入。**上传目标**：附件经 `/upload` 真实落盘，验证器读取文件内容。
  - Airtable（Fennwick Purchasing 基）：Supplier Items 表提供 Item Code ↔ Supplier SKU 映射、Costing Unit、当前 Case Price、合约价与截止日、Status；Suppliers 表有 Prices Effective。**映射来源 + 第二处持久化**。
- **输入**：三站种子；Gmail 附件 `HMP_PriceList_2027.csv`、`HMP_PriceList_2027_revB.csv`、`HDC_Prices_Jan2027.csv`（下载到 /workspace/downloads）。无 /workspace/input。
- **输出**：Yahoo 已发送邮件（含上传的 CSV 附件，文件在 /var/lib/cua/files/yahoo_mail/<sid>/）；Airtable 状态/复选框/日期改动；本地 `/workspace/output/halvorsen_plateful_prices.csv`。

## 主杠杆 L13（文件往返）

从 Gmail 下载 rev B → 本地 CLI 处理（按 Item No 取 Revised 最新行去重、按 Price Basis 换算整箱价、英制换公制、按“供应商 + SKU”映射 Airtable Item Code、剔除 Inactive/停产/合约覆盖条目）→ 在 Yahoo 写邮件、从电脑上传附件并发送。上传文件内容决定 74/100 分（F1–F9、U1），换算精度（case_qty 三位、cost_per_unit 四位）只能靠脚本稳定达成。

## 主要约束（≥4 类）

1. **对象筛选 / 权限状态**：仅 Halvorsen Mill & Pantry 且 Airtable Status=Active；FP-1004 为 Inactive。
2. **跨站字段匹配**：价目表 Item No ↔ Airtable Supplier SKU，必须同时匹配 Supplier；Halvorsen Dairy Co-op 的 FD-2040（12040）与 FD-2421（10421）撞号。
3. **金额/数量计算**：LB/EA 计价乘 Pack×Size；英制→公制（系数在 v3 通知里）；cost_per_unit = case_price / case_qty；Price Review 阈值 > 8%。
4. **时间窗口**：生效日 12-07（更正后）；合约 Contract Ends ≥ 生效日才排除（FP-1021 排除，FP-1022 于 12-06 结束需按新价）。
5. **重复**：11218 原样重复两行；rev B 中 4 个 Item No 有更正行。
6. **版本冲突/更正**：价目表 v1→rev B；Plateful 模板 v2→v3（格式、单位、日期、地址全部变更）。
7. **交付格式**：固定表头、两位/三位/四位小数、KG/L/EA、YYYY-MM-DD、CSV 附件 + 本地同内容副本。
8. **保护非目标**：不在 Airtable 手填价格；其他供应商、FD-2210 已有的 Price Review、其他记录不动。

## 陷阱（≥3，均可从可见材料中解出）

| 陷阱 | 可见依据 | 粗心做法 | 检查点 |
|---|---|---|---|
| 价目表被回复更正 | Gmail 同线程 11-16 回复 + rev B 附件 | 用 v1、生效日 12-01 | F2、F4、F5、F8、A1–A3 |
| 追加更正行，按 Revised 取最新 | 回复正文 + Revised 列 | drop_duplicates 保留首行 | F2、F3、F4、A2 |
| 同姓供应商撞号 | Dana 邮件 + Airtable Supplier 列 | 只按 SKU 匹配 | F6、A4 |
| 合约截止边界 | Airtable Contract Ends + 更正后生效日 | 所有合约条目都排除 / 用 12-01 判断 | F5、A2 |
| Plateful 规格被新通知取代 | Yahoo 10-06 v3 通知 | 用 v2 模板英制、MM/DD/YYYY、旧地址 | F1、F7、F8、U1 |
| 包装规格变化 | 价目表 Pack/Size 与 Airtable Pack 不同 | 用 Airtable 4 x 32 fl oz | F7 |
| 近阈值与已排除条目 | 价格比例 | 勾 FP-1071（+7.6%）或 FP-1021 | A2 |

## 浏览器的必要性

附件下载、Yahoo 写信/上传附件/发送、Airtable 单选/复选框/日期编辑都只能在页面中完成；模型通过 task.toml 声明的浏览器 MCP 工具操作，看不到 DOM、站点接口或状态文件。本地转换依赖下载的 CSV，结果文件又必须回传到 Yahoo，形成真实的 CLI 依赖（tool_type=2）。操作难度 2：撰写邮件 + 文件上传选择器 + 网格单元格编辑，均为带中间态的复合控件，无拖拽。

## 环境复现

- 同工厂运行时：sitehost + 浏览器守护进程，三站各开一个标签页；时钟固定为 2026-11-18 10:15（America/Los_Angeles）。
- 种子文件：Gmail 附件放在 seed/files/gmail；Yahoo 历史附件与 golden 上传文件（不可猜测的 sha 前缀存储名，种子中无引用）放在 seed/files/yahoo_mail。
- 健康检查：`curl -fsS http://127.0.0.1:8079/health`。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读，模型以 `agent` 用户运行；站点接口需随机密钥头；参考解经 `/__oracle/apply` 写入 golden 状态。

## 评分方式

见 `rubric.json`：14 个程序化检查点，加权部分分；“不应包含/不应改动”类检查以完成对应工作为前提，空操作得 0。`expected.json` 给出每行期望值、排除集合与 Airtable 目标。夹具估分：golden=1.0、nop=0.0、naive≈0.17、slip_v1_file≈0.63、slip_dedupe_first≈0.80、slip_plateful_v2≈0.74、slip_dairy_collision≈0.94、slip_contract_boundary≈0.94。

## 自测与证据

- 已完成：world.py 生成与草稿打包；ui_probe 实测 Gmail 附件下载（落到 /workspace/downloads）、Yahoo“Attach files from computer”上传并发送（附件 source='upload'，落盘文件与本地副本逐字节一致）、Airtable 单选（Status）/复选框（Price Review）/文本（Prices Effective）写入，均出现在服务端状态中。
- 探测中发现并处理：① 运行时 browserd 经 route.fetch 转发请求时 Chromium 丢弃 FormData 中的文件内容（上传 0 字节）→ 已在 `runtime/browser/browserd.py` 增加 INLINE_UPLOAD_BODIES 初始化脚本，把含文件的 multipart 序列化为内存字节后再发送，重测通过；② Airtable mock 的 date 类型单元格把 YYYY-MM-DD 按 UTC 解析，在洛杉矶时区显示早一天 → 本题的 Contract Ends 与 Prices Effective 改用文本字段存 ISO 日期，避免依赖该显示缺陷；③ 无头 Chromium 中原生 select 弹出层的鼠标点击不生效，键盘（方向键 + Enter）可正常选择 Discontinued。
- 待完成：verifier 编写与 selfcheck、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
