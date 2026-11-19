# 任务说明：Stripe 打款逐笔对账（stripe-payout-reconciliation）

- **任务标识与版本**：`cua-hard/stripe-payout-reconciliation`，v0.1.1（实验批 exp1，槽位 exp1-l04，主杠杆 L04 规模）。
- **场景**：专业事务 / 代账与收款对账。普罗维登斯六人设计工作室 Fernhill Creative 的外包记账员 Rosa Delgado，在 2026-11-16（周一）上午补做 Stripe 收款对账。客户通过 Stripe 付款链接刷卡付发票；Stripe 每周二、五自动打款到 Citizens Bank 支票账户。
- **涉及站点**：QuickBooks Online（发票收款、费用、银行流水；主站）、Stripe Dashboard（付款详情、描述与 metadata、退款、payout 状态）、Gmail（老板 Nadia 与客户来信、发送催款邮件），外加本地 CSV（Stripe itemized payout 导出）与本地交付文件。三站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：三站的初始数据；`/workspace/input/stripe_payouts_nov.csv`，即 Stripe 逐项 payout 对账导出，共 5 个 payout、51 行。列为 automatic_payout_id、automatic_payout_effective_at、balance_transaction_id、created_utc、reporting_category、source_id、payment_intent_id、customer_email、gross、fee、net、currency。导出**没有描述列**，每笔付款写了哪个发票号必须到 Stripe 上逐笔查看。
- **输出**：
  - QuickBooks：32 张发票收款（Receive payment），另为两个 payout 各新增 1 条 Stripe 手续费 expense。
  - Stripe：1 笔全额退款。
  - Gmail：2 封少付催款邮件。
  - 本地文件 `/workspace/output/payout_reconciliation.csv`，35 行。

## 主杠杆 L04：规模

两个已到账、尚未记账的 payout 共含 35 笔客户扣款，每一笔都要经过 CSV → Stripe → QuickBooks 的查找：

1. 用 CSV 里的 payment_intent_id 在 Stripe 找到这笔付款，读描述和 metadata。
2. 到 QuickBooks 按客户、发票号和未付余额找到对应发票。
3. 决定这笔付款的处理方式：收款、留作未结并发邮件催款，或在 Stripe 退款。

其中 17 笔是常规付款，其余 18 笔混入了各类陷阱：

- 3 笔尾款要和余额比，而不是和发票总额比；
- 2 笔是一次付多张发票；
- 1 张发票分两笔付清；
- 2 对重复扣款；
- 2 笔少付；
- 1 笔差额经老板同意豁免；
- 1 笔写错了发票号；
- 1 笔的发票号由客户事后更正；
- 2 笔没有写发票号，其中 1 笔有近似重名客户。

另有 1 个在途 payout 的 5 笔扣款作为不应处理的反例，其发票状态由 P10 检查。

## 主要约束（≥4 类）

1. **对象筛选与时间窗口**：只对账“已到账且未记账”的 payout。
   - po_1Q1yO5…（11/3）与 po_1QTtOT…（11/6）已有手续费 expense，且对应发票已收款。
   - po_1QGiTQ…（11/16）在 Stripe 上为 in_transit，QuickBooks 银行流水里也没有这笔入账；Stripe 邮件写着预计 11/16 到账。
2. **跨站字段对应**：CSV 只有 payment_intent_id 和付款人邮箱，发票号只能在 Stripe 的描述或 metadata 中找到，余额只能在 QuickBooks 中看到。
   - Stripe 客户名或邮箱与 QuickBooks 客户记录不同：Marlowe Finch、Odessa Park，以及 Harbor & Pine 的 Marta Ostrowski。
3. **金额核算**：
   - 尾款与 Partial 发票的未付余额比较：1154、1157、1160。
   - 合并付款需拆分到各张发票：4,300 = 1178 + 1182；4,350 = 1191 + 1198。
   - 分笔付款需合计：1,000 + 860 = 1179。
   - 少付金额需精确算出：1176 欠 250.00，1195 欠 240.00。
   - 手续费 = 该 payout 在 CSV 中 fee 的合计：po_B 为 1,218.91，po_C 为 1,179.91。
4. **以较新信息为准**：
   - Juniper 的 Dana 来信把付款对应的发票从 1192 更正为 1197。
   - Nadia 来信说 Calder 的 $85 差额不收。
   - Nadia 说过“今晚我来退款”，但 Stripe 上 Wren 并没有退款记录，需要以 Stripe 为准。
5. **重复处理**：Brightwater 的重复扣款已于 11/6 退款，退款行在 CSV 中，不应再退。Atlas 描述里写的 1158 在 10 月已付清，实际应付的是 1193，不是重复付款。
6. **交付格式**：本地 CSV 的列名、payout ID、分号连接的发票号和四种 action 取值均固定。
7. **保护非目标数据**：
   - 在途 payout 对应的发票不动。
   - Stripe 付款失败的 1213、尚在 pending 的 1214 不动。
   - 近似重名客户的 1184、被误引用的 1192、同一客户的另一张发票 1199 不动。
   - 不向已付清或豁免的客户催款。

## 陷阱一览

