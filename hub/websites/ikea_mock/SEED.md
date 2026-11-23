# IKEA — build brief

To show the optional cookie preferences panel, set `"uiPrompts": { "privacy": { "enabled": true, "path": "/", "id": "account-entry" } }` on the site's seed. A browser session remembers the choice by session ID and prompt ID. Dismissing the panel does not update orders or cart data.

- Real product: IKEA (https://www.ikea.com). Mock directory: `websites/ikea_mock`.
- Scenario: 生活消费; tier A (core mainstream: highest fidelity).
- Must-have workflows (each is P0/P1 and must persist structured records): cart, delivery/assembly booking, returns.
- Runtime contract: follow `HARBOR_CONTRACT.md` and use `templates/state-api.js` + `templates/dataManager.js` as-is.
- Dev server port for this app: 5314 (other apps are built in parallel; never use another port).
- Default data (`createInitialData`): realistic, English, fixed ids, enough volume to make
  lists, filters and search meaningful (dozens of records per main entity).
