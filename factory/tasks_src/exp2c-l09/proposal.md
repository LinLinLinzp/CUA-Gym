# 任务说明：退款队列——先核对再出手（refund-queue-before-payout）

- **任务标识与版本**：`cua-hard/refund-queue-before-payout`，v0.1.0（exp2c 杠杆批次，主杠杆 L09 不可逆与顺序）。
- **场景**：产业运营 / 电商售后退款。波特兰咖啡器具网店 Kettle & Crane Coffee 的客服负责人 Rina Takahashi 整天开供应商会议，把自己 Zendesk 队列里的退款工单交给助理在当晚结算（payout）前清完。
- **涉及站点**：Stripe Dashboard（订单 charge、既有退款、Disputes 争议、发起退款与提交争议证据）、Zendesk（Rina 的工单队列、客户后续更正、内部备注、回复与状态、合并重复工单）、Yahoo Mail（外部记账师 Malcolm 的退款规则新旧两版、逐单审批线程、Stripe 争议通知，发出审批请求），外加本地 CSV（仓库退货日志）与本地交付文件。三站均为 CUA-Gym-Hub mock，以真实域名离线提供。
- **输入**：三站初始数据；`/workspace/input/returns_log.csv`（RMA、订单号、SKU、状态 received/in_transit/label_created、入库日期、检验备注）。
- **输出**：Stripe 新增退款与争议证据状态、Zendesk 公开回复/状态/合并、Yahoo 发给 Malcolm 的审批邮件等服务端持久化状态；`/workspace/output/refund_queue.csv`（ticket,order,action,refund_amount）。

## 主杠杆 L09：不可逆与顺序

Stripe 退款只能新增、无法撤销（mock 中 ADD_REFUND 只追加 refunds 记录并累加 amount_refunded，界面无任何撤销/删除入口）。9 张退款工单里有 8 张的“表面诉求”是错的或必须先改正/等待：客户在后文改了金额、退货还没入库、需要的审批在邮件线程后面才到、已经退过、客户已向银行发起争议。只要在核对前点了 Refund，错误就永久留在 refunds 历史里——评分逐笔检查新增退款记录（而非最终 amount_refunded），“先退错再补”“分多笔凑数”都无法洗白（多笔凑对只得 0.5）。核心检查点 S1–S8 标为 core，合计 62/100 权重。

## 工单真值（9 张，均在 Rina 名下）

| 工单 | 客户 / 订单 | 表面诉求 | 正确处理 | 陷阱来源 |
|---|---|---|---|---|
| 4412 | Hannah Lowell / KC-48213 | 整单 $248 | 只退研磨机 189.00，Solved | 同工单后续评论改为保留电子秤 |
| 4409 | Marco Bellini / KC-48190 | （催单写 $64） | 整单损坏退商品+运费 71.00，Solved | 新规则第 2 条：整单损坏退运费；9 月同额旧单 KC-47702 不得动 |
| 4415 | Marco Bellini / KC-48190 | $64 | 4409 的重复催单：合并/关闭，不退第二笔 | 邮件渠道、标题不同 |
| 4405 | Lucia Fernandez / KC-48122 | $677 | 按 Malcolm 最终批准退 649.00，Solved | 邮件线程：先“暂缓”，11/17 晚的未读回复才批准 649（她保留了奶缸） |
| 4411 | Samuel Okoro / KC-48219 | $189 | 已拆封改主意，扣 15% 退 160.65，Solved | 9 月旧规则 10%（170.10）已作废；退货日志“opened, used”；Stripe 邮箱与 Zendesk 不同；近似客户 Sam Okafor KC-48226 同为 $198 |
| 4416 | Priya Shah / KC-48155 | $21 | 已于 11/14 由 Theo 退过，不再退，Solved | 已处理项：旧工单 #4398 + Stripe 既有 2100 退款 |
| 4413 | Derek Olsen / KC-48177 | $214“没收到” | 不退款；在 Stripe Disputes 提交证据（UPS 签收），工单回复 | 争议只在 Stripe Disputes 与通知邮件可见；Theo 内部备注给出签收证据；新规则第 5 条 |
| 4418 | Ben Arnaud / KC-48204 | $318 | 超 $250 且无批准：给 Malcolm 发审批邮件（客户、单号、318.00），不退款，On-hold | 收件箱里 10/28 的批准是 Ben 另一订单 KC-47655 的（已退）；9 月旧规则“$500 内免审批”已作废 |
| 4420 | Grace Whitaker / KC-48231 | $129 | 退货仍在途（仅本地 CSV 可见），不退款，On-hold | 客户已给退货单号，看起来“已寄回” |

