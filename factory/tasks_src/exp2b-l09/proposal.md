# exp2b-l09 · 峰会供应商合同发送前更正（summit-vendor-envelopes，草稿，UI 缺口阻塞）

状态：**blocked:ui_gap**，见 `gaps.json`。2026-11-18 用 ui_probe 实测 DocuSign mock：
- 草稿无法从 UI 重新打开编辑；
- 已发出（delivered）的信封仍能通过 `/prepare/:id` 修改消息并写入服务器，状态不变；
- 发送不记录首发快照，Correct 会覆盖收件人且不留 before/after；
- 所有历史事件的操作者都是写死的 Sarah Chen；
- 新建信封自带一个占位 Document.pdf；
- 上传的 PDF 在放置字段画布上显示为破图。

Airtable 的日期列按 UTC 解析，显示早一天。

因此“过早发送会留下永久错误记录”既不成立，也无法观测，主杠杆 L09 的核心检查无从实现。world.py 的 golden 状态已按 gaps.json 中约定的 `sentSnapshot` 结构生成。mock 补齐后，按下面的设计直接完成（version 升到 0.1.0、写 verifier、跑 selfcheck）。

## 故事

- **人物**：Nadia Okafor，Brightline Events（圣巴巴拉的活动策划公司）创始人兼首席策划。她同时是 Yahoo Mail、DocuSign 和 Airtable 的当前用户。
- **时钟**：2026-11-18 10:00（America/Los_Angeles）。
- **客户与活动**：Halvorsen Biotech 2027 领导力峰会，地点 Mirasol Hotel Santa Barbara。11/10 客户把日期从 1 月 20–22 日顺延为 1 月 21–23 日。
- **前情**：助理 Theo 11/12 按 Airtable 供应商表建好了 DocuSign 草稿，本地 `/workspace/input/contracts` 留有他当时的合同副本。之后邮箱里陆续来了人数变更、签字人交接、乐队降配、班车改期和花艺暂缓。Theo 还在 11/17 把旧版班车合同直接发了出去。
- **委托**：Nadia 下午要去场地，请助理逐一核对后把合同发出去。已发出的错件要作废并重发正确版，暂不能发的标 On hold。完成后同步 Airtable 表，并输出本地汇总 CSV。

## 每个信封的正确处理（L09 核心）

| 信封 | 草稿/现状 | 正确处理 | 证据来源 |
|---|---|---|---|
| Coastline Catering（草稿） | v2，140 人，$23,800，客户签字人 Elise | 换成 v3 净版（不是 redline），总额 $26,350、定金 $7,905；超过 $25k，客户签字人改为 Daniel；之后再发 | Elise 11/14 邮件（155 人）+ Maria 11/16 邮件附件（金额只在 PDF 里）+ Elise 11/5 签字权限邮件 |
| Lumen AV（草稿） | 供应商签字人 Greg | 改为 Priya Raman `priya.raman@lumenav.com` 并排在第一位，客户 Daniel 不变 | Greg 11/13 交接邮件；DocuSign 通讯录里的同名旧联系人 `priya@coastalstageworks.com` 是陷阱；UI 新加的收件人默认排在最后，需开启签署顺序上移 |
| Harbor Lights（草稿） | v1，6 人乐队，$7,500，1 月 22 日 | 换成 v2，$5,800（定金 $2,900），4 人乐队，1 月 23 日 | Elise 11/12 预算上限 $6,000 + Marcus 11/16 邮件附件 |
| Pacific Shuttle（Theo 11/17 已发，已查看） | v1，1 月 20–22 日 | 作废，并写原因；新建信封上传 v2（1 月 21–23 日，定金 12/8 到期），Luis 先签、Elise 后签，然后发出 | Luis 11/17 邮件附件；本地 input 只有 v1 |
| Bloom & Vine 峰会花艺（草稿） | — | 不发，Airtable 标 On hold | Hazel 11/18 未读邮件（周五 11/20 前答复） |
| Sandpiper 摄影（草稿） | 正确 | 原样发出 | — |
| Mirasol 场地 | 11/12 已签完，另有一份重复草稿 | 不动，CSV 填 already_signed | DocuSign 已完成信封 + Theo 邮件 |

**非目标**：
- Marlowe-Chen 婚礼的两份草稿。Hazel 另一封邮件说婚礼花艺可以发，但新人要求暂缓。
- 约 8 个历史信封（已完成、已作废、已拒签）。
- Airtable 中的 Seaside Signs（无合同）和 Gold Coast Rentals（在线下单，不走 DocuSign）两行。
- 婚礼表和联系人表。

