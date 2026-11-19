# Mock 建站交接（Codex 独立运行）

从规划到审计的全部环节都由 Codex 完成，不依赖 Claude。可以在其他设备上运行，也可以在 Codex 窗口里运行。

## 需要同步的代码

- 主仓库 `CUA-Gym` 分支 `qwen-cuas`：需要其中的 `factory/` 目录（脚本、站点清单）。
- hub 子模块（`LinLinLinzp/CUA-Gym-Hub`）分支 `qwen-cuas`。其中这几处是建站必需的：
  - `HARBOR_CONTRACT.md`：运行时约定；
  - `templates/`：标准状态接口模板；
  - `.claude/agents/*.md`：plan/dev/audit/playwright 的操作规范；
  - 已完成的站点。

注意：目前这两处都只在本机提交过，没有推送。迁移前需要先推送，或者直接拷贝整个目录。

## 环境要求

- Node ≥ 18 和 npm。npm 源默认用 `registry.npmmirror.com`，可以用 `NPM_REGISTRY` 改。
- Python 3.9 及以上；Docker（动态认证要用）。
- 已登录的 Codex CLI。ChatGPT 账号目前用不了 `gpt-6.2-sol`，脚本会自动退回到 `gpt-6.1-sol`。
- 如果 Node 报 TLS 证书错误，导出系统根证书，并用 `NODE_EXTRA_CA_CERTS` 指过去。

## 方式一：脚本批量跑（推荐）

```bash
cd CUA-Gym
# A 级站点，6 个并行，所有环节都用 Codex
python3 factory/hub_tools/build_mocks.py --tier A --workers 6 --engine codex-all
# 只建指定的站
python3 factory/hub_tools/build_mocks.py --brands "Yahoo Mail,Google Chat" --engine codex-all
```

- **进度**：`factory/build/mock_status.json`；日志在 `factory/build/mock_logs/<站点>.log`。
- **断点续跑**：可以随时中断，重跑会从断点继续。已验收的站会跳过；标记为 failed 的站会再完整尝试一次。
- **验收**（全部满足才算通过）：
  - TODO 里的 P0/P1 全部完成；
  - AUDIT 没有未修复的 P0；
  - TEST 以 `TEST COMPLETE … PASS` 结尾；
  - 能构建；
  - 动态认证通过：能渲染、加载后会写回服务端、空闲时不会回写。
- **通过后**：自动提交到 hub 的 `qwen-cuas` 分支，并写入 `factory/catalog/built_sites.json`。

## 方式二：在 Codex 窗口里逐站做

对每个站点，把下面这段贴给 Codex（替换尖括号里的内容）：

> 在 hub 仓库为 <品牌> 构建 mock，目录 `websites/<slug>_mock`，开发端口 <端口>。
> 先读 `websites/<slug>_mock/SEED.md`（没有的话，就按 `factory/catalog/candidates.json` 里该站的核心业务操作来写）和 `HARBOR_CONTRACT.md`。
> 然后依次按 `.claude/agents/plan.md`、`dev.md`、`audit.md`、`playwright.md` 完成规划、开发、审计、测试，直到满足验收条件。最后运行 `python3 factory/hub_tools/dyn_certify.py <slug>`，确认通过。

## 回传

远端把每批通过的站点推到 hub 的 `codex/mock-tier-a-production` 分支。每站随源码提交 `package-lock.json`、`SEED.md`、`SCHEMA.md`、`TEST.md` 和 `AUDIT.md`。后两份报告默认被 Git 忽略，需要按站点路径加入提交。

本机在 `CUA-Gym` 根目录查看已交付站点，并在本地构建及复验通过后更新构题站点池。

```bash
python3 factory/hub_tools/sync_remote_mocks.py
NODE_EXTRA_CA_CERTS=/etc/ssl/cert.pem NPM_REGISTRY=https://registry.npmjs.org \
  python3 factory/hub_tools/sync_remote_mocks.py --apply
```

命令使用本机交接快照确定分给远端的 Tier A 站点。遇到同名本地版本或交付报告缺失时，会保留并报告待处理的站点。添加 `--pilot` 可以检查 Wayfair 和 Grubhub 的试点分支。

