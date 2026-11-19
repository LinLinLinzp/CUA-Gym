# 任务说明：探望父亲的 Airbnb 月度分摊结算（dad-visits-airbnb-settlement）

- **任务标识与版本**：`cua-hard/dad-visits-airbnb-settlement`，v0.1.0（exp1 杠杆批次，slot `exp1-l07`，主杠杆 L07 可重算脚本）。
- **场景**：生活消费 / 家庭开支分摊。Emily Carter 和哥哥 James、妹妹 Megan 轮流飞到 Asheville 探望髋关节术后在康复中心的父亲 Walter。民宿大多用 Emily 的 Airbnb 账号订，每月在 Google 表格里结算一次。现在要结 10 月；James 12 月起接手订房，要一个每月能自己重跑的结算脚本。
- **改编说明**：原 premise 是房东的 co-host 与业主结算，但 Airbnb mock 只有房客端（没有房东后台和 payout），因此改为房客侧的家庭分摊。主站 Airbnb 的行程、收据、改期和取消记录仍是事实来源。
- **涉及站点**：Airbnb（行程、收据、改期/取消与退款，只读）、Google Sheets（“Dad visits - Asheville stays”工作簿：Bookings / Settlement / Notes）、Gmail（分摊规则线程及其 10 月修订、James 自订行程的收据与更新收据、Megan 的漏登提醒、James 的接手请求）。另有 CLI 交付：`/workspace/output/settle.py`、`bookings.csv`、`settlement_2026-10.csv`。
- **输入**：三站初始数据；无 `/workspace/input` 文件（Bookings 导出须由 agent 根据表格自行整理）。
- **输出**：Sheets 中 Bookings 工作表的修正与 Settlement 的 10 月三行、Gmail 发给 James 和 Megan 的结算邮件（两个站点持久化）；本地三个文件。

## 主要约束（≥4 类）

1. **对象筛选/时间窗口**：按入住月份归属；9/29–10/2 属于 9 月；O5 由 10/31 改到 11/1 后移出 10 月；脚本需正确处理 11/30、12/30–1/2、1/1 等边界。
2. **跨站字段对应**：表格行（确认码）↔ Airbnb 行程/收据 ↔ James 邮件中的收据；Megan 提到的漏登行程只能在 Airbnb 找到金额。
3. **金额计算**：net = total − refund；付款人承担服务费；10 月起清洁费三人均摊；取消行只分摊未退回部分；全额退款为 0（max(0,·) 下限）；四舍五入到分。
4. **版本更正/生效日**：分摊规则的 10 月修订只在 Gmail 线程回复中，且“从 10 月入住开始、8/9 月不重算”；Notes 工作表仍是旧规则。James 10/28 的更新收据取代 10/20 的报价。
5. **状态**：O1 在表中为 confirmed，实际 10/6 已取消并部分退款；O2 已改期缩短。
6. **保护非目标**：Emily 与伴侣 Sam 的私人行程（10/2–10/4，以及被房东取消的 Catskills 行程）不得进表；8、9 月已结算行与 Settlement 历史行不得改动。
7. **交付格式与接口**：脚本环境变量 BOOKINGS_CSV / MONTH / OUT_CSV，输出表头 person,share,paid,balance，非法输入退出码 2 且不写文件。

## 陷阱（≥3）

- 规则修订藏在邮件线程回复里（清洁费均摊）且带生效日 → 影响 R1–R4、C1、S6、E1。
- O1 已取消（部分退款 367.38），表中仍为 confirmed。
- O2 缩短为 3 晚，表中仍是原日期，收据金额已变。
- O3 漏登（Megan 邮件），同月私人行程为近似的非目标。
- O4 为 James 的报价收据，随后被更新收据取代。
- O5 改期到 11/1，不再属于 10 月。
- 脚本层：全额退款取消的负值下限、人名校验、9 月旧规则。

## 主杠杆 L07 的落点

R1–R6 共 52 分，是 verifier 用 `cuaverify.run_replay` 以 agent 用户在 6 组隐藏输入上重跑 `settle.py` 的结果：10 月 golden、9 月旧规则、11 月混合（全额退款取消、Megan 付款、跨月行）、12 月边界（跨年）、非法人名（期望退出码 2）、空月份。另有 C1（9 分）要求本地 10 月结果与同一规则一致。只把 10 月数字手算对、脚本泛化不了的 agent 拿不到这一大半分数。

## 浏览器的必要性

行程状态、改期、退款金额只能在 Airbnb 页面（Trips、行程详情、收据页）看到；规则修订、James 的收据和 Megan 的提醒在 Gmail；表格修改与追加行、发送邮件都要通过页面完成。Sheets 没有 CSV 下载，bookings.csv 需要 agent 依据页面内容整理，脚本由 CLI 编写、调试。

## 环境复现

- 同工厂通用镜像与 sitehost；时钟固定为 2026-11-18 09:00（America/Los_Angeles）并实时前进。
- 每个 trial 是新容器，从种子重新初始化。

## 评分方式

见 `rubric.json`：16 个程序化检查点，加权部分分；P1 以 10 月工作确实完成为前提，空操作得 0。夹具预期：golden=1.0、nop=0.0、naive≈0.18、slip_floor≈0.90、slip_validation≈0.92、slip_effective_date≈0.91、slip_moved_stay≈0.75、slip_james_quote≈0.90。

## 自测与证据

- world.py 在生成时用子进程运行参考 settle.py，断言其在全部 6 组隐藏输入上与参考规则一致。
- 已完成 ui_probe：Sheets 双击单元格编辑、新增行（Bookings 与 Settlement，日期与 2026-10 保持字符串）、Gmail 撰写并发送给两人，均落入服务端状态；Airbnb 收据页可见改期后金额与退款。注意：Sheets 选中单元格后直接打字不会进入编辑，需要双击、F2 或编辑栏；Gmail 撰写窗口固定插入 Demo User 签名（hub 小问题，不影响评分）。
- 待完成：verifier 编写与 package 自测、平台 Qwen×5 / Opus×2 评测。