## 主要约束（≥4 类）

1. **对象筛选与权限**：只处理 Rina 名下的退款工单；Theo 名下的 #4414（Nora，退货日志里也有）不得动；Rina 队列中的非退款工单（4401/4417/4419/4421）不改状态。
2. **跨站字段匹配**：按 KC- 订单号把 Zendesk 工单对到 Stripe charge（Payments 搜索描述 “Order KC-…”；Samuel 的邮箱两站不同；近似客户 Sam Okafor）；Disputes 列表只显示 payment ID，需对回 Derek 的订单。
3. **金额计算**：部分退款（Hannah 189）、含运费（Marco 71）、15% 重新上架费（Sam 160.65）、按批准金额（Lucia 649）。
4. **审批与顺序**：> $250 必须先有 Malcolm 书面批准且按批准额退；批准在线程最新回复里；没有批准就发请求并挂起。
5. **版本冲突**：11/2 新规则取代 9/8 旧规则（审批额度、重新上架费比例、运费、争议）。
6. **重复与已处理**：#4415 重复催单；Priya 已退；Marco 9 月同额旧单；Ben 10 月旧批准。
7. **例外**：争议中的 charge 不退款，改为提交证据。
8. **交付格式**：本地 CSV 固定表头与 action 枚举、两位小数金额。

## 浏览器与 CLI 的必要性

退款、提交争议证据、回复工单/改状态/合并、发邮件都只能通过页面完成。退货日志只在本地 CSV 中，决定 Grace 不能退（in_transit）、Sam 是“opened”而扣费、Lucia/Hannah/Marco/Ben 已入库；汇总 CSV 需在本地写出，形成真实 CLI 依赖。

## 评分方式

见 `rubric.json`：16 个程序化检查点，加权部分分（满分 100），其中 S1–S8 为 core。“不应退款/不应改动”类检查（S5–S9、Z5）以 S1–S4 至少一项得分为前提，空操作得 0。

预期夹具分数：golden=1.0；nop=0.0；naive≈0.0（按客户诉求全退、读旧规则、不发审批、不提交证据）；slip_approval≈0.85；slip_restock≈0.88；slip_dispute≈0.90；slip_correction≈0.88。

## UI 可行性（ui_probe 实测）

2026-11-18 用 `ui_probe.py` 在打包后的容器里逐类实测，均在 `/var/lib/cua/state/<site>/current.json` 中确认：

- **Stripe 退款（不可逆性探针）**：Payments → Hannah 的 $248.00 → Refund，弹窗输入 189.00 → refunds 新增 1 条 18900、amount_refunded=18900、refunded=false，同时新增 balanceTransactions 与 charge.refunded 事件；退款后页面只剩“Refund”按钮（可继续追加），没有任何撤销/删除入口，代码中 refunds 只在 ADD_REFUND 里被追加——退款确属永久记录。弹窗金额框为空时占位符 248.00 不会被提交。
- **Stripe 争议证据**：More → Disputes → $214.00 行 Respond → 填写 Explanation → Submit Evidence → 该 dispute status=under_review、evidence_submitted_at 写入。
- **Zendesk 回复与状态**：#4420 公开回复 + “Submit as Hold” → 新增 public=true、author_id=1 的评论，status=hold。
- **Zendesk 合并**：Your unsolved tickets 视图勾选 #4415 → Merge → 目标选 #4409 → 4415 closed，两边各加一条内部备注（与 world.py 的 golden 完全一致）。目标下拉为原生 select，键盘输入 “#4409” 可选中；评分同样接受把 4415 直接设为 Solved。
- **Yahoo 发信**：Compose → 收件人 malcolm@ferrisbookkeeping.com、主题、正文 → Send → messages 新增 folderId=sent，activityLog 新增 message.send。

未发现缺失功能，无需 gaps.json。

## 环境复现

- 时钟：2026-11-18 09:40（America/Los_Angeles），页面 `Date` 固定并实时前进。
- 每个 trial 新容器、从种子初始化。
