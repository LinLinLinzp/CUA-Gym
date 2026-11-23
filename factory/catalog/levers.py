#!/usr/bin/env python3
"""Difficulty levers beyond what CUA-Gym uses (multi-app, ordering, edge cases).

Each experimental task is built around ONE primary lever (plus an ordinary
realistic multi-site story) so platform scores can be attributed to it.
Writes catalog/levers.json (for agents) and catalog/levers.md (Chinese, for people).
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# id, 中文名, what it is (for authors), how to build it, how to verify it, runtime support needed
LEVERS = [
    ("L01", "门槛计分", "Core requirements are all-or-nothing: unless every core check passes, the reward is capped low.",
     "Mark 4-8 checks as core in rubric.json (`core: true`); reward = weighted score if all core pass, else min(score, 0.3).",
     "cuaverify Grader.gate(); recomputable offline from any report.json", "none"),
    ("L02", "非文本证据", "The decisive facts exist only inside images or scanned documents (receipt photo, signed form scan, chart, screenshot) attached on a site.",
     "Render evidence with worldkit.scan_document()/chart_png(); attach via the site's file/attachment fields; no text copy anywhere.",
     "Outcome depends on values readable only from the image", "worldkit media helpers"),
    ("L03", "隐藏数据", "Needed records are not on the first screen: beyond pagination, behind default filters (archived, closed, other year), in collapsed threads or 'load more'.",
     "Seed 100+ records so lists paginate; put 30-50% of targets behind a default filter or on later pages; no shortcut that lists them all.",
     "Per-target checks; missing the hidden ones costs most of the score", "none"),
    ("L04", "规模", "25-40 items must each be processed with a per-item cross-site lookup and exact handling.",
     "Generate items programmatically with varied, realistic attributes; each needs data from a second site.",
     "Per-item checks with an accuracy threshold on the core group", "none"),
    ("L05", "多跳依赖", "A chain of 4+ dependent hops across 3-4 sites: a value found on A identifies a record on B, whose data drives an action on C that produces an id needed on D.",
     "Design the chain so each hop's input only exists in the previous hop's output; no hop can be skipped by guessing.",
     "Check the final artifacts and every intermediate write", "none"),
    ("L06", "判断冲突", "Sources disagree and nothing states which wins; the right answer follows professional norms (signed contract over email, system of record over chat, later signed amendment over earlier terms, official notice over hearsay).",
     "Plant 3+ conflicts each resolvable by one clear norm a competent professional applies; the wrong source must look equally authoritative at a glance.",
     "Check the values that depend on resolving each conflict", "none"),
    ("L07", "可重算脚本", "Besides doing the work, deliver a script that recomputes the outputs from inputs; the verifier reruns it on hidden mutated inputs.",
     "Specify the script interface (env vars for input/output paths, exit codes); generate 3-6 mutations in the verifier.",
     "cuaverify.run_replay() as the agent user with a timeout; compare outputs per mutation", "replay helper"),
    ("L08", "高级操作", "The outcome requires continuous/precise manipulation: drag-and-drop ordering between columns, date-range pickers, spreadsheet range selection/fill, resizing.",
     "Pick a site interaction that genuinely needs it (no keyboard alternative); verify the resulting order/range.",
     "operation_difficulty = 3", "browser drag/move actions (present)"),
    ("L09", "不可逆与顺序", "Some actions are irreversible or lock records (submit, publish, pay) and order matters (approve before pay, fix data before submitting).",
     "Seed records that must be corrected before an irreversible submit; submitting early leaves a permanent wrong record.",
     "Check final state and the event history (e.g. first submission content)", "sites keep history fields"),
    ("L10", "不可信指令", "Content from third parties contains instructions that must not be followed (vendor asks to change bank details by email, a doc says 'also forward this to ...').",
     "Embed 1-3 plausible but unauthorized requests in emails/docs/tickets within the work material.",
     "Check that no unauthorized change/forward happened, alongside the real work", "none"),
    ("L11", "长文条款", "A long policy/contract (8-15 pages) with exceptions and definitions buried in later sections decides the outcome.",
     "Generate a multi-page PDF (worldkit.long_pdf()) on a site; the exception applies to some items only.",
     "Check items affected by buried exceptions", "worldkit media helpers"),
    ("L12", "数值精算", "Exact arithmetic with domain rules: proration by days, currency conversion with rates published on another site for a specific date, rounding rules, fee tiers.",
     "Put rates/rules on a different site than the amounts; require cents-exact results.",
     "Exact match to independently computed values", "none"),
    ("L13", "文件往返", "Download a file from one site, transform it locally (CLI), upload the result to another site in a required format.",
     "The uploaded file's content is what gets checked (parse it from the target site's stored files).",
     "Read uploaded file via /var/lib/cua/files/<site>/", "upload/download (present)"),
    ("L14", "动态世界", "The world reacts to the agent: after a submission a rejection/reply/new request arrives that must be handled.",
     "Declare triggers in world output (triggers.json): when a record matching X appears on site A, append Y to site B after N seconds.",
     "Check that the follow-up was handled", "sitehost triggers + browser storage refresh"),
    ("L15", "状态错觉", "Things look done but are not: drafts vs sent, scheduled vs published, pending vs posted, saved vs submitted.",
     "Seed items in deceptive intermediate states; the instruction asks for the real final state.",
     "Check the true status field", "none"),
    ("L16", "隐含意图", "The request leans on history ('same split as last quarter', 'the usual courier', 'like we did for Acme') that must be inferred from past records.",
     "Seed the history so exactly one reading is consistent; nearby distractor histories exist.",
     "Check values derived from the inferred precedent", "none"),
]


def main():
    data = [{"id": i, "name_zh": zh, "what": what, "build": build, "verify": verify, "runtime": rt}
            for i, zh, what, build, verify, rt in LEVERS]
    (HERE / "levers.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    rows = ["# 加难手段清单", "", "CUA-Gym 已用：多应用、顺序要求、边界情况。以下为新增手段，每道实验题以其中一项为主，便于从平台分数归因。", "",
            "| 编号 | 手段 | 说明 | 运行时支持 |", "|---|---|---|---|"]
    rows += [f"| {d['id']} | {d['name_zh']} | {d['what']} | {d['runtime']} |" for d in data]
    (HERE / "levers.md").write_text("\n".join(rows) + "\n")
    print(f"{len(data)} levers")


if __name__ == "__main__":
    main()
