#!/usr/bin/env python3
"""Regenerate catalog/sites.json from the table below plus build/certify.json.

role:     scenario = counts toward the 7-scenario pool and de-duplication;
          common   = shared tool (mail/chat/docs/calendar) reusable across tasks.
status:   ready        English, static certification passed, brand restored
          needs_brand  UI still shows an invented brand (fix in hub before use)
          needs_sync   UI changes never reach the server (excluded until fixed)
          dyn_fail     failed dynamic certification in the task runtime (fix before use)
          zh           Chinese UI; batch is English-first, kept for later
origin_group: sites sharing an origin can't appear in the same task.
"""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CERT = HERE.parent / "build" / "certify.json"
DYN = HERE.parent / "build" / "dyn_certify.json"

# hub, brand, origin, scenario, role, flags
S, C = "scenario", "common"
LIFE, CULTURE, OFFICE, PRO, INDUSTRY, TECH, PUBLIC = "生活消费", "文化内容", "组织办公", "专业事务", "产业运营", "数字技术", "公共事务"
TABLE = [
    # ---- shared tools (common) ----
    ("gmail_mock", "Gmail", "https://mail.google.com", OFFICE, C, ""),
    ("outlook_web_mock", "Outlook", "https://outlook.office.com", OFFICE, C, ""),
    ("slack_mock", "Slack", "https://app.slack.com", OFFICE, C, ""),
    ("microsoft_teams_mock", "Microsoft Teams", "https://teams.microsoft.com", OFFICE, C, ""),
    ("google_calendar_mock", "Google Calendar", "https://calendar.google.com", OFFICE, C, ""),
    ("google_drive_mock", "Google Drive", "https://drive.google.com", OFFICE, C, ""),
    ("google_docs_mock", "Google Docs", "https://docs.google.com", OFFICE, C, ""),
    ("google_sheets_mock", "Google Sheets", "https://sheets.google.com", OFFICE, C, ""),
    ("notion_mock", "Notion", "https://www.notion.so", OFFICE, C, ""),
    ("zoom_web_mock", "Zoom", "https://app.zoom.us", OFFICE, C, ""),
    # ---- 生活消费 ----
    ("amazon_mock", "Amazon", "https://www.amazon.com", LIFE, S, ""),
    ("instacart_mock", "Instacart", "https://www.instacart.com", LIFE, S, ""),
    ("uber_eats_mock", "Uber Eats", "https://www.ubereats.com", LIFE, S, ""),
    ("booking_com_mock", "Booking.com", "https://www.booking.com", LIFE, S, ""),
    ("expedia_mock", "Expedia", "https://www.expedia.com", LIFE, S, "needs_brand"),
    ("google_flights_mock", "Google Flights", "https://www.google.com", LIFE, S, ""),
    ("tripadvisor_mock", "Tripadvisor", "https://www.tripadvisor.com", LIFE, S, ""),
    ("zillow_mock", "Zillow", "https://www.zillow.com", LIFE, S, ""),
    ("ebay_mock", "eBay", "https://www.ebay.com", LIFE, S, ""),
    ("paypal_mock", "PayPal", "https://www.paypal.com", LIFE, S, ""),
    ("robinhood_mock", "Robinhood", "https://robinhood.com", LIFE, S, ""),
    ("coinbase_mock", "Coinbase", "https://www.coinbase.com", LIFE, S, ""),
    ("TradingView_mock", "TradingView", "https://www.tradingview.com", LIFE, S, ""),
    ("epic-health_mock", "MyChart", "https://mychart.epic.com", LIFE, S, "needs_sync"),
    ("12306_mock", "12306", "https://www.12306.cn", LIFE, S, "zh"),
    # ---- 文化内容 ----
    ("youtube_mock", "YouTube", "https://www.youtube.com", CULTURE, S, ""),
    ("reddit_mock", "Reddit", "https://www.reddit.com", CULTURE, S, ""),
    ("twitter_mock", "X", "https://x.com", CULTURE, S, ""),
    ("instagram_mock", "Instagram", "https://www.instagram.com", CULTURE, S, ""),
    ("pinterest_mock", "Pinterest", "https://www.pinterest.com", CULTURE, S, ""),
    ("facebook_mock", "Facebook", "https://www.facebook.com", CULTURE, S, ""),
    ("linkedin_mock", "LinkedIn", "https://www.linkedin.com", CULTURE, S, ""),
    ("discord_mock", "Discord", "https://discord.com", CULTURE, S, ""),
    ("canva_mock", "Canva", "https://www.canva.com", CULTURE, S, ""),
    ("canvas_mock", "Canvas Editor", "https://editor.canvas.example", CULTURE, S, "needs_brand"),
    ("weibo_mock", "微博", "https://weibo.com", CULTURE, S, "zh"),
    ("xiaohongshu_mock", "小红书", "https://www.xiaohongshu.com", CULTURE, S, "zh"),
    ("zhihu_mock", "知乎", "https://www.zhihu.com", CULTURE, S, "zh"),
    ("wechat_mock", "微信", "https://wx.qq.com", CULTURE, S, "zh"),
    # ---- 组织办公 ----
    ("asana_mock", "Asana", "https://app.asana.com", OFFICE, S, ""),
    ("trello_mock", "Trello", "https://trello.com", OFFICE, S, ""),
    ("monday_mock", "monday.com", "https://acme.monday.com", OFFICE, S, ""),
    ("airtable_mock", "Airtable", "https://airtable.com", OFFICE, S, ""),
    ("confluence_mock", "Confluence", "https://acme.atlassian.net", OFFICE, S, ""),
    ("lucidchart_mock", "Lucidchart", "https://lucid.app", OFFICE, S, ""),
    ("miro_mock", "Miro", "https://miro.com", OFFICE, S, ""),
    ("lattice_mock", "Lattice", "https://acme.latticehq.com", OFFICE, S, ""),
    ("bamboohr_mock", "BambooHR", "https://acme.bamboohr.com", OFFICE, S, ""),
    ("workday_mock", "Workday", "https://wd5.myworkday.com", OFFICE, S, ""),
    ("adp_mock", "ADP Workforce Now", "https://workforcenow.adp.com", OFFICE, S, ""),
    ("gusto_mock", "Gusto", "https://app.gusto.com", OFFICE, S, ""),
    ("greenhouse_mock", "Greenhouse", "https://app.greenhouse.io", OFFICE, S, ""),
    ("Expensify_mock", "Expensify", "https://new.expensify.com", OFFICE, S, ""),
    ("docusign_mock", "DocuSign", "https://app.docusign.com", OFFICE, S, ""),
    ("dingtalk_mock", "钉钉", "https://im.dingtalk.com", OFFICE, C, "zh"),
    ("feishu_mock", "飞书", "https://www.feishu.cn", OFFICE, C, "zh"),
    # ---- 专业事务 ----
    ("clio_mock", "Clio", "https://app.clio.com", PRO, S, ""),
    ("westlaw_mock", "Westlaw", "https://1.next.westlaw.com", PRO, S, ""),
    ("contractbook_mock", "Contractbook", "https://app.contractbook.com", PRO, S, ""),
    ("quickbooks_mock", "QuickBooks", "https://qbo.intuit.com", PRO, S, ""),
    ("Canvas-LMS_mock", "Canvas LMS", "https://canvas.instructure.com", PRO, S, ""),
    ("openreview_mock", "OpenReview", "https://openreview.net", PRO, S, ""),
    ("PACS-viewer_mock", "PACS Viewer", "https://pacs.hospital.example", PRO, S, "needs_sync"),
    # ---- 产业运营 ----
    ("shopify_admin_mock", "Shopify", "https://admin.shopify.com", INDUSTRY, S, ""),
    ("amazon_seller_mock", "Amazon Seller Central", "https://sellercentral.amazon.com", INDUSTRY, S, ""),
    ("woocommerce_mock", "WooCommerce", "https://greenleaforganics.com", INDUSTRY, S, ""),
    ("salesforce_mock", "Salesforce", "https://acme.lightning.force.com", INDUSTRY, S, ""),
    ("hubspot_mock", "HubSpot", "https://app.hubspot.com", INDUSTRY, S, ""),
    ("hubspot_marketing_mock", "HubSpot Marketing Hub", "https://app.hubspot.com", INDUSTRY, S, ""),
    ("SAP_mock", "SAP S/4HANA", "https://my-s4hana.cloud.sap", INDUSTRY, S, ""),
    ("ServiceNow_mock", "ServiceNow", "https://acme.service-now.com", INDUSTRY, S, ""),
    ("Zendesk_mock", "Zendesk", "https://acme.zendesk.com", INDUSTRY, S, ""),
    ("stripe_dashboard_mock", "Stripe", "https://dashboard.stripe.com", INDUSTRY, S, ""),
    ("mailchimp_mock", "Mailchimp", "https://us1.admin.mailchimp.com", INDUSTRY, S, ""),
    ("klaviyo_mock", "Klaviyo", "https://www.klaviyo.com", INDUSTRY, S, ""),
    ("google_ads_mock", "Google Ads", "https://ads.google.com", INDUSTRY, S, ""),
    ("meta_ads_mock", "Meta Ads Manager", "https://adsmanager.facebook.com", INDUSTRY, S, ""),
    ("google_analytics_mock", "Google Analytics", "https://analytics.google.com", INDUSTRY, S, ""),
    ("amplitude_mock", "Amplitude", "https://app.amplitude.com", INDUSTRY, S, ""),
    ("mixpanel_mock", "Mixpanel", "https://mixpanel.com", INDUSTRY, S, ""),
    ("hotjar_mock", "Hotjar", "https://insights.hotjar.com", INDUSTRY, S, ""),
    ("looker_studio_mock", "Looker Studio", "https://lookerstudio.google.com", INDUSTRY, S, ""),
    ("tableau_mock", "Tableau", "https://online.tableau.com", INDUSTRY, S, ""),
    ("taobao_seller_mock", "淘宝卖家中心", "https://myseller.taobao.com", INDUSTRY, S, "zh"),
    # ---- 数字技术 ----
    ("github_mock", "GitHub", "https://github.com", TECH, S, ""),
    ("gitlab_mock", "GitLab", "https://gitlab.com", TECH, S, ""),
    ("jira_mock", "Jira", "https://acme.atlassian.net", TECH, S, ""),
    ("linear_mock", "Linear", "https://linear.app", TECH, S, ""),
    ("circleci_mock", "CircleCI", "https://app.circleci.com", TECH, S, ""),
    ("vercel_mock", "Vercel", "https://vercel.com", TECH, S, ""),
    ("cloudflare_mock", "Cloudflare", "https://dash.cloudflare.com", TECH, S, ""),
    ("aws_console_mock", "AWS Console", "https://console.aws.amazon.com", TECH, S, ""),
    ("azure_mock", "Microsoft Azure", "https://portal.azure.com", TECH, S, ""),
    ("datadog_mock", "Datadog", "https://app.datadoghq.com", TECH, S, ""),
    ("sentry_mock", "Sentry", "https://acme.sentry.io", TECH, S, ""),
    ("postman_mock", "Postman", "https://web.postman.co", TECH, S, ""),
    ("wandb_mock", "Weights & Biases", "https://wandb.ai", TECH, S, ""),
    ("aliyun_mock", "阿里云", "https://home.console.aliyun.com", TECH, S, "zh"),
    # ---- 公共事务 ----
    ("visa_portal_ds160_mock", "DS-160 (CEAC)", "https://ceac.state.gov", PUBLIC, S, ""),
    ("usa-gov_mock", "USAGov", "https://www.usa.gov", PUBLIC, S, "needs_sync"),
    ("california_tax_mock", "CalFile (FTB)", "https://webapp.ftb.ca.gov", PUBLIC, S, ""),
]

