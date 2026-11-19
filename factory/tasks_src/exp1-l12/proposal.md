# 任务说明：Hartley 家年中跨州搬迁的加州报税（hartley-part-year-calfile）

- **任务标识与版本**：`cua-hard/hartley-part-year-calfile`，v0.1.0（exp1 杠杆批次，主杠杆 L12 数值精算）。
- **场景**：公共事务 / 个人报税。Daniel Hartley 2024 年 6 月从俄勒冈波特兰搬到萨克拉门托，与全年加州居民 Leah 夫妻合并申报。会计 Gloria Reyes 已完成联邦申报，并在邮件中给出 CalFile（只支持 540）的填报规则：只把 Daniel 俄勒冈期间的收入通过 Schedule CA 减项排除。Daniel 把收尾工作交给代理完成。
- **涉及站点**：CalFile/MyFTB（webapp.ftb.ca.gov：W-2、1099-INT、其他收入、联邦 AGI、减项、预缴、提交、Web Pay）、Gmail（规则邮件、PDF 附件、收费表及其更正、Leah 的收据与付款账户、回复确认号）、PayPal（摄影客户收款毛额、退款、加元款、向会计付费）。外加本地 CSV（加拿大央行 USD/CAD 汇率）与本地交付文件。三站均为 CUA-Gym-Hub mock。
- **输入**：三站初始数据；`/workspace/input/boc_usdcad_2024.csv`（date,FXUSDCAD，仅发布日，周末与加拿大法定假日无数据）。
- **输出**：CalFile 申报表与 Web Pay 记录、PayPal 付款、Gmail 已发送邮件等服务端持久化状态；`/workspace/output/photography_2024.csv`。

## 数值链（L12 主杠杆）

| 量 | 规则 | 正确值 |
|---|---|---|
| 居民起始日 | 租约 PDF 第 2 条生效日（非签约日 6/5、非 Daniel 自述 6/15） | 2024-06-18 |
| 俄勒冈天数 | 1/1～6/17，闰年 366 天 | 169/366 |
| WVCU 利息俄勒冈份额 | 612.40×169/366，四舍五入到分 | 282.77 |
| PayPal 手续费（PayPal 只显示毛额，费率在 Gloria 邮件中） | USD 3.49%+0.49，CAD 4.99%+CA$0.59，每笔舍入到分；金额已避开半分进位歧义 | 例：875→31.03，CA$640→32.53 |
| 加元款 | 净额 ÷ 当日汇率；无汇率用此前最近发布日（3/23→3/22，9/2→8/30，12/28→12/27）；每笔先舍入到分 | 839.31 / 442.79 / 633.39 / 316.34 |
| 摄影净收入（13 笔） | 10 笔收款净额 − 2 笔退给客户的退款 | 7839.99 |
| 其中俄勒冈期 | 6/18 之前（含 6/15、6/17） | 4157.82 |
| Schedule CA 减项 | 38416.92 + 282.77 + 4157.82 | 42857.51 |
| 联邦 AGI | Gloria 4/2 终值（3/18 草稿 164493.60 作废） | 163591.78 |
| 2024 税年预缴 | 250 + 300 + 450（排除 2023 Q4 180、2025 Q1 200） | 1000.00 |
| 应缴余额（CalFile 自动计算） | 依赖以上全部输入 | 402.32 |
| 会计费 | (240+120+95+15)×(1−15%)，按同线程更正版收费表 | 399.50 |

## 主要约束（≥4 类）

