# 任务说明：照去年的做法订团聚房间（reunion-rooms-like-last-year）

- **任务标识与版本**：`cua-hard/reunion-rooms-like-last-year`，v0.1.0（exp2 杠杆批次，主杠杆 L16 隐含意图）。
- **场景**：生活消费 / 家庭年度聚会订房与费用分摊。Sacramento 的 Dana Whitfield 每年替 Whitfield 家订冬季团聚的住处。2026 年仍是 Lake Tahoe 的 Lakeview Pines Lodge，12/27–12/30。妈妈只说了一句“rooms like last year”，Mark 也回“去年怎么做就怎么做”。
- **涉及站点**：Booking.com（主站点，订房；历史预订含 2024 Big Bear、2025 Tahoe、已取消的 Queen 房、9 月姐妹周末）、PayPal（历年请款与收款）、Google Calendar（历年团聚与去年的取消提醒）、Yahoo Mail（确认/取消邮件、分摊讨论、妈妈的房间要求、Leah 换邮箱、小屋新退改政策、去年的 “rooms are booked” 邮件），外加本地 RSVP 导出与本地交付文件。
- **输入**：四站初始数据（root-only 种子）。`/workspace/input/reunion_rsvp_2026.csv` 共 7 行，列 submitted_at,name,email,household,attending,arrive,depart,adults,children,notes；其中 Leah 有两行（后一行改为 12/28 到），Jake 不需要房间，Ruth 不来。
- **输出**：Booking.com 4 个新预订；PayPal 2 条请款；Google Calendar 1 个提醒事件；Yahoo Mail 1 封家庭通知邮件；`/workspace/output/reunion_2026.csv`（4 行）。

## 主杠杆：L16 隐含意图

指令只说“像去年那样”，没有给出房型、价格方案、分摊规则或提醒日期。唯一与所有记录一致的读法如下，附近都设了干扰历史：

| 维度 | 从去年记录推出的做法 | 依据 | 干扰历史 / 错误读法 |
|---|---|---|---|
| 房型 | Dana Family Room、Mark Two-Bedroom Lakeside Cabin、Leah King Room with Lake View、父母 Accessible Queen Room – Ground Floor | 2025 年 4 个 completed 预订、“Tahoe rooms are booked!”邮件 | 2024 Big Bear 的房型；名称相近的 Two-Bedroom Forest Cabin；Lakeview Pines Resort & Spa |
| 退改条款 | 全部订灵活价（Free cancellation） | 2025 年确认邮件写着 “Free cancellation until 13 December 2025”；2025 年 1 月 Leah 要求“以后只订可免费取消的” | 2024 年全订不可退款价；9 月姐妹周末在同一家小屋订了不可退款的 Double Room（最近一次）；每种房型的不可退款行都排在前面且更便宜 |
| 父母的房间 | 无障碍一楼房，特殊要求写一楼/靠大堂/拐杖 | 2025-11-04 妈妈邮件（二楼无电梯）；最终预订带 special request | 2025-11-03 先订后取消的 Queen Room – Second Floor（Trips 的 Cancelled 页签与取消邮件） |
| 分摊 | 各户付自己的房间，Dana、Mark、Leah 三人平摊父母房 | 2025 年 PayPal 只向 Mark 请 $1,360、向 Leah 请 $790：1360−1185 = 790−615 = 175 = 525/3 | 2024 年按人头 $204（备注写明，也向妈妈请款）；1 月线程中 Leah 提议 Dana 免单、父母房两人平分；照抄去年金额 |
| 提醒 | 免费取消截止的前一天 | 2025-12-12 的 “Reunion rooms: free cancellation ends tomorrow”，对应截止日 12-13 | 今年截止日改为 12-20（10/3 小屋邮件：入住前 7 天；结账页显示），照抄 12-12 会错 |
| 通知邮件 | 发给妈妈、Mark、Leah，列出各房确认号 | 2025-11-06 已发邮件 | Leah 旧地址 leah@ortizdesign.co（去年收件人、联系人卡片仍是旧地址）；2026-08-19 她已改用 Gmail，PayPal 也一样 |

这些维度决定 B1–B5、P1、P2、C1、M1，合计 72 分。P1/P2 的金额同时依赖房型、退改价、Leah 的日期和分摊规则，任何一环错都会拿不到。

## 主要约束（≥4 类）

1. **跨站字段匹配**：房型、退改价和客人姓名来自 Booking.com 历史预订与 Yahoo 确认邮件；分摊规则只在 PayPal 金额里；提醒提前量只在日历里；Leah 的新地址在 Yahoo 与 PayPal。
2. **更正 / 后续信息**：Leah 的 RSVP 后一行改为 12/28 到；妈妈的邮件推翻了先订的 Queen 房；Leah 换了邮箱；小屋改了退改政策。
3. **金额计算**：今年税费为每晚 $28，Dana 819、Mark 1269、Leah 434（2 晚）、父母 579。请款 Mark 1269+193=1462，Leah 434+193=627；Dana 自己承担 1012。
4. **时间窗口**：只订 12/27–12/30（Leah 12/28–12/30）；提醒日期为 2026-12-19（浏览器本地 = UTC）。
5. **对象筛选 / 保护非目标**：Jake（住朋友家）与 Ruth（不来）不订房；不向父母、Jake、Chris 请款；不动 2027 年 1 月 Coronado 等历史预订；不误订 Lakeview Pines Resort & Spa。
6. **交付格式**：CSV 列 guest_name,room,check_in,check_out,confirmation_number,total,requested；确认号须与状态中的新预订一致。

## 期望结果