## 主要约束（≥4 类）

1. **对象筛选**：只处理 Halvorsen 峰会的信封，排除婚礼和历史信封，也排除重复的场地草稿。
2. **跨站字段匹配**：邮件附件 PDF 决定 DocuSign 文档、金额和日期；邮件决定签字人；Airtable 行跟随实际发出的内容。
3. **金额与阈值**：$25,000 签字权限（$26,350 越线，$9,750、$5,800、$4,800 不越线）；$6,000 娱乐上限；定金金额。
4. **时间窗与日期**：1 月 20–22 日顺延为 21–23 日；乐队改到周六 23 日；班车定金到期日改为 12/8；Airtable Sent On 为当天 2026-11-18。
5. **状态与不可逆**：已发信封只能作废重发；不可先发后改。
6. **例外与暂缓**：花艺 On hold。
7. **保护非目标**：同上。
8. **交付格式**：CSV 的表头、action 枚举和两位小数。

## 陷阱（≥3）

- **更正与新版本**：catering v3 取代 v2，且同封邮件带一份不可签的 redline；乐队 v2 取代 v1；班车 v2 取代 v1；客户改期。
- **第二来源才有的事实**：新金额只在附件 PDF 中（需下载后用 pdftotext 读取）；本地 input 是过期副本。
- **近似实体**：DocuSign 通讯录中有同名的 Priya（另一家公司）；Hazel 的婚礼邮件；重复的场地草稿；Lumen 早先作废的同名信封。
- **已处理项**：场地已签；班车在 Airtable 已标 Sent，但实际是错件。
- **阈值边界**：修订后总额越过签字权限，客户签字人必须随之变化。

## 浏览器的必要性

- **Yahoo Mail**：所有更正信息和修订版 PDF 附件都在这里。
- **DocuSign**：编辑并发送信封、作废、新建。
- **Airtable**：读取 Theo 的基线，并写回状态。

三站缺一不可：没有 Yahoo 就不知道要改什么；DocuSign 是不可逆提交所在地；Airtable 是需持久化的第二个站点。

## CLI 的必要性

- 修订版合同的总额、定金和日期只写在 PDF 正文里，需要在 `/workspace/downloads` 下用 pdftotext 读取。
- 本地 `/workspace/input/contracts` 是过期版本，可用来比对差异。
- 必须写出 `/workspace/output/summit_contracts.csv`。

## 环境复现

`world.py` 用 worldkit 生成，结果确定：
- 11 份合同 PDF（`long_pdf`）和 DocuSign 页面预览 PNG；
- 三个站点的 seed；
- 按补丁后 mock 结构写出的 golden；
- expected.json，包含文档文件名、字节数和 sha256、过期文本正则、Airtable 期望更新以及 CSV 行；
- 7 个 variants。

Yahoo 附件放在 `seed/files/yahoo_mail/`，DocuSign 已有文档放在 `seed/files/docusign/`。

## 安全边界

- 只作废 Theo 发错的班车信封。
- 不向婚礼客户或供应商发送任何东西。
- 不发送、不删除暂缓的花艺草稿。
- 所有地址均为虚构域名或 mock 内地址。

## 评分方式

见 `rubric.json`，共 15 个检查点，权重合计 100：
- DocuSign 9 项（56 分，其中 C1–C5、C9 为 core，依据首发 sentSnapshot）；
- Airtable 5 项（21 分）；
- CSV 1 项（7 分，按行部分得分）。

“不应发送/不应改动”类检查以至少一个目标信封首发正确为门控。

## 自测与证据

用 /tmp 下按 rubric 写的模拟评分器跑 variants：

| variant | 得分 |
|---|---|
| golden | 1.00 |
| nop | 0.00 |
| naive | 0.06 |
| slip_authority | 0.81 |
| slip_floral | 0.88 |
| slip_send_then_correct | 0.82 |
| slip_shuttle | 0.80 |

UI 探测证据见 `gaps.json`。已实测可用的操作：
- Yahoo 附件下载到 /workspace/downloads，pdftotext 可读；
- DocuSign 上传 PDF（保留文件名，fileSize 2443 与 expected 一致）；
- DocuSign 作废（需填原因）、Correct、发送；
- Airtable 文本单元格编辑；
- Airtable 单选单元格编辑（原生 select，用键盘选择）。
