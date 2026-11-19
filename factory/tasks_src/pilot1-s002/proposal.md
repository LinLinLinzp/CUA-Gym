# 任务说明：社区影迷协会 12 月片单定档（lsfs-december-programme）

- **任务标识与版本**：`cua-hard/lsfs-december-programme`，v0.1.0。
- **场景**：文化内容 / 社区影迷放映策划。伦敦社区放映组织 Lantern Street Film Society 的选片负责人 Hannah 委托助手根据会员提名帖敲定 12 月三场放映，并把排片落到协作看板、日历和社区公告上。
- **涉及站点**：
  - Reddit：r/LanternStreetFilms 的提名帖（已锁定），以及置顶的场地改期帖和其中的版主回复。完成后在此发布节目单。
  - GitLab：lsfs-programme 项目。维基上有选片规则、场地手册、2025 年前放映史和许可说明，看板上是 2025 年以来的放映记录。完成后在看板建放映 issue。
  - Google Calendar：Lantern Street FS 日历，上面有 10、11 月放映和 12 月场地占位。完成后在此新建放映日程。
  - 本地 CSV：发行商报价表。
  - 三站均为 CUA-Gym-Hub mock，在容器内以真实域名离线提供。
- **输入**：三站初始数据（root-only 种子）；`/workspace/input/distributor_quotes.csv`（发行商、片名、年份、导演、分级、介质、费用、许可期、片长，共 20 行）。
- **输出**：GitLab 新 issue、Google Calendar 新事件、Reddit 新帖，均为服务端持久化状态；另有 `/workspace/output/december_programme.csv`。

## 正确结果

| 日期 | 开映 | 影片 | 年份 | 分级 | 票数 | 费用 (£) | 发行商 |
|---|---|---|---|---|---|---|---|
| 2026-12-03（周四） | 19:30 | Paris, Texas | 1984 | 15 | 48（27+21） | 130.00 | Curzon Film |
| 2026-12-10（周四） | 19:30 | Solaris | 1972 | PG | 44 | 140.00 | Arrow Films |
| 2026-12-19（周六） | 14:30 | The Red Shoes | 1948 | U | 22 | 110.00 | BFI Distribution |

被排除的提名及原因：

| 影片 | 净票数 | 排除原因 |
|---|---|---|
| Aftersun | 52 | 只有 DCP |
| Stalker | 39 | 许可 2027-01-22 才开始 |
| Portrait of a Lady on Fire | 25 | 15 级，不能用于下午场；晚场名额已被前两名占满 |
| My Neighbour Totoro | 24 | 2025-06-19 放过，未满两年 |
| The Umbrellas of Cherbourg | 23 | £165，超过 £150 上限 |
| Paddington 2 | 15 | 票数低于 The Red Shoes |
| Wings of Desire | 11 | 12 级，且票数低 |
| Possession | 9 | 18 级，且 £175 超上限 |

## 主要约束（≥4 类）

1. **对象筛选与重复合并**：只有顶层评论算提名，跟帖不计。同一影片的多次提名按维基规则合并：Paris, Texas 27+21=48，合并后超过 Solaris 的 44。
2. **跨站字段对应**：
   - 提名的片名要对应到报价表的具体行。“Solaris (Tarkovsky)” 对应 1972 版，不是 2002 版 Soderbergh。
   - 放映史分两处查：2025 年起在 GitLab 看板，之前在维基历史页。
3. **金额与数量**：许可费上限 £150；票数取 upvotes−downvotes。
4. **时间窗口**：
   - 两年禁映期：Totoro 2025-06-19 放过，排除；The Red Shoes 2024-11-28 放过，2026-11-28 起可再放。
   - 许可期：Stalker 许可从 2027-01-22 开始，排除。
5. **状态/资格**：
   - 介质：DCP-only 的 Aftersun 排除。
   - 分级：下午场只能放 U/PG。