| 陷阱 | 粗心做法 | 正确依据 |
|---|---|---|
| 在途 payout | 把 CSV 里 5 个 payout 全部对账 | Stripe payout status、银行流水、Stripe 邮件 |
| 已记账 payout | 重复记 11/3、11/6 两个 payout 的手续费 | 已有的 expense 描述里含 payout ID |
| 尾款 | 3,600 对比 7,200 总额，当作少付 | 发票状态为 Partial，查看 Balance Due |
| 合并付款（metadata） | 只收 1191 | Stripe 付款 metadata 里 invoice_numbers=1191,1198，金额也对得上 |
| 分笔付款 | 两笔都当作少付 | 同一客户同日两笔合计等于发票总额 |
| 错误发票号 | 把 Atlas 的付款当作重复付款退款 | 1158 在 10 月已付清，1193 金额正好吻合 |
| 客户更正 | 当作 1192 的少付并催款 | Dana 11/11 的邮件 |
| 老板豁免 | 向 Calder 催 $85 | Nadia 11/13 的邮件 |
| 邮件说已退款但实际未退 | 跳过 Wren 退款 | Stripe 上无退款记录 |
| 已退款 | Brightwater 再退一次 | Stripe 付款已显示 Refunded，CSV 中也有 refund 行 |
| 近似重名客户 | 把 1,800 记到 Marlow & Finch Legal 的 1184 | Stripe 邮箱 hello@marlowefinch.com 对应 Marlowe Finch Design |
| 账单地址 | 催款发到 m.ostrowski@gmail.com | QuickBooks 客户记录上的邮箱是 accounts@harborpine.com |

## 浏览器的必要性

以下操作都只能通过页面完成：

- QuickBooks 的收款、新建 expense，以及查看发票余额；
- Stripe 的付款描述与 metadata 查看、退款（弹窗里输入金额）；
- Gmail 的读信和发信。

模型通过 task.toml 声明的浏览器 MCP 工具操作，看不到 DOM、站点接口或状态文件。本地 CSV 是唯一能把 payment_intent_id 归到 payout 的来源，手续费合计也要在 CLI 中计算；结果文件同样由 CLI 写出，因此与网页操作之间是真实的数据依赖。

## 环境复现

- 与参考题相同：Playwright 基础镜像，sitehost 统一提供三站，浏览器启动时为三站各开一个标签页，每个 trial 从种子重新初始化。
- 时钟：页面内的 `Date` 固定为 2026-11-16 09:30（America/New_York），并实时前进。
- 数据生成：`world.py` 确定性生成（`factory/.venv/bin/python world.py <out>`），所有 ID 都由固定种子哈希得到；头像使用 worldkit 的离线 `avatar()`。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读，模型以 `agent` 用户运行。
- sitehost 只接受带密钥头的请求。
- 参考解通过 `/__oracle/apply` 写入 golden 状态。

## 评分方式

详见 `rubric.json`：共 19 个程序化检查点，权重合计 100，按加权部分分计。

- 保护性检查各自查看相关违规。空操作时各项均得 0。
- 1180 和 1196 的收款结果由 P1 检查，退款结果由 S1 和 S2 检查。

隐藏真值见 `expected.json`：逐项付款、payout 角色、手续费金额、少付邮箱与金额、可接受的退款对象。

## 自测与证据

| 夹具 | 预期得分 | 说明 |
|---|---|---|
| golden | 1.0 | |
| nop | 0.0 | |
| naive | 0.4476 | |
| slip_in_transit | 0.9283 | |
| slip_deposits | 0.8997 | |
| slip_wren_refund | 0.9366 | |

UI 写操作探针（`ui_probe.py`，打包后容器内实测，均已落到服务端状态）：

- Stripe：在付款详情页点 Refund，输入 2640.00，确认后 `refunds` 新增 264000 美分记录，付款 `amount_refunded=264000`、`refunded=true`。
- QuickBooks：发票列表行内的 “Receive payment” 和发票详情弹窗里的 “Receive Payment” 均可用，结果为 `status=Paid`、`paidAmount=total`、`paidDate=2026-11-16`；连续 6 次点击全部落盘。
- QuickBooks：Expenses → New transaction → Expense。Vendor 和 Category 是原生下拉框，需要键盘选择。保存后生成 `{payee:'Stripe', vendorId:'v_stripe', category:'Miscellaneous', amount:1218.91, description 含 payout ID, type:'Expense'}`；date 默认为今天。
- Gmail：Compose 后发送，`folder=sent`，`to=[{email}]`，正文为 HTML 并附带 mock 固定签名。

探针中发现并修复了一个运行时缺陷：QuickBooks mock 用 `fetch(..., {keepalive:true})` 回传整份状态，而在 browserd 的请求拦截下，Chromium 不会释放 keepalive 的 64 KiB 额度，导致每次页面加载后累计约 64 KiB 的回传之后，所有写入都会静默丢失（本题 QuickBooks 状态约 60 KB，加载后的第一次写入就会丢失）。修复方式是在 `factory/runtime/sitehost/sitehost.py` 的 boot 脚本中把页面 fetch 的 keepalive 置为 false。修复后已重新打包验证；workday_mock 也受益于这一修复。
