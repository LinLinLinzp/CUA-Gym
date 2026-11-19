# 任务说明：Larkspur MAP 表批量改价回传（larkspur-map-flatfile）

- **任务标识与版本**：`cua-hard/larkspur-map-flatfile`，v0.1.0（exp2 杠杆批次，槽位 exp2-l13，主杠杆 L13 文件往返）。
- **场景**：产业运营 / 多渠道卖家。明尼阿波利斯的厨房餐具店 Fernwood Table Co. 的联合创始人 Tessa Lindgren 委托完成供应商 Larkspur Pottery 2027 成本/MAP 表的上线：亚马逊批量改价改库存，同时调整自营 Shopify 店价格。
- **涉及站点**：Amazon Seller Central（主站：All Listings 报表下载、Price & Quantity 库存文件上传）、Yahoo Mail（供应商 MAP 表 v1 与更正版 rev2、合伙人 Rafael 的执行规则邮件）、Shopify 后台（主商品库与库存、变体价格修改）。三站各承担不可替代的信息或写入：MAP/MSRP/生效日只在邮件附件里，库存只在 Shopify，现价与 min/max 只在亚马逊报表，结果持久化在亚马逊（上传文件）和 Shopify（变体价格）。
- **输入**：三站初始数据（root-only 种子）；无 `/workspace/input` 文件，所有输入都需从站点下载到 `/workspace/downloads` 后在本地处理。
- **输出**：亚马逊上传的制表符分隔文件（服务端存储于 `/var/lib/cua/files/amazon_seller/<sid>/`，由 `inventoryFileUploads[]` 记录指向）、Shopify 变体价格；本地副本 `/workspace/output/larkspur_price_quantity.txt`。

## 主要约束（≥4 类）

1. **版本更正**：Owen Tate 11/16 的回复附带 `Larkspur_MAP_2027_rev2.csv`，声明“完全替代第一版”：花瓶 MAP 46→48、玻璃盖水瓶 34→36、烛台生效日 11/20→12/01、汤勺托标记 DISCONTINUED。
2. **时间窗口**：生效日 ≤ 2026-11-27（黑色星期五，含当日）的行本次切换，其余行沿用报表现值；LK-PLT-DIN4 恰为 11-27，LK-PCH-LG 为 11-28。
3. **金额计算**：price = max(MAP, 现价)（不得降价），min = MAP，max = MSRP；Shopify 只把本次生效且低于 MAP 的变体提到恰好 MAP。
4. **数量计算**：自发货行数量 = Shopify 库存 − 2，下限 0；FBA 行数量留空并保持 AMAZON_NA。
5. **对象过滤与状态**：只含 Larkspur 的亚马逊 listing，Inactive 的 LK-SLT-CEL 也要包含（需下载 All Listings 而非 Active Listings 报表）；停产品排除且 Shopify 不动；已归档的旧模具花瓶 LK-VSE-RIB-SG-23 不是库存来源。
6. **近似实体与干扰**：Northwind Glass 的同名花瓶/水瓶、Maple & Birch 的同款马克杯；收件箱里另有 Northwind 价目表附件；油瓶 LK-OIL-CRT 只在 Shopify 上，不能凭空加亚马逊行，但 Shopify 仍要提价。
7. **交付格式**：精确 6 列表头、制表符分隔、两位小数、DEFAULT/AMAZON_NA 渠道代码，本地副本与上传内容一致。
8. **保护非目标数据**：未生效、停产、归档及其他供应商的 Shopify 变体价格不得改动。

## 杠杆 L13（文件往返）

核心分数（F 类 76/100）完全来自智能体上传回 Seller Central 的文件内容：下载报表与附件 → 本地 CLI 连接三份数据并按规则变换 → 用浏览器上传。评分器从服务端存储读取该文件逐行核对，不看页面状态。浏览器无法直接完成变换，CLI 无法直接完成下载/上传，两者形成真实依赖。

## 浏览器的必要性

报表请求与下载、附件下载、库存文件上传、Shopify 改价都只能通过页面完成；模型使用 task.toml 声明的浏览器 MCP 工具（含 `browser_upload` 选择本地文件），看不到 DOM、站点接口或状态文件。下载文件落在 `/workspace/downloads`，CLI 负责解析 CSV/TSV、计算并生成上传文件。

## 当前状态：阻塞于 mock 能力缺口

Amazon Seller Central mock 目前没有 min/max 允许价字段、没有库存报表下载、没有库存文件上传（见 `gaps.json` 三条）。world.py 已按缺口中约定的数据形状生成种子与 golden（`minimumSellerAllowedPrice`/`maximumSellerAllowedPrice`、`inventoryReports[]`、`inventoryFileUploads[]`），待 hub 增量 mock 实现后再做 UI 探测与打包自检。Yahoo 附件下载与 Shopify 变体改价为现有能力。

## 环境复现

- 与工厂其他任务相同的单容器 sitehost 运行时；浏览器启动时三站各开一个标签页。
- 时钟：页面内 `Date` 固定到 2026-11-18 09:30（America/Chicago）并实时前进。
- 邮件附件以 `/files/__SID__/<name>` 引用，文件放在 `seed/files/yahoo_mail/`，启动时复制到会话目录。
- **oracle 上传文件**：`/__oracle/apply` 只能写状态、不能放文件，因此 golden 上传文件以不可猜测的哈希名（`sha256` 前 8 位 + `_larkspur_price_quantity.txt`）预置在 `seed/files/amazon_seller/`，只有 golden 状态里的 `inventoryFileUploads` 记录引用它；智能体看不到该记录，seed 文件目录也仅 root 可读。

## 安全边界

- `/opt/cua` 与 `/var/lib/cua` 仅 root 可读；模型以 `agent` 用户运行。
- sitehost 只接受带随机密钥头的请求；模型直接 curl 站点端口得到 403。
- 参考解通过 `/__oracle/apply` 写入 golden 状态，令牌仅在 `solution/` 中。

## 评分方式

见 `rubric.json`：9 个程序化检查点（F0–F7 基于上传文件，S1 基于 Shopify 状态，O1 基于本地副本），加权部分分；无上传或表头不可按制表符解析时 F 类全部 0；S1 对改动受保护变体扣分，空操作得 0。夹具估算：golden=1.0、nop=0.0、naive≈0.23、format_comma≈0.24、slip_v1_sheet≈0.72、slip_effective_dates≈0.78、slip_fba_quantity≈0.90、slip_price_lowered≈0.90。

## 自测与证据

- 已完成：world.py 确定性生成种子、golden、golden_output、expected.json 与 8 个夹具；按本 rubric 的草稿评分脚本算出上述夹具分数。
- 待完成（mock 补齐后）：ui_probe 验证报表下载、文件上传与 min/max 字段；package + selfcheck；本地 oracle/nop；平台 Qwen×5 / Opus×2 评测。