NAMES = {"shopify_admin_mock": "shopify"}  # keys already used by packaged tasks

# Gaps to build with the hub pipeline (English-first); 公共事务 is the thinnest.
PLANNED = [
    ("city311_mock", "NYC311", "https://portal.311.nyc.gov", PUBLIC, "service requests, case status, agency routing"),
    ("dmv_mock", "California DMV", "https://www.dmv.ca.gov", PUBLIC, "appointments, registration renewal, address change"),
    ("irs_mock", "IRS Online Account", "https://sa.www4.irs.gov", PUBLIC, "balances, payment plans, notices, transcripts"),
    ("permits_mock", "Accela Citizen Access", "https://aca-prod.accela.com", PUBLIC, "building permits, inspections, fees"),
    ("courts_mock", "Odyssey eFileCA", "https://california.tylertech.cloud", PUBLIC, "e-filing, case lookup, hearing dates"),
    ("medicare_mock", "Medicare.gov", "https://www.medicare.gov", PUBLIC, "plan comparison, claims, enrollment"),
    ("library_mock", "BiblioCommons", "https://sfpl.bibliocommons.com", PUBLIC, "holds, renewals, fines, events"),
]


def add_mock_releases(sites, dyn):
    """Register accepted releases from immutable Hub revisions."""
    candidates = json.loads((HERE / "candidates.json").read_text())
    by_brand = {candidate["brand"]: (scenario, candidate)
                for scenario, group in candidates.items() for candidate in group["new"]}
    releases = json.loads((HERE / "mock_releases.json").read_text())
    for release in releases:
        revision = release["revision"]
        for name, brand in release["sites"].items():
            scenario, candidate = by_brand[brand]
            origin = candidate["origin"]
            entry = sites.get(name, {
                "hub": f"{name}_mock", "brand": brand, "origins": [origin], "home": origin + "/",
                "role": C if scenario == "公共工具" else S, "scenario": scenario, "locale": "en",
                "tier": release["tier"], "new": True,
            })
            result = dyn.get(name, {})
            failed = (result.get("hub_revision") == revision
                      and not all(result.get(check) for check in ("render", "sync", "idle", "hydrate")))
            sites[name] = {**entry, "hub_revision": revision, "status": "dyn_fail" if failed else "ready"}
            if name in release.get("overlays", {}):
                sites[name]["default_overlay"] = release["overlays"][name]


