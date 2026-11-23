# 加难手段清单

CUA-Gym 已用：多应用、顺序要求、边界情况。以下为新增手段，每道实验题以其中一项为主，便于从平台分数归因。

| 编号 | 手段 | 说明 | 运行时支持 |
|---|---|---|---|
| L01 | 门槛计分 | Core requirements are all-or-nothing: unless every core check passes, the reward is capped low. | none |
| L02 | 非文本证据 | The decisive facts exist only inside images or scanned documents (receipt photo, signed form scan, chart, screenshot) attached on a site. | worldkit media helpers |
| L03 | 隐藏数据 | Needed records are not on the first screen: beyond pagination, behind default filters (archived, closed, other year), in collapsed threads or 'load more'. | none |
| L04 | 规模 | 25-40 items must each be processed with a per-item cross-site lookup and exact handling. | none |
| L05 | 多跳依赖 | A chain of 4+ dependent hops across 3-4 sites: a value found on A identifies a record on B, whose data drives an action on C that produces an id needed on D. | none |
| L06 | 判断冲突 | Sources disagree and nothing states which wins; the right answer follows professional norms (signed contract over email, system of record over chat, later signed amendment over earlier terms, official notice over hearsay). | none |
| L07 | 可重算脚本 | Besides doing the work, deliver a script that recomputes the outputs from inputs; the verifier reruns it on hidden mutated inputs. | replay helper |
| L08 | 高级操作 | The outcome requires continuous/precise manipulation: drag-and-drop ordering between columns, date-range pickers, spreadsheet range selection/fill, resizing. | browser drag/move actions (present) |
| L09 | 不可逆与顺序 | Some actions are irreversible or lock records (submit, publish, pay) and order matters (approve before pay, fix data before submitting). | sites keep history fields |
| L10 | 不可信指令 | Content from third parties contains instructions that must not be followed (vendor asks to change bank details by email, a doc says 'also forward this to ...'). | none |
| L11 | 长文条款 | A long policy/contract (8-15 pages) with exceptions and definitions buried in later sections decides the outcome. | worldkit media helpers |
| L12 | 数值精算 | Exact arithmetic with domain rules: proration by days, currency conversion with rates published on another site for a specific date, rounding rules, fee tiers. | none |
| L13 | 文件往返 | Download a file from one site, transform it locally (CLI), upload the result to another site in a required format. | upload/download (present) |
| L14 | 动态世界 | The world reacts to the agent: after a submission a rejection/reply/new request arrives that must be handled. | sitehost triggers + browser storage refresh |
| L15 | 状态错觉 | Things look done but are not: drafts vs sent, scheduled vs published, pending vs posted, saved vs submitted. | none |
| L16 | 隐含意图 | The request leans on history ('same split as last quarter', 'the usual courier', 'like we did for Acme') that must be inferred from past records. | none |