## 当前进度

- 已通过：Airbnb、Medium。
- 已开始：ClickUp、Xero（测试没过，需要继续返工）；NetSuite（规划中断）。
- 规划阶段已开始的公共工具：Yahoo Mail、Google Chat、Fastmail、Mattermost、Excel 网页版、Proton Mail。

这些站的文件都在 `hub/websites/<slug>_mock/` 下，续跑时直接接着做。

## 已有站点待修清单（动态认证不通过，2026-11-18）

运行 `python3 factory/hub_tools/dyn_certify.py <站点>` 可以复现。修好、提交以后重跑一次，通过就会自动回到站点池（重新生成目录：`python3 factory/catalog/build_catalog.py`）。

- **注入数据无效**（hydrate=False）：coinbase、expedia、google_docs、google_flights、clio、contractbook、hubspot、amplitude、google_analytics、meta_ads、wandb。
  已修过的 4 个站（`git log` 里可以看到）涉及 3 类问题：
  - 取 `/state` 时没有拆出 `stored_state`，而是把整个返回包当成数据（Zendesk、Expensify）；
  - 读错了字段（BambooHR）；
  - 首次渲染就把默认数据写回服务端，覆盖了注入数据（Greenhouse）。
- **打开就崩**：google_drive、google_flights、outlook_web、uber_eats、monday，原因是缺 Provider 或字段为 undefined。
- **空闲时反复回写**：coinbase、robinhood。行情这类实时数据不能写进 state，应该在渲染时从固定数据推导出来。
- **加载后不写回服务端**：tradingview、hubspot_marketing、openreview、mailchimp、mixpanel。需要确认用户操作之后会不会写回。

## 出题发现的缺失功能（增量 mock 需求）

下面是出题 agent 在实际试做时发现的站点缺失功能，原文照录。实现后把对应条目加进该站的 `TODO.md`（P0），按正常流程验收；补好后告诉我，我会重新出这几道题。

- **visa_portal_ds160**（exp2-l09）：Lock the application after final submission. Once Sign Application succeeds (ds160Application.status == "Submitted"), every form page (personal1 … photo) and the Sign page must be read-only: inputs/radios/selects/checkboxes disabled, Save and Next/Sign Application hidden or disabled, and a banner such as "This application has been submitted and can no longer be edited" with a link to the Confirmation page. updateState writes to form sections must be ignored while status is Submitted.
  - 原因：Lever L09 (irreversible submit) depends on submission being final. Probed 2026-11-18 via ui_probe: after signing (status Submitted, signedDate 16:00:44Z) I changed Personal 1 marital status SINGLE→MARRIED from the sidebar and it reached server state with the status still Submitted. Today an agent that submits too early can quietly fix the data and re-sign, so 'submitted with wrong answers' is neither permanent nor observable.
- **visa_portal_ds160**（exp2-l09）：Immutable submission record. On successful Sign Application, write state.submission = {submittedAt, applicationId, confirmationNumber, data: deep copy of personalInfo, addressAndPhone, passport, travel, travelCompanions, previousUSTravel, usContact, family, workEducation, security, photo.photoUploaded, signature}, and append the same object to state.submissionHistory[] (array, default []). Neither may be changed by later actions. Show confirmationNumber and submittedAt on the Confirmation page.
  - 原因：The L09 verifier must grade what was actually submitted (the content of the first and only submission), not the live form. Today handleSign only sets signature.signedDate (overwritten by every re-sign) and status, and nothing records the submitted answers.
- **amazon_seller**（exp2-l13）：Per-listing minimum/maximum allowed price. Add products[].minimumSellerAllowedPrice and products[].maximumSellerAllowedPrice (number or null; default seed: null or a sensible band). Show both as columns in Manage Pricing (/pricing) and in Manage All Inventory (/inventory), editable inline like price, and document them in SCHEMA.md (Observable State Changes: inline edit writes the field and lastUpdated).
  - 原因：The L13 task's flat file carries minimum-seller-allowed-price / maximum-seller-allowed-price; for rows that are not yet effective the agent must carry the current values over from the listings report, so the mock must hold and report them. Today products[] has no such fields (checked SCHEMA.md and src/pages/Pricing.jsx, Inventory.jsx on 2026-11-18).
