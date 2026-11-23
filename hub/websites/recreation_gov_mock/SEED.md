# Recreation.gov — build brief

To show an optional visitor notice, set `"uiPrompts": { "visitorNotice": { "enabled": true, "path": "/explore", "id": "seasonal-access", "message": "Check destination details for seasonal road closures." } }` on the site seed. The path defaults to `/explore`. Dismissal persists through reload in the same browser session and leaves reservation records untouched.

- Real product: Recreation.gov (https://www.recreation.gov). Mock directory: `websites/recreation_gov_mock`.
- Scenario: 公共事务; tier A (core mainstream: highest fidelity).
- Must-have workflows (each is P0/P1 and must persist structured records): campsite/permit reservations, lotteries, cancellations.
- Runtime contract: follow `HARBOR_CONTRACT.md` and use `templates/state-api.js` + `templates/dataManager.js` as-is.
- Dev server port for this app: 5515 (other apps are built in parallel; never use another port).
- Default data (`createInitialData`): realistic, English, fixed ids, enough volume to make
  lists, filters and search meaningful (dozens of records per main entity).
