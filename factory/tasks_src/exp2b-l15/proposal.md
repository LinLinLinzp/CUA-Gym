# 任务说明：Ember 系列上线日状态核查（ember-launch-status-audit）

- **任务标识与版本**：`cua-hard/ember-launch-status-audit`，v0.1.0（exp2b 杠杆实验题，主杠杆 L15 状态错觉）。
- **场景**：产业运营 / 电商新品上线核查。Portland 家居品牌 Hearth & Hollow 的电商经理 Nadia Okafor 在 Ember 冬季系列上线当天上午（2026-11-18 周三 10:30 PT，上线时间 08:00 PT）核查“到底什么是真的上线了”。
- **涉及站点**：Shopify 后台（商品 / 折扣 / 博文的真实状态与修复）、Yahoo Mail（Nadia 的邮箱：Theo 的“已完成”邮件、经销商改址通知、仍躺在 Drafts 的经销商上线通知）、Slack（#ember-launch 置顶清单及线程里的 QA 撤下决定、团队“已上线”的说法、状态汇报）。tool_type=2：本地 `/workspace/input/ember_launch_sheet.csv`（上线清单，含 SKU/折扣码/博文 handle、上线与结束日期）→ 输出 `/workspace/output/launch_audit.csv`。
- **输出**：Shopify 状态修复、Yahoo 已发送的经销商通知、Slack 状态消息（服务端持久化）；本地核查表 CSV。

## 主杠杆 L15：状态错觉（lever 检查点合计 76 权重）

清单 11 项，团队口径“全部上线”，真实状态如下：

| ref | 团队/邮件声称 | Shopify 真实（初始） | 正确处理 | 最终 live |
|---|---|---|---|---|
| EMB-CND-CED | live | active | 不动 | yes |
| EMB-CND-FIG | live（Theo 邮件、草稿通知） | draft | **不动**（线程里 QA 撤下） | no |
| EMB-CND-AMB | live | draft | 改 active | yes |
| EMB-THR-RST | live | active | 不动 | yes |
| EMB-THR-CHR | live | archived（Theo 清理旧商品时误归档；近似常规款 HH-THR-CHR 为 active） | 改 active | yes |
| EMB-MUG-SET | live | active | 不动 | yes |
| EMB-GFT-BOX | “隐藏到 12/1” | active（被批量上架） | 改 draft | no |
| EMBER15 | “is up” | scheduled，开始日误设 Nov 25 | Activate | yes |
| EMBERSHIP | live | active | 不动 | yes |
| EMBERVIP | “今天还在用” | expired（11/17 结束，符合清单） | **不动** | no |
| meet-the-ember-collection（博文） | “Blog post is up” | Draft（已保存未发布） | 发布 | yes |

另外：经销商通知其实一直在 Yahoo **Drafts** 中（Sent 里只有 11/10 的预告邮件），Nadia 自己在 Slack 说过“going out tonight”。

## 其它约束（≥4 类）

1. **对象筛选**：只处理清单 11 项；Ember 系列与常规款并存（同名近似的 Charcoal 毯、Cedarwood 蜡烛、已发布的 Ember 预告博文、同为 scheduled 的 BLACKFRIDAY26、已过期的 EMBERSTAFF）。
2. **跨站字段对应**：清单 SKU ↔ Shopify 商品详情中的变体 SKU（列表页不显示 SKU）；折扣码 ↔ 折扣列表；博文 handle ↔ 博文。
3. **时间窗口**：上线日期（礼盒 12/1 未到）、折扣起止（EMBERVIP 11/17 结束、EMBER15 应 11/18–11/30）。
4. **版本冲突 / 更正信息**：QA 撤下 Fig & Clove 只在置顶清单的线程回复里（清单未更新、草稿通知未更新）；Ashby & Co 改名 Ashby Home 并更换采购邮箱（Stockists 文件夹中的邮件），草稿与通讯录仍是旧地址。
5. **状态/已处理项**：draft vs sent、scheduled vs active、saved vs published、archived vs active；已真正上线的项目不应被改动。
6. **保护非目标**：常规款商品、其它折扣、其它博文保持原状；不重复发送通知。
7. **交付格式**：Slack 每项一行 `<ref>: live|not live`；CSV 列 ref,found_status,fixed_to,live。

## 陷阱（≥3）

- 线程回复里的 QA 撤下（Fig & Clove 不得上架，也不得出现在通知里）。
- 近似重名商品（Wool Throw – Charcoal 常规款 active vs Ember 款 archived）。
- 只在第二来源的事实：礼盒 12/1 上线日期与 EMBERVIP 结束日期在本地清单；Ashby 新地址在邮件里。
- 看似已处理：Sent 中的预告邮件、已发布的预告博文、Slack 里的“we're live”。
- 看似需修正的非目标：BLACKFRIDAY26（scheduled）、EMBERVIP（expired）。

## 浏览器的必要性

三站的状态都只能在页面上看到（Shopify 的 SKU 在商品详情、折扣状态在折扣列表、博文状态在博文列表；Yahoo 草稿与已发送分处文件夹）；修复（商品状态下拉或批量操作、折扣 Activate、博文发布开关）、编辑并发送草稿、在 Slack 发消息都必须通过 UI 完成。本地清单与核查表由 CLI 处理，清单决定了哪些项该上线、哪些不该。

## 评分方式

见 `rubric.json`：14 个程序化检查点，加权部分分；“保持原状”类检查以完成对应修复为前提，空操作得 0。Slack 行与 CSV 行除了与期望值一致，还要求与最终真实状态一致（只报不修不得分）。夹具预期：golden=1.0、nop=0.0、naive≈0.17、slip_fig≈0.83、slip_charcoal≈0.90、slip_address≈0.94、slip_giftbox≈0.90。

## 环境与时钟

- 时钟：页面内 `Date` 固定为 2026-11-18 10:30（America/Los_Angeles）并实时前进；Shopify 的折扣状态为存储字段，不随时间自动变化。
- 种子：Shopify 30 个商品（7 个 Ember + 23 个常规款）、19 个订单（含上线当天 6 单）、9 个折扣、5 篇博文；Yahoo 19 封邮件（含 2 封草稿）；Slack 4 个频道、置顶清单及 4 条线程回复。
