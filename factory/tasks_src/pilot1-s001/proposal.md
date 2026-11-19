# 任务说明：旅居伦敦的生日礼物代购（birthday-gifts-abroad）

- **任务标识与版本**：`cua-hard/birthday-gifts-abroad`，v0.1.0（pilot1-s001）。
- **场景**：生活消费 / 跨国家庭礼物代购与日程。住在伦敦的美国人 Emily Carter 委托助手，在 amazon.com 上把今年剩余的家人生日礼物直接寄给美国各地的亲戚，并在自己的 Google 日历上按对方当地时间建好生日通话提醒。
- **涉及站点**：Amazon（商品、地址簿、支付方式、购物车/稍后再买、订单）、Google Calendar（Birthdays 日历、搬家暖房事件、已有通话提醒），外加本地礼物清单 CSV 与本地交付文件。两站均为 CUA-Gym-Hub mock，已还原真实品牌，在容器内以真实域名离线提供。
- **输入**：两站初始数据（root-only 种子）；`/workspace/input/gift_list.csv`（收件人、首选 ASIN、每件最高价、备选 ASIN、寄送对象描述、备注；不含生日和具体地址）。
- **输出**：Amazon 新订单（商品、数量、收件地址、付款卡）、购物车/稍后再买状态、Google 日历新事件等服务端持久化状态；`/workspace/output/birthday_gifts.csv`。

## 主要约束（≥4 类）

1. **对象筛选 + 时间窗口**：只处理清单中生日落在 2026-11-18 至 12-31 的人；生日只在日历 Birthdays 日历上（Tom 11/10 已过、Jess 1/1 窗口外；Hannah 在窗口内但不在清单上）。
2. **跨站字段对应**：清单里的 “Kate's place / Ben & Priya's / Grandma's condo / Mom & Dad's house” 要对应到 Amazon 地址簿；Kate 有新旧两个地址，新地址只在日历 “Kate's housewarming” 事件的地点和描述里。
3. **金额与数量**：最高价按每件计；Grandma 首选缺货、Dad 首选现价 99.95 超出 80（备注中的 79.95 是 9 月旧价）→ 改买备选；双胞胎一行需买同款 2 件。
4. **重复处理 / 已办项**：妈妈的礼物上周已下单（Shipped），Call Mom 提醒已存在，均不能重复；但 CSV 仍要列出妈妈的已有订单。
5. **权限与状态**：付款必须用个人 Visa 4417；默认卡是公司 Amex，另一张 Visa 2290 已过期。
6. **时区换算**：通话提醒为对方当地 19:00（丹佛 MST、波特兰 PST、萨拉索塔/哥伦布 EST），日历以伦敦时间显示，全部跨到伦敦的次日。
7. **保护非目标数据**：购物车里 Emily 自己的线缆和笔记本不能随礼物结账也不能删除；已有日历事件不能改动。
8. **交付格式**：CSV 列与订单号、ASIN、数量、两位小数金额需与真实订单一致。

## 陷阱一览

- 近似商品：黑色 Paperwhite（愿望单里、同价）、绿色 Signature 版、Kids 版；Aura Carver Mat（有货）；MEATER Plus（79.95，恰好低于上限但不在清单上）；T. rex & Atrociraptor 套装。
- 被更正的信息：Kate 搬家（暖房事件）；清单备注中的旧价格。
- 已处理项：妈妈的订单与 Call Mom；Tom 的订单与 Call Tom（窗口外）。
- 只在第二来源可见的事实：生日在日历上，地址在 Amazon 地址簿和日历事件里，价格/库存在商品页。
- 结账会把整个购物车下单（Buy Now 同样），需先把个人物品 Save for later。

## 浏览器的必要性

下单、选地址/卡、稍后再买、建日历事件都只能通过页面完成；模型通过浏览器 MCP 工具（截图 + 坐标/键盘）操作，看不到 DOM、站点接口或状态文件。题面不写工具用法。本地 CSV 与网页形成真实依赖：首选/备选 ASIN 与最高价只在 CSV 中，订单号只在网页上，结果需回写本地文件。

## 环境复现

- 基础镜像与 sitehost/browserd 运行时同参考题；每个 trial 新容器，从种子重新初始化。
- 时钟：页面内 `Date` 固定到 2026-11-18 10:15（Europe/London，此时 GMT = UTC）并实时前进；浏览器时区为 Europe/London，日历 datetime-local 输入按伦敦时间解释。
- 启动时为两个站点各开一个标签页。健康检查：`curl -fsS http://127.0.0.1:8079/health`。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行；sitehost 需随机密钥头，直接 curl 得 403。
- 参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：15 个程序化检查点（A1～A9 Amazon，B1～B5 日历，C1 CSV），加权部分分；“不得做”类检查（A6、A7、A9、B5）以完成对应工作为前提，空操作得 0。夹具预期：golden=1.0、nop=0.0、naive≈0.00、slip_kate_address≈0.93、slip_timezone≈0.73、slip_mom_duplicate≈0.86、slip_dad_budget≈0.89。

## 自测与证据

- 已完成：world.py 确定性生成；instruction 风格检查通过；ui_probe 实测 Amazon 稍后再买、非默认地址 + 非默认卡结账、日历按伦敦时间建 30 分钟事件均落入服务端状态。
- 待完成：verifier 编写后的 fixture 自测、本地 `harbor run -a oracle / -a nop`、平台评测。
