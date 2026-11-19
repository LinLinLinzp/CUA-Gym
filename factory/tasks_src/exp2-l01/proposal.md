# 任务说明：Q4 续约结单（q4-renewal-closeout）

- **任务标识与版本**：`cua-hard/q4-renewal-closeout`，v0.1.1（实验批 exp2，槽位 exp2-l01）。
- **场景**：产业运营 / 客户续约结单。数据分析 SaaS 公司 Acme Analytics（伦敦）的高级客户经理 Sarah Chen 在巴塞罗那参加 EMEA 销售大会，委托代理人在财务锁账前结清她名下的 Q4（FY27）续约。
- **涉及站点**：Salesforce（续约商机的阶段/金额/关单日）、DocuSign（续约订单表信封：是否完全执行、执行的是哪个报价版本、归档与作废）、Yahoo Mail（Elena 的结单清单及 Marcus 的修订回复、客户来信约时间/改期/不续约）、Google Calendar（已有日程与新建 kickoff 会议），外加本地 CPQ 导出 CSV（每个报价版本的年费与合同总额）与本地交付 CSV。四站均为新建 hub mock，以真实域名离线提供。
- **输入**：四站初始数据；`/workspace/input/cpq_quotes.csv`（22 行，含 Q-2291 的 v1/v2/v3 三个版本）。
- **输出**：Salesforce 5 个商机的阶段/金额/关单日；DocuSign 4 个信封归档、1 个信封作废；Google Calendar 4 个 kickoff 事件；`/workspace/output/q4_renewals.csv`（9 行）。
- **时钟**：2026-12-14（周一）09:15，Europe/London（12 月英国时间 = UTC，避免 Salesforce 日期显示在美洲时区的错位）。

## 正确结果

| 商机 | 结果 | 依据 |
|---|---|---|
| Northwind Logistics | Closed Won，88800，2026-12-09；会议 12/16 10:00–10:45，Dana + Marcus | env_402（Q-2291 v2，36 个月）12/9 完成；v1 已作废、v3 仅草稿；周二 14:00 与 Forecast review 冲突 |
| Bluepeak Health | Closed Won，57600，2026-12-10；会议 12/17 15:00–15:45，Jordan | Q-2307 年费 57600（SF 现值 54000）；客户写 10:00 am Eastern |
| Harbor Freightways | 不动，不建会，不归档 | env_404 仅客户签（状态 Signed），Marcus 邮件说暂缓会签 |
| Cobalt Retail Group | Closed Lost，41000，2026-12-11；作废 env_405（原因 Customer not renewing） | CFO 12/11 书面不续约取代 11/23 的“发文件”邮件 |
| Summit Dental Group | Closed Won，27600，2026-12-08；会议 12/21 13:30–14:15，Megan | 12/11 改期邮件取代已确认的周五 18 日 |
| Summit Dental Partners | 不动 | 近似实体，信封仍未签（MD 21 日回来再签） |
| Pinecrest Software | 不动，不重复建会 | 早已 Closed Won、已归档、kickoff 已在日历 |
| Lakeside Credit Union | Closed Won，63000，2026-12-11；会议 12/17 11:00–11:45，Aoife + Marcus | 24 个月，年费 63000 / TCV 126000；周三 15:00 与 Halcyon QBR 冲突 |
| Driftwood Hotels | 不动（10 月已 Closed Lost），仅列入 CSV | 已处理项 |

## 主要约束（≥4 类）

1. **对象筛选**：只处理 Sarah 名下、type=Renewal、关单日在 2026 Q4 的商机；排除 FY26 同名续约、Ferro（2027-01）、Northwind 加购与其他销售的商机。
2. **权限 / 状态**：仅 Completed（客户签 + Marcus 会签）的信封才能 Closed Won；Harbor 只有客户签。
3. **金额计算**：从信封文件名取报价号和版本，在本地 CPQ 导出里查年费；多年期记年费不记 TCV。
4. **跨站字段对应**：信封 → 报价版本（文件名）→ CPQ 行；邮件中的客户 → 商机 → 会议邀请邮箱。
5. **时间窗口 / 时区**：关单日 = 信封完成的英国日期；Bluepeak 的美东时间须换算；Cobalt 关单日 = 不续约邮件日期。
6. **版本冲突**：Marcus 的回复把会议改为 45 分钟并在年费 ≥ 6 万美元时加他；Megan 改期；Hannah 的邮件被 CFO 取代；Northwind v1 作废、v3 草稿。
7. **重复处理 / 保护非目标**：Pinecrest 已完结不重复建会；Harbor、Summit Dental Partners、Ferro 及其他信封不得改动；不在已有日程上叠会。
8. **交付格式**：CSV 表头、整数金额、YYYY-MM-DD、英国时间 HH:MM。

## 陷阱（≥3）

- Harbor：DocuSign 显示 “Signed”、客户邮件主动约会，看似已成交，实则未会签（C6、K1、M5）。
- Northwind：两封同主题信封，作废的 v1 与 SF 现值一致，CPQ 还有更新的 v3 草稿（C1）。
- Lakeside：多年期 TCV 126000 与年费 63000（C4）。
- Cobalt：先“发文件”后正式不续约（C5、K2）。
- Summit Dental Group / Partners 近似实体（C3、C6）。
- Bluepeak 美东时间、Summit 改期、Northwind/Lakeside 的日程冲突、Marcus 的修订（M1–M4）。

## 浏览器的必要性

商机编辑（阶段路径点选、行内编辑金额与日期）、信封批量移动文件夹与作废、新建日历事件并添加来宾都只能通过页面完成；邮件只读但规则与客户约定只存在于邮件中。本地 CPQ CSV 是金额的唯一来源（DocuSign 详情页不显示字段值），形成真实的 CLI 依赖。

## 评分方式

`rubric.json` 定义 15 个独立检查点，按权重汇总。三项保护性检查各自查看相关违规，空操作得 0。

## 自测与证据

- 夹具自测分数为 golden 1.0、nop 0.0、naive 0.2867、slip_timezone / slip_reschedule / slip_conflict 0.9311、slip_amendment 0.9100、slip_harbor 0.8911、slip_tcv 0.9111。
- UI 探针（ui_probe，Europe/London）：Salesforce 编辑弹窗改 stage/amount/closeDate → 状态 `closeDate='2026-12-09'`、页面显示 Dec 9；DocuSign 批量“Move to Folder” → `folderId=folder_fy27` + MOVE_ENVELOPE 审计；详情页 Void 填原因 → `status=voided`、history 含 “Envelope voided: Customer not renewing”；Calendar 新建事件（日期时间输入需逐段输入）→ `start=2026-12-16T10:00:00.000Z`、`end=10:45Z`、guests 两人，与 golden 形状一致。注意：Agreements 的 “Void Selected” 批量作废原因固定为 “Bulk void”，K2 只得 0.6。
