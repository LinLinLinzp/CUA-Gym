# 任务说明：一月新员工建档与录用条款核对（january-new-hire-records）

- **任务标识与版本**：`cua-hard/january-new-hire-records`，v0.1.0（exp1 杠杆实验批，主杠杆 L06 判断冲突）。
- **场景**：组织办公 / 人事运营。初创公司 Fernhill Labs 的 People Ops 经理 Rosa Delgado 在假期冻结前完成 2027 年 1 月入职批次：在 BambooHR 建档、在 Greenhouse 结案为 Hired、回复招聘的 Slack 线程，并输出名单 CSV。
- **涉及站点**：Greenhouse（申请、offer 表单、招聘备注）、DocuSign（各录用信/修订信封的状态与所含文件名）、Slack（招聘群聊、Theo 的提问线程）、BambooHR（员工档案、薪酬变更），外加本地 `/workspace/input/offer_letters/` 中 15 份生成的录用信/修订 PDF。四站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：四站初始数据；本地 PDF（包括作废版、未发出的草稿、未签署的修订，与正式版格式完全相同）。
- **输出**：BambooHR 新员工与薪酬、Greenhouse 阶段、Slack 线程回复（服务端持久化状态）；`/workspace/output/january_new_hires.csv`。

## 主杠杆 L06：来源冲突且无明示优先级

题面只说“offer 已确定、一月入职的人”和“与实际签署不一致的 offer”，不说哪个来源为准。每个冲突都由一条职业常识裁决，错误来源乍看同样权威：

| 人 | 冲突 | 裁决常识 | 正确值 |
|---|---|---|---|
| Priya Raman | Greenhouse / Slack / 本地首版 PDF 写 165,000；首个信封 12/1 作废，rev1 信封 12/3 completed | 已签署合同优先，作废文件无效 | 172,000 |
| Marcus Lindqvist | 原信 completed 写 1/4，Slack “Starting Jan 4”；12/10 completed 的修订改为 1/19 | 后签署的修订优先于原条款 | 2027-01-19 |
| Elena Petrova | Slack 称已升为 Senior PD / 128k，本地有修订 PDF；信封仅 delivered 未签 | 未签署的修订不生效，聊天不是记录 | Product Designer / 118,000 |
| Leo Fischer | Greenhouse 职位与 offer、Slack、本地 AE 草稿均为 AE/95k；completed 信封里是 SAE 文件 | 已签署文件优先于 ATS 表单与草稿 | Senior Account Executive / 105,000 |
| Sam Ortiz | 工程总监转述传闻“接受反聘、先别建档” | 正式记录优先于传闻（无撤回，且有招聘备注确认） | 正常建档 |
| Nadia Haddad | 已签信封 + offer 仍为 accepted + 早期 Slack 名单；Greenhouse 申请 12/7 “Candidate withdrew” 并有备注 | 后发生的正式撤回优先 | 不建档 |
| Owen Brandt | Greenhouse 起始日 1/25；已签信写 2/1 | 已签署文件优先于 ATS | 不属一月，不建档；需在 Slack 报告 |

## 主要约束（≥4 类）

1. **对象筛选**：只处理 offer 已确定且一月入职的人；Ines 的 offer 只是 sent、信封未签；12 月已入职者（Wei、Tariq）不在范围内。
2. **跨站字段对应**：DocuSign 信封中的文件名 → 本地 PDF 中的条款 → BambooHR 字段；Greenhouse 申请 → Hired 阶段。
3. **金额与日期**：基本年薪与入职日必须取签署值。
4. **时间窗口**：以签署的入职日判断是否属于 2027 年 1 月（Owen 2/1 排除）。
5. **状态**：voided / delivered / completed 信封，rejected 申请，sent 与 accepted 的 offer。
6. **重复与近名**：Jordan 已于 12/10 建档（Slack 说明），不得重复；BambooHR 中有近名员工 Priya Ramanathan，Greenhouse 中有近名候选人 Hannah Sato 和 Omar Haddad，均不得改动。
7. **交付格式**：CSV 表头、日期格式、整数薪资；Slack 必须回复在指定线程。

## 浏览器与 CLI 的必要性

建档、薪酬变更、移动阶段、线程回复都只能在页面中完成。DocuSign 页面只显示信封状态、历史与文件名，不显示条款正文；条款只在本地 PDF 中（需用 pdftotext 等 CLI 读取）。两者缺一不可：只看 PDF 不知道哪份生效，只看 DocuSign 不知道金额。DocuSign 在本题只读。

## 环境复现

- 基础镜像与 sitehost 运行时同 P0 试点题；浏览器启动时为四个站点各开一个标签页。
- 时钟：页面内 `Date` 固定到 2026-12-14 09:30（America/Los_Angeles）并实时前进。
- `world.py` 确定性生成种子、golden、PDF（reportlab invariant 模式）、expected.json 与夹具。

## 评分方式

见 `rubric.json`：14 个程序化检查点，加权部分分，core 检查点合计 76 权重，均由冲突判断决定。“不得创建/不得改动”类检查以完成相应工作为前提，空操作得 0。预期夹具分：golden=1.0、nop=0.0、naive≈0.16，五个 slip（Priya 作废信封、Marcus 修订、Elena 未签修订、Leo 草稿、Nadia 撤回）均在 0.87～0.89。

## 自测与证据

- 已完成：world.py 生成与确定性校验（两次生成逐字节一致）；本地评分草稿核对夹具分布（golden 1.000 / nop 0.000 / naive 0.156 / slip 0.872–0.894）；ui_probe 实测全部写操作：BambooHR 新建员工与薪酬变更、Greenhouse 移至 Hired、Slack 线程回复（golden 的 threads 结构按实测对齐），并确认 DocuSign 详情页显示作废横幅、历史原因与文件名，其 Download 仅导出元数据、不含条款。
- 待完成：verifier 编写后的 selfcheck、本地 `harbor run -a oracle / -a nop`、平台 Qwen×5 / Opus×2 评测。
