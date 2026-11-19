# exp2-l09 · DS-160 提交前更正（草稿，UI 缺口阻塞）

状态：**blocked:ui_gap**，见 `gaps.json`。DS-160 mock 在 Sign Application 后既不锁定表单，也不记录提交内容。
2026-11-18 用 ui_probe 实测：提交后从侧栏回到 Personal 1 把婚姻状况 SINGLE→MARRIED，
改动写入了服务器状态，status 仍为 Submitted；再次签名只会覆盖 `signature.signedDate`。
因此“过早提交、留下错误记录”既不是永久的，也无法观测，主杠杆 L09 的核心检查无从实现。
当前 `world.py`/`spec.json`/`instruction.md`/`rubric.json` 只是为探测打包用的占位稿。

mock 补上 `submission`/`submissionHistory` 与提交后锁定之后，按下面的设计完成任务。

## 故事

Kestrel Robotics 瓜达拉哈拉办公室的 People Ops 协调员 Lena Vogel（Gmail 当前用户，BambooHR 管理员）。
员工 Tomás Herrera（高级控制工程师）1 月要去圣何塞总部做 B1 商务出差，自己填了 DS-160（AA00K7M2P9，
地点 MEX），存到 Review 一步后发邮件请 Lena “对照 HR 记录核一下，没问题就直接提交，下周二面签”。
时钟 2026-11-18 10:00（America/Mexico_City）。

## 需要在提交前更正的字段（核心，L09）

| # | DS-160 现值 | 正确值 | 证据来源 |
|---|---|---|---|
| C1 | 护照 G28831405，签发 09-JUN-2017，到期 09-JUN-2027，签发城市 GUADALAJARA | 新护照（号码、签发/到期日、ZAPOPAN），只在邮件附件扫描件（`worldkit.scan_document`）里 | Gmail 附件 |
| C2 | 婚姻状况 SINGLE，无配偶信息 | MARRIED，配偶姓名来自 BambooHR 紧急联系人（关系 Spouse），生日/国籍来自 Tomás 的线程回复 | BambooHR + Gmail |
| C3 | 旧住址（Providencia） | BambooHR 8 月更新的新住址（Col. Americana） | BambooHR |
| C4 | 职位 CONTROLS ENGINEER，月收入 58,000 | 10/1 晋升后的职位与月收入 = 年薪 payRate/12 | BambooHR payChangeHistory |
| C5 | 抵达 12-JAN-2027，离开 23-JAN-2027 | 差旅组后续邮件改为 19-JAN / 30-JAN；离开日以 `/workspace/input` 中的行程导出为准 | Gmail 更正邮件 + 本地文件 |

## 陷阱

- 顺序/不可逆（主杠杆）：只能在全部更正后提交一次；Tomás 邮件催促“直接提交”，Review 页全部绿勾。
- 近似实体：BambooHR 另有一名 Tomás Herrera Ibarra（蒙特雷仓库），需按员工邮箱/生日匹配。
- 被更正的信息：差旅日期的第一封邮件被后续邮件取代。
- 只在第二来源：新护照号只在扫描件里，邮件正文没有。
- 保护非目标：出生日期、身份证号、出生地、以往赴美记录、安全问题全部保持原值；旧护照不是遗失/被盗（lostOrStolen 保持 No）。

## 提交后的工作（写入至少两个站点 + 本地输出）

- BambooHR：在 Tomás 的 Notes 里记录“DS-160 AA00K7M2P9 已于 11/18 提交”及确认号。
- Gmail：把确认号和面签前须知回复给 Tomás（抄送差旅组）。
- `/workspace/output/ds160_changes.csv`：`section,field,old_value,new_value,source` 每处更正一行。

## 检查点规划（mock 补齐后）

- 核心（core）：`submissionHistory` 恰好 1 条，且 `submission.data` 中 C1–C5 各字段正确（逐项计分）。
  提交时任一核心字段错误即为过早提交，按 L09 通过 gate 压低总分。
- 非目标字段在提交快照中与种子一致（只有在已提交后才计分）。
- BambooHR 新增备注挂在正确员工（非 Ibarra）名下，且含确认号。
- 给 Tomás 的回复含确认号。
- CSV 逐行比对。
- 夹具：golden 1.0；nop 0；naive（不改直接提交）≤0.35；每个 slip 漏一项更正，落在 0.55–0.95；
  另设 `slip_submit_then_fix`（先提交后改）用于验证锁定与快照。