- **amazon_seller**（exp2-l13）：Inventory Reports page with a real file download. Route /reports/inventory (sidebar Reports > Inventory Reports, plus an 'Inventory reports' link on /inventory). Report type select with 'All Listings Report' (reportType 'all_listings', every product incl. Inactive/Suppressed) and 'Active Listings Report' ('active_listings', status Active only); 'Request report' appends state.inventoryReports[] = {id:'RPT_nnn', reportType, reportName, requestedAt, completedAt, status:'Done', fileName:'All+Listings+Report_MM-DD-YYYY.txt' (or Active+Listings...), rowCount}. Each Done row has a Download button that saves a UTF-8 tab-delimited .txt generated from current products, LF line endings, header exactly: seller-sku, asin1, item-name, price, minimum-seller-allowed-price, maximum-seller-allowed-price, quantity, fulfillment-channel, status. Values: sku, asin, title, price/min/max with two decimals (empty if null), availableQuantity (for FBA rows too), fulfillment-channel DEFAULT for FBM and AMAZON_NA for FBA, status. The download must reach the browser download manager (Blob + anchor without a remote href, or /files with Content-Disposition), not open in a tab. Default state: inventoryReports: [].
  - 原因：Lever L13 is a file round trip that starts by downloading Seller Central's listings report; the mock has no report download at all today (grep for download/Blob in src finds nothing; /orders/reports is a placeholder InsightsPage).
- **amazon_seller**（exp2-l13）：Inventory file upload stored server-side. Route /inventory/upload ('Add Products via Upload' with an 'Upload your inventory file' tab; link from sidebar Catalog and from /inventory). Controls: file type select ('Price & Quantity file' -> 'price_quantity', 'Inventory Loader' -> 'inventory_loader', 'Listing Loader' -> 'listing_loader'), a file input accepting .txt,.tsv,.csv,.xls,.xlsx, and an Upload button that POSTs multipart/form-data to /upload?sid=<sid> (same contract as yahoo_mail_mock attachments.jsx uploadFiles: response {files:[{original_name, stored_name, size, content_type, url}]}) and on success appends state.inventoryFileUploads[] = {id:'UPL_nnn', fileType, fileName: original_name, storedName: stored_name, url, size, contentType, uploadedAt (ISO), status:'Done', recordsProcessed: number of non-empty lines after the first}. A 'Monitor upload status' table lists uploads newest first (date, batch id, file name, file type, status, records processed) with a link to download the uploaded file. The upload must NOT parse/apply the file to products (the grader reads the stored file itself), must not validate delimiter/columns, and must keep every upload (no overwrite). Default state: inventoryFileUploads: []. Document both new keys and the action->field mapping in SCHEMA.md.
  - 原因：L13 grades the content of the file the agent uploads back to Seller Central, read from /var/lib/cua/files/amazon_seller/<sid>/<stored_name> via inventoryFileUploads[-1].url. The only file input in the mock today is the product image dropzone in ProductForm.jsx, which never calls /upload.