def main():
    cert = json.loads(CERT.read_text()) if CERT.exists() else {}
    dyn = json.loads(DYN.read_text()) if DYN.exists() else {}
    catalog = HERE / "sites.json"
    previous = json.loads(catalog.read_text())["sites"] if catalog.exists() else {}
    sites = {}
    for hub, brand, origin, scenario, role, flag in TABLE:
        name = NAMES.get(hub) or hub.lower().removesuffix("_mock").replace("-", "_")
        c = cert.get(hub)
        d = dyn.get(name)
        if flag:
            status = flag
        elif c is not None and not c.get("pass"):
            status = "uncertified"
        else:
            prior = previous.get(name, {})
            status = prior["status"] if prior.get("hub") == hub else "uncertified"
            if c is not None and status != "dyn_fail":
                status = "ready"
            if d and (c is not None or status in {"ready", "dyn_fail"}):
                passed = d["render"] and d["sync"] and d["idle"] and d.get("hydrate", True)
                status = "ready" if passed else "dyn_fail"
        sites[name] = {"hub": hub, "brand": brand, "origins": [origin], "home": origin + "/", "role": role,
                       "scenario": scenario, "locale": "zh" if flag == "zh" else "en", "status": status}
    sites["shopify"]["patches"] = ["structured refunds[] with per-line quantities"]
    # Mocks accepted by hub_tools/build_mocks.py (high-fidelity, contract-compliant).
    built = HERE / "built_sites.json"
    for name, b in (json.loads(built.read_text()) if built.exists() else {}).items():
        sites[name] = {"hub": b["hub"], "brand": b["brand"], "origins": b["origins"], "home": b["origins"][0] + "/",
                       "role": C if b["scenario"] == "公共工具" else S, "scenario": b["scenario"], "locale": "en",
                       "tier": b["tier"], "new": True,
                       "status": "ready" if cert.get(b["hub"], {}).get("pass", True) else "uncertified"}
    add_mock_releases(sites, dyn)
    groups = {}
    for name, site in sites.items():
        for origin in site["origins"]:
            groups.setdefault(origin, []).append(name)
    for origin, names in groups.items():
        if len(names) > 1:
            for name in names:
                sites[name]["origin_group"] = origin
    out = {"_doc": __doc__.strip(), "sites": sites,
           "planned": [{"hub": h, "brand": b, "origins": [o], "scenario": s, "role": S, "scope": d, "status": "planned"}
                       for h, b, o, s, d in PLANNED]}
    catalog.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    summary = {}
    for s in sites.values():
        key = (s["scenario"] if s["role"] == S else "公共工具", s["status"])
        summary[key] = summary.get(key, 0) + 1
    for (scenario, status), n in sorted(summary.items()):
        print(f"{scenario:8} {status:12} {n}")


if __name__ == "__main__":
    main()