| 户 | 房间（roomId） | 日期 | 客人 / 邮箱 | grandTotal | PayPal 请款 |
|---|---|---|---|---|---|
| Dana | Family Room 灵活价（room_1_9） | 12/27–12/30 | Dana Whitfield / dana.whitfield@yahoo.com | 819 | — |
| Mark | Two-Bedroom Lakeside Cabin 灵活价（room_1_12） | 12/27–12/30 | Mark Whitfield / mark.whitfield@gmail.com | 1269 | 1462.00 → mark.whitfield@gmail.com |
| Leah | King Room with Lake View 灵活价（room_1_5） | 12/28–12/30 | Leah Whitfield-Ortiz / leah.whitfield.ortiz@gmail.com | 434 | 627.00 → leah.whitfield.ortiz@gmail.com |
| 父母 | Accessible Queen Room – Ground Floor 灵活价（room_1_3），带一楼/大堂/拐杖特殊要求 | 12/27–12/30 | Carol Whitfield / carol.whitfield@sbcglobal.net | 579 | — |

日历：新事件，UTC（浏览器本地）日期 2026-12-19，标题或描述含 “cancel”。邮件：发给 carol.whitfield@sbcglobal.net、mark.whitfield@gmail.com、leah.whitfield.ortiz@gmail.com，正文含 4 个新确认号。

## 网站必要性

- Booking.com：唯一能下单的地方；历史预订（含已取消的那条）给出房型、灵活价和父母的特殊要求；结账页给出今年的免费取消截止日。
- PayPal：分摊规则只能从 2025 年的请款金额倒推；请款也在这里发出；联系人里新旧两个 Leah 地址并存。
- Google Calendar：只有去年的提醒事件说明了“截止前一天”这个提前量；今年的提醒写在这里。
- Yahoo Mail：妈妈换房的理由、分摊讨论、Leah 换邮箱、小屋新政策和去年的通知邮件都只在邮件里；今年的通知从这里发。
- CLI：RSVP 导出只在本地 CSV 中，决定 Leah 的日期以及 Jake、Ruth 不订房；汇总 CSV 由 CLI 写出。

## 环境复现

- 单容器多站运行时：sitehost + 浏览器守护进程，启动时四站各开一个标签页。
- 时钟固定为 2026-11-18 18:30 UTC 并实时前进；浏览器时区为 UTC。原因：Booking.com mock 的 My Trips 和 Confirmation 页用 new Date("YYYY-MM-DD") 显示日期，在 UTC 以西的时区（如 America/Los_Angeles）会显示成前一天（ui_probe 实测 12/27–12/30 显示为 Dec 26–Dec 29），可能诱使模型取消并重订正确的预订。用 UTC 之后，所有站点的日期显示都正确，日历编辑弹窗的时区偏移问题也随之消失。人物仍住在 Sacramento，指令不涉及时区。
- Booking.com 物业详情页无法修改成人/儿童/房间数（固定 2 成人、1 间），所以历史预订也统一为 2 成人、1 间，评分不检查人数。
- PayPal mock 加载种子时会规范化交易字段（丢弃 recipientEmail/senderEmail），所以种子交易只用规范化后保留的字段；UI 新建请求时 recipientName 写入的是联系人邮箱。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行，无法直接读状态或种子。
- sitehost 只接受带随机密钥头的请求；参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：13 个程序化检查点，加权部分分，权重合计 100；不标 core，不调用 gate/cap。“不应多做”类（B6、P3）以完成相关工作为前提，空操作为 0。

夹具预期：golden=1.0、nop=0.0、naive≈0.17、slip_rsvp≈0.76、slip_split≈0.69、slip_old_email≈0.88、slip_parents_room≈0.57、slip_reminder≈0.92。

## 自测与证据

- 已完成：world.py 确定性生成；本地参考打分模拟验证夹具区间（golden 1.000、nop 0.000、naive 0.171、slip_rsvp 0.755、slip_split 0.690、slip_old_email 0.881、slip_parents_room 0.565、slip_reminder 0.920）。
- UI 探针（ui_probe，打包草稿 + 浏览器实操，四类写入都已在服务端状态中确认）：
  - Booking.com：在 Lakeview Pines Lodge 选择 2026-12-27→12-30，预订 Accessible Queen Room – Ground Floor 的可免费取消行，编辑住客姓名、邮箱和特殊要求后完成预订。状态中新增 booking：roomId=room_1_3，grandTotal=579，guestFirstName/LastName=Carol/Whitfield，specialRequests 为输入文本，freeCancellation=true，cancellationDeadline=2026-12-20。结账页显示 “Free cancellation until 2026-12-20”。
  - PayPal：在 /send?mode=request 选择 Mark Whitfield 联系人，金额 1462，备注后提交。transactions 头部新增 {type: request_sent, amount: 1462, recipientName: "mark.whitfield@gmail.com", status: pending, description: 备注}。
  - Google Calendar：Create 弹窗输入标题、开始 12/19/2026 09:00 AM、结束 09:15 AM（年份字段可输入 6 位，需要 Tab 切到时间段）、描述后保存。events 新增 start=2026-12-19T09:00:00.000Z，calendarId=c1。
  - Yahoo Mail：Compose 的 To 栏连续输入三个地址（逗号成 chip），填写主题和正文后 Send。messages 新增 folderId=sent，to=[carol, mark, leah 新邮箱]。
  - 探针中发现 “Family trips” 日历的 bg-orange-500 类没有被 Tailwind 编译，复选框显示为未勾选。已改为 bg-red-600，这个类在源码中存在。
- 待完成：独立 verifier 编写与 selfcheck、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
