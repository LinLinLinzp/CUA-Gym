# 任务说明：PSYC 3150 迟交与重交成绩登记（psyc3150-late-resubmission-grading）

- **任务标识与版本**：`cua-hard/psyc3150-late-resubmission-grading`，v0.1.0（exp2 杠杆批次，主杠杆 L11 长文条款）。
- **场景**：专业事务 / 高校助教评分。Lakeshore State University 心理学课程 PSYC 3150 的助教 Jordan Ellis 在另一位助教 Kevin Tran 出差期间，按教授要求把 Lab Report 3 剩余 17 份报告和 Lab Report 2 的 6 份重交作业的最终分数登记到 Canvas，并同步 TA 跟踪表。
- **涉及站点**：Canvas LMS（课程 Syllabus 页链接的 9 页《Course Policies》PDF、成绩发布公告、Gradebook 录分）、Gmail（教授批准的延期及其更正、SAS 便利信、教务长缺席通知、学生与 Kevin 的来信）、Google Sheets（TA 跟踪表：rubric 原始分、已用重交记录、需回填的 Days late / Final / In Canvas），外加本地 CSV（Canvas 提交时间导出，UTC）与本地交付文件。三站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：三站的初始数据；`/workspace/input/submissions_export.csv`（列 student_name,sis_user_id,section,assignment,attempt,submitted_at_utc；含 Diego 的两次提交与 6 份 Lab 2 重交的 attempt 2）。
- **输出**：Canvas 中 3103（Lab 3）17 条 submission 的 score 与 3102（Lab 2）中 3 条重交的 score；Sheets「Lab 3」表 17 行 F/G/H 列与「Lab 2 Resubmissions」表 6 行 E/F 列；`/workspace/output/grade_entries.csv`（sis_id,assignment,final_score，23 行）。

## 主要约束（≥4 类）

1. **长文条款（主杠杆 L11）**：Syllabus 页只有摘要（每天扣 10%、可重交一次、延期找教授），真正决定分数的条款埋在 PDF 后半部分：7.2 不足 24 小时按一天计、7.3 超过 120 小时记 0、9.3 助教承诺无效、10.2 七天窗口、10.3 重交封顶 85%、10.4 每学期一次、10.5 取较高者、11.2/11.3 SAS 灵活截止 = 48 小时且超窗后从窗口结束起算、11.4 不追溯、12.2 教务长核实缺席期内到期免罚、14.2 以最后一次提交为准、14.3 15 分钟宽限但超出后从截止起算。每条例外只适用于个别学生。
2. **时间窗口与时区**：导出 CSV 为 UTC，截止为中部时间 23:59（11 月 1 日起为 CST，UTC−6）；Lena Vogel 的 11-07T04:48Z 实为当地 11-06 22:48 按时；Lab 2 重交窗口由 Canvas 公告时间（10-30）推出，至 11-07T05:59Z 关闭（Kofi 超窗）。
3. **金额/分数计算**：每天 −5 分、半分记录（42.5）、封顶与取较高者（Julia 48→42.5<44 保留 44）。
4. **跨站字段对应**：Sheets 行 ↔ Canvas 学生（SIS ID / 姓名）↔ 邮件中的延期与信件 ↔ CSV 提交时间；Priya 已用的 Lab 1 重交只记录在 Sheets「Resubmissions Used」表。
5. **更正信息与近似实体**：教授第一封邮件把延期写给 Aisha Bello，同串回复更正为 Aisha Rahman；两位 Aisha 分属不同 section。
6. **权限/状态**：Kevin 在邮件串中“take the weekend”无效（只有教授能延期）；SAS 信签发日期决定是否生效。
7. **保护非目标数据**：Kevin 已录入的 7 份 Lab 3 成绩与表格行、其他作业成绩不得改动。

## 浏览器的必要性

政策 PDF 只能从 Canvas Syllabus/Pages 中的链接下载；成绩发布日期在 Canvas 公告；延期、更正、SAS 信与教务长通知只在 Gmail；原始 rubric 分与已用重交记录只在 Google Sheets；录分只能在 Canvas Gradebook 中逐格输入，跟踪表回填只能在 Sheets 中编辑。本地 CSV（UTC 提交时间、多次提交）是 Canvas UI 不显示的信息，必须用 CLI 读取并换算，二者形成真实依赖；PDF 下载后可用 `pdftotext` 阅读。

## 环境复现

- 与工厂其他任务相同的基础镜像与 sitehost 运行时；政策 PDF 位于 `seed/files/canvas_lms/PSYC3150_Course_Policies_Fall2026.pdf`，以 `/files/__SID__/…` 提供，点击即下载到 `/workspace/downloads`。
- 时钟：页面内 `Date` 固定到 2026-11-18 09:30（America/Chicago）并实时前进。
- world.py 用规则函数计算所有最终分并与手工核对表断言一致，确定性生成种子、golden、expected.json 与各夹具。

## 安全边界

- `/opt/cua`（站点代码、种子、oracle 令牌哈希）与 `/var/lib/cua`（状态、密钥）仅 root 可读；模型以 `agent` 用户运行。
- sitehost 只接受带随机密钥头的请求，模型直接 curl 站点端口会得到 403。
- 参考解通过 `/__oracle/apply` 写入 golden 状态，需要只存在于 `solution/` 中的令牌。

## 评分方式

见 `rubric.json`：20 个程序化检查点，加权部分分。L11 条款检查 K1–K11 共 64 权重；“保持原分”类（K10、K11、S4）须同时在 Sheets 填入正确 Final，P1 保护检查以至少 5 名 Lab 3 学生录分正确为前提，空操作得 0。预估夹具：golden=1.0、nop=0.0、naive≈0.21、slip_ta_extension≈0.935、slip_accommodation_window≈0.935、slip_term_cap≈0.933。

## 自测与证据

- 已完成：world.py 生成与本地评分模拟（与上列预估一致）；ui_probe 验证 Canvas Gradebook 录分（含 42.5）、Sheets 单元格编辑、Syllabus PDF 链接下载。
- 待完成：verifier 实现、fixture 自测（`factory/pipeline/selfcheck.py`）、平台 cua-pre-valid 与 Qwen×5 / Opus×2 评测。