6. **版本冲突（过时信息）**：维基场地页和日历占位仍是 12/17 晚场。置顶帖改为 12/19 周六 14:30 开映，版主回复又补充了下午场的分级规则和排序方式。
7. **交付格式**：
   - issue 标题 `Screening YYYY-MM-DD: Film title`，带 screening 标签，描述写发行商与费用。
   - 日历事件按 11 月惯例写：“LSFS: 片名”，记在 Lantern Street FS 日历，地点为 St Brigid's Hall。
   - Reddit 帖带 Programme 标签。
   - CSV 列固定。
8. **保护非目标**：不得为未入选影片或 12/17 建 issue 或事件，不得改动既有 issue 和其他日程。

## 陷阱

| 陷阱 | 粗心做法 | 能发现问题的可见材料 | 对应检查点 |
|---|---|---|---|
| 重复提名 | 只看单条最高票，排成 Solaris 第一、Paris 第二 | 维基规则第 1 条；kodachrome_kid 的第二次提名以及 desertmotel 的回复 | G1、G2、C1、C2、O1 |
| 场地改期 | 按日历和维基仍排 12/17 19:30 晚场 | Reddit 置顶帖与 Marta 的回复 | G3、G6、C3、C5、R2、O1 |
| 下午场分级 | 第三场放 15 级的 Portrait | Marta 的回复 + 报价表 certificate 列 | G3、C3、O1 |
| 近期重复放映 | 第三场放 Totoro（2025-06-19 放过） | GitLab 看板放映史 | G3、C3、O1 |
| 边界日期 / 近似标题 | 看到 “we showed it a while back”，或把 “The Red Turtle” 当成同一部片，从而排除 Red Shoes | 维基 Screening history 页：2024-11-28，已满两年 | G3、C3、O1 |
| 近似报价行 | Solaris 取 2002 版（12A、£85） | 提名写明 Tarkovsky；报价表的 year/director 列 | G4、R1、O1 |

## 浏览器的必要性

提名票数、置顶改期和版主回复只能在 Reddit 页面上读到，选片规则、场地手册和放映史只能在 GitLab 页面上读到。建 issue、建日历事件、发帖也只能通过页面完成。报价表是本地文件，必须用 CLI 读取，它决定了分级、介质、许可期和费用，是真实的数据依赖。

## 环境复现

- 时钟固定为 2026-11-18 09:30（Europe/London，周三）。12 月伦敦为 GMT，因此日历存储的 UTC 时间与本地时间一致。
- 每个 trial 都在新容器中从种子初始化。
- 操作只需新建 issue（模态框）、新建日历事件（模态框，日期时间输入 + 日历下拉）、发帖（社区下拉 + 标签选择），不需要拖拽。

## 安全边界

同参考题：
- 站点代码与状态目录仅 root 可读。
- sitehost 只接受浏览器守护进程的密钥请求。
- 参考解通过 oracle 令牌写入 golden 状态。

## 评分方式

见 `rubric.json`。共 14 个程序化检查点，按权重计部分分：

| 站点 / 输出 | 检查点 | 权重 |
|---|---|---|
| GitLab | G1–G6 | 36 |
| Calendar | C1–C5 | 31 |
| Reddit | R1–R2 | 17 |
| CSV | O1 | 16 |

“不得做”类检查以对应站点至少完成一项正确放映为前提，因此空操作得 0。

夹具预期得分：

| 夹具 | 得分 |
|---|---|
| golden | 1.0 |
| nop | 0 |
| naive | ≈0.04 |
| slip_merge | ≈0.57 |
| slip_move | ≈0.60 |
| slip_repeat | ≈0.65 |
| slip_boundary | ≈0.65 |
| slip_solaris | ≈0.89 |

## 自测与证据

- 已完成：
  - `world.py` 生成种子、golden 与 8 个变体。
  - 用本地模拟评分核对各变体分数，均落在 `spec.fixture_expectations` 区间内。
  - 用 ui_probe 在浏览器里实测三类写操作，均已持久化到服务端状态。
- 待完成：verifier 编写与 selfcheck，以及平台评测。