1. **金额计算**：按天数比例分摊、汇率换算与回退、逐笔舍入、手续费扣除、退款记负、阶梯收费与折扣；全部精确到分。
2. **时间窗口**：居民日边界（6/17 vs 6/18）、只计 2024 年的 PayPal 交易、只计 2024 税年的预缴（按税年而非缴款日期）。
3. **对象筛选**：只计摄影客户的已完成款项；排除相机卖出款（goods）、私人转账、供应商退款、待处理请款。
4. **跨站字段对应**：PDF 附件 → CalFile 表单；PayPal 交易 → CSV 与其他收入；汇率 CSV → 加元换算；Leah 邮件 → Web Pay 账户。
5. **版本冲突**：W-2c 更正 Leah 的工资；收费表被同线程回复更正；联邦 AGI 草稿被终值取代；搬家日期以租约为准。
6. **重复/已处理**：Leah 的 W-2 和 1099 已在 CalFile 中，需编辑而非重复录入；MyFTB 中已有历史预缴记录。
7. **交付格式与保护非目标**：CSV 列与格式固定；个人信息、抵免、加项不得改动；费用不得付到会计私人账户。

## 陷阱

- Daniel 已发邮件写“6 月 15 日搬家”，租约生效日为 6/18（6/15 的 Pearl District、6/17 的 Northbound 款归俄勒冈期）。
- PayPal 只显示毛额，手续费需按 Gloria 邮件中的费率自行扣除（加元先扣费再换算）。
- 4 笔加元款中 3 笔落在周六或加拿大法定假日；PayPal 导出的 CSV 没有币种列，只有列表/详情中显示 CA$。
- Cascade 的 W-2 只有俄勒冈州栏，州预扣 2987.11 不应填入加州预扣。
- W-2c 的“原报/更正”两列；Box 2、Box 17 不变。
- 收费表更正（85→120，10%→15%）；PayPal 联系人中同时有 “Gloria Reyes”（私人）与 “Reyes Tax Services”（业务）。
- Leah 的 Web Pay 收据跨三个税年；付款需用联名支票户（尾号 4471），不用旧储蓄户 2290；Web Pay 默认日期为今天，需改为 4/15。

## 已知 mock 限制

paypal_mock 的种子归一化（`normalizeTransaction`）会丢弃 fee、netAmount、transactionId、category 等字段，详情弹窗中的手续费、交易号无法通过种子显示。因此本题不依赖这些字段：手续费规则放在 Gloria 邮件中，CSV 以日期为键。

运行时：Gmail 附件是 `<a download href=…>`，Chromium 对带 download 属性的链接直接走下载管理器、绕过 Playwright 请求拦截，离线时下载失败。已在 `runtime/browser/browserd.py` 加入点击时去掉 http(s) 链接 download 属性的 init script（sitehost 已返回 `Content-Disposition: attachment`），UI 探测确认点击附件后文件落到 `/workspace/downloads`。本题依赖此修复，需使用含该修复的镜像。

## 浏览器的必要性

CalFile 的多步表单、W-2 编辑与新增、提交签名、Web Pay，PayPal 的交易明细（日期、毛额、币种）与付款，Gmail 的附件下载与回信，都只能通过页面完成。附件 PDF 下载到 `/workspace/downloads` 后可用 `pdftotext` 读取；汇率文件只在本地，加元换算必须结合 CLI 数据，形成真实依赖。

## 环境复现

- 同工厂统一运行时：sitehost + 浏览器守护进程，三站各开一个标签页；每个 trial 从种子重新初始化。
- 时钟：页面内 `Date` 固定到 2025-04-10 09:15（America/Los_Angeles）并实时前进。

## 评分方式

见 `rubric.json`：14 个程序化检查点，加权部分分；L12 相关核心项（C1、C2、C9、C10、C13）合计 56 权重。C11、C14 以完成对应工作为前提，空操作得 0。夹具预期：golden=1.0、nop=0.0、naive≈0.22、slip_move_date≈0.79、slip_fx_fallback≈0.68、slip_w2c≈0.94、slip_estimates≈0.89、slip_fee_card≈0.94。

## 自测与证据

- 已完成：world.py 生成全部夹具；草稿评分脚本按 rubric 规则核对夹具分数。
- 待完成：verifier 实现、selfcheck、本地 oracle/nop 运行、平台评测。
