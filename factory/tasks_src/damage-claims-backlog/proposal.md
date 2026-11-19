# 任务说明：破损索赔积压处理（damage-claims-backlog）

- **任务标识与版本**：`cua-hard/damage-claims-backlog`，v0.1.0（P0 试点题，用于验证单容器多站运行时）。
- **场景**：产业运营 / 电商售后。家居电商 Juniper & Pine 的客服负责人在同事请假期间清理破损索赔。
- **涉及站点**：Gmail（客户来信、回复）、Slack（置顶政策及其线程修订、审批频道）、Shopify 后台（订单、退款、标签），外加本地 CSV（承运商送达日期）与本地交付文件。三站均为 CUA-Gym-Hub mock，已还原真实品牌，在容器内以真实域名离线提供。
- **输入**：三站的初始数据（root-only 种子，启动时写入状态目录）；`/workspace/input/carrier_deliveries.csv`。
- **输出**：Shopify 退款与标签、Slack 审批消息、Gmail 回复等服务端持久化状态；`/workspace/output/claims_log.csv`。

## 主要约束（≥4 类）

1. **跨站字段对应**：邮件中的客户/单号 → Shopify 订单；来信地址可能与订单邮箱不同（#1051）；客户写错单号（#1047→#1053）。
2. **时间窗口**：以承运商送达日期判断 14 天窗口，Shopify 只有发货日期（#1029 逾期）；#1051 有一次投递异常记录。
3. **金额计算**：只退破损件、默认不退运费；整单损坏退全额；玻璃制品（GL-）额外退运费。
4. **权限与审批**：单笔 > $200 不能直接退款，需在 #refund-approvals 提交（#1038）。
5. **版本冲突**：置顶政策的线程回复修订了审批额度（150→200）和玻璃制品运费规则；客户的第二封邮件更正了破损数量。
6. **重复处理**：#1035 已于 3/10 全额退款，客户催促邮件不能触发二次退款。
7. **保护非目标数据**：无人投诉的订单不得改动。

## 浏览器的必要性

三站的退款、打标签、发审批消息、回复邮件都只能通过页面完成；模型通过 task.toml 中声明的浏览器 MCP 工具（computer / browser_navigate / browser_tabs / browser_upload，截图 + 坐标/键盘，与 computer-use 工具同构）操作，看不到 DOM、站点接口或状态文件。题面不写任何工具用法，工具自描述。本地 CSV 与日志文件由 CLI 处理，二者形成真实依赖（送达日期决定是否退款）。

## 环境复现

- 基础镜像 `mcr.microsoft.com/playwright/python:v1.65.2-noble`，apt/pip 使用阿里云镜像；镜像内不预装 Claude Code（平台预装 / Harbor 内置 claude-code agent 自行安装）。
- 容器 ENTRYPOINT 启动 sitehost（静态站点 + 统一状态接口）与浏览器守护进程，浏览器启动时已为三个站点各开一个标签页（同 CUA-Gym 的初始打开应用）；每个 trial 都是新容器，从种子重新初始化，无需人工重置。
- 时钟：页面内 `Date` 被固定到 2026-03-16 09:30（America/Los_Angeles）并实时前进。
- 健康检查：`curl -fsS http://127.0.0.1:8079/health`。

## 安全边界

- `/opt/cua`（站点代码、种子、oracle 令牌哈希）与 `/var/lib/cua`（状态、密钥）仅 root 可读；模型以 `agent` 用户运行。
- sitehost 只接受带随机密钥头的请求，密钥仅浏览器守护进程持有；模型直接 curl 站点端口会得到 403。
- 参考解通过 `/__oracle/apply` 写入 golden 状态，需要只存在于 `solution/` 中的令牌（镜像内仅存 SHA-256）。

## 评分方式

见 `rubric.json` 与 `verifier-checkpoints.md`：19 个程序化检查点，加权部分分；“不得做”类检查以完成对应工作为前提，空操作得 0。夹具自测：golden=1.0、nop=0.0、naive≈0.32、one_slip≈0.88。

## 自测与证据

- 已完成：fixture 自测（`factory/pipeline/selfcheck.py`）。
- 待完成：本地 `harbor run -a oracle / -a nop`、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测；结果登记在 `evaluation.json`。