- **youtube**（exp2-l15）：Per-video publishing state in the data model. Add to every videos[] entry: visibility ('public'|'unlisted'|'private', default 'public'), publishAt (ISO8601|null; when set and in the future relative to the page clock the video is Scheduled and becomes public at that time), isPremiere (bool, default false) with premiereAt (ISO8601|null), and uploadStatus ('processed'|'draft', default 'processed'; a draft has its details unfinished and was never published). Derived effective status, computed against the in-page Date (the task clock): draft > private > scheduled (publishAt > now) > premiere-upcoming (isPremiere && premiereAt > now) > unlisted > public. Seed arrays must keep these fields; deepMergeWithDefaults/array normalizers must not drop them.
  - 原因：Lever L15 (status illusion) needs launch-week videos that look published elsewhere (Notion tracker says Published, a Slack message says 'it's up', a notification says 'uploaded') but are really scheduled, private, unlisted, unfinished drafts or upcoming premieres. Today a video has only uploadDate; visibility is written by UploadPage.addUploadedVideo but never read anywhere, and there is no schedule/premiere/draft concept at all.
- **youtube**（exp2-l15）：YouTube Studio channel-content page for the signed-in user (e.g. route /studio/videos, reachable from the avatar menu 'YouTube Studio' and the sidebar 'Your videos'). A table of the current user's videos (channelId == user.userId), including non-public ones, with columns Video (thumbnail+title+description snippet), Visibility (Public / Unlisted / Private / Scheduled / Draft), Date (e.g. 'Published Nov 16, 2026', 'Scheduled Nov 21, 2026, 9:00 AM', 'Premieres Nov 19, 2026, 6:00 PM', 'Uploaded Nov 17, 2026' for drafts), Views, Comments, Likes. Draft rows show an 'Edit draft' button instead of stats. Filter chips or a tab for Videos/Shorts/Live are optional; a visibility filter is nice-to-have.
  - 原因：The channel manager's ground truth for 'is this really live' is Studio. Without it the true state of each launch video cannot be read from the UI, so the Notion status column and the X promotion decision cannot be derived honestly.
- **youtube**（exp2-l15）：Public surfaces honour the effective status. HomePage, ChannelPage (Videos/Home tabs), SearchPage, SubscriptionsPage, TrendingPage and the watch-page suggestions list only effective-public videos; ChannelPage additionally shows an 'Upcoming' shelf for upcoming premieres with 'Premieres <date time>' instead of view count. Watch page /watch/:id: for the channel owner viewing a non-public own video show a visibility chip under the title ('Private', 'Unlisted', 'Scheduled for <date time>', 'Draft'); for an upcoming premiere show the premiere waiting room ('Premieres <date time>', countdown, no views, player not playable); unlisted videos open normally by direct link but are not listed anywhere. Home/Channel cards must also stop showing 'Today' for future uploadDate values.
  - 原因：L15 traps rely on deceptive-but-visible signals: a scheduled video whose thumbnail appears on the owner's channel or that opens fine by link, an unlisted video reachable from a pasted link, a premiere whose watch page exists. The real UI distinguishes these with chips/labels; today every video is listed and playable everywhere and future dates render as 'Today'.
- **youtube**（exp2-l15）：Edit visibility from Studio. A video details page (e.g. /studio/video/:id) or row 'Visibility' dropdown that lets the owner set Public / Unlisted / Private, or Schedule with a date+time picker, then Save; persists videos[i].visibility and videos[i].publishAt (null when made public now; publishing a draft sets uploadStatus 'processed' and uploadDate to now). Observable change: videos[i].visibility / publishAt / uploadStatus.
  - 原因：The task should include one YouTube write tied to the lever: a video the Slack thread says must go public at launch but that was left Unlisted (to be made Public), while a different one is correctly held as Scheduled and must not be touched. Without an edit path YouTube is read-only and the scheduled-vs-public decision cannot be persisted on the primary site.
- **docusign**（exp2b-l09）：Reopen a draft envelope for editing from the UI (Edit/Continue button on the draft EnvelopeDetail page; Drafts-list row click for status=draft opens /prepare/:id)
  - 原因：ui_probe 2026-11-18: in Agreements > Drafts, clicking 'Halvorsen ... Catering Agreement' opens /agreements/detail/env_hb_catering, which offers only Void and Download. The task's core work is fixing Theo's seeded drafts (document, client signer, vendor signer, message) before sending, and /prepare/:id is reachable only by typing the URL by hand.
- **docusign**（exp2b-l09）：Lock sent envelopes. PrepareEnvelope must refuse (redirect to detail or read-only with a banner like 'This envelope has been sent. Void it and send a new one, or use Correct to change recipients.') when status != 'draft'; the store's updateEnvelope must ignore documents/recipients/fields/subject/message changes for non-draft envelopes; the Send button must not appear for non-drafts
  - 原因：ui_probe 2026-11-18: /prepare/env_hb_shuttle (status 'delivered', sent by Theo) opened the full wizard with Send enabled. Changing the message to 'PROBE EDIT AFTER SEND (January 21-23, 2027)' landed in server state, and the status stayed 'delivered'. Lever L09 needs sending to be irreversible: the old shuttle envelope's wrong dates must only be fixable by void plus a new envelope, and a careless early send must leave a permanent record.
- **docusign**（exp2b-l09）：Immutable send snapshot. sendEnvelope writes envelope.sentSnapshot = {sentAt, subject, message, documents:[{id,name,fileSize,storedName}], recipients:[{id,name,email,role,routingOrder}]} once (never overwritten) and copies it into the history 'sent' event as `snapshot`. correctEnvelope's 'corrected' history event records `before` and `after` recipient arrays. voidEnvelope stores envelope.voidReason
  - 原因：ui_probe 2026-11-18: sending env_hb_photo through the wizard set status/sentAt and appended history {action:'sent', details:'Envelope sent to 2 recipient(s)'} with no snapshot. Correct overwrote recipients ('Jonah Reyes' became 'Jonah Reyes X') and logged only 'Envelope corrected - recipients updated'. Void kept the reason only inside history details. Without a snapshot, 'send to Greg, then Correct to Priya' looks the same as a correct first send, so the core L09 checks (C1-C3, C5, C9 in rubric.json) cannot be verified.
- **docusign**（exp2b-l09）：History/audit actor from state.user. createEnvelope/sendEnvelope/voidEnvelope/correctEnvelope/resendEnvelope history and auditLog entries use state.user.name/email instead of the hardcoded 'Sarah Chen <sarah.chen@acmecorp.com>'; the Home 'My DocuSign ID' signature placeholder uses state.user.name
  - 原因：ui_probe 2026-11-18: with seed user Nadia Okafor <nadia.brightlineevents@yahoo.com>, the sent, voided and corrected events written through the UI all had actorName 'Sarah Chen'. The Home card's signature preview also reads 'Sarah Chen'. The task tells apart Theo's earlier send from the agent's actions by actor, and the wrong name breaks the persona.
- **docusign**（exp2b-l09）：'Send an Envelope' starts with no documents. Home handleSendEnvelope/createEnvelope should not inject the placeholder picsum 'Document.pdf'; the wizard should open on step 1 when documents is empty
  - 原因：ui_probe 2026-11-18: Home > Start > Send an Envelope created an envelope with a 1-page 'Document.pdf' already attached and jumped to step 2 (Add Recipients). An agent building the replacement shuttle envelope can easily send that junk file next to, or instead of, the v2 PDF, which fails C5 for a reason unrelated to the task. The file can be deleted by hand, but it is a UI artifact.
- **docusign**（exp2b-l09）：Render PDF documents (uploaded data: URLs and /files/... URLs with fileType 'pdf') in the Prepare 'Place Fields' canvas and the SigningRoom via <iframe>/<object> or pdf.js, instead of <img src=fileUrl>
  - 原因：ui_probe 2026-11-18: after uploading /workspace/downloads/Pacific_Shuttle_Agreement_HBLS27_v2.pdf (stored correctly: name kept, fileSize 2443, contentType application/pdf), step 3 showed a broken <img alt='Document'> on a blank page. The agent cannot see which contract version is on the envelope before the irreversible send, and checking the attached version is the point of the task.
- **airtable**（exp2b-l09）：Date-only fields shown in local time. Cell.jsx renders `new Date(value).toLocaleDateString()` for 'YYYY-MM-DD'; parse date-only values as local dates (e.g. new Date(y, m-1, d)) or format the string directly
  - 原因：ui_probe 2026-11-18 (browser TZ America/Los_Angeles): Deposit Due stored as '2026-11-20' displays as 11/19/2026 and '2026-12-01' as 11/30/2026. The stored value is right (the editor is <input type=date>), but an agent that enters Dec 8 for the reissued shuttle contract sees 12/7/2026 and may 'fix' it to Dec 9, failing A3 because of a UI bug.
