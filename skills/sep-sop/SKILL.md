---
name: sep-sop
description: "Plan, validate, build, and operate SEO-focused browser-game sites. Use for game-site keyword research, a single-site build, or a measured multi-site portfolio; do not treat deployment or indexing as a promise of traffic or revenue."
---

# SEP-SOP: Browser-Game Site Validation and Operations

Use this workflow to find a real search need, ship a useful and legally usable browser game, and decide from observed results whether to expand. The business objective is sustainable, policy-compliant revenue, not a site-count target by itself. A five-month/200-site target is a capacity constraint to test, not a guarantee or a reason to bypass release gates.

## Operating Rules

- Define the unit before planning: an independent domain, a branded site, a game, and an indexable URL are different units. Prefer related games as genuinely useful pages on a coherent site unless a separate brand/domain has a distinct audience, product, or business case.
- Start with a small pilot and expand in cohorts only after quality, discoverability, engagement, and monetization evidence supports it. See [portfolio-gates.md](references/portfolio-gates.md).
- Do not create near-identical doorway sites/pages, fabricate FAQs or product claims, or use random cross-domain footer links to pass ranking signals. Interlink relevant pages naturally within a site. Cross-site links must have a genuine editorial/user purpose.
- Never claim that a page will rank, be indexed, earn revenue, bypass a school/network policy, or achieve a fixed Core Web Vitals/TTFB score. Report observations, date, market, and uncertainty.
- Preserve the original project's license and attribution. Verify the license, assets, game name, trademarks, and permission to distribute/monetize before adapting a game. Do not remove required attribution or disguise an unauthorized clone as the official game.
- Keep ad code off during development. Before enabling ads, verify the current ad-network policies, site approval status, privacy/consent requirements, and placement distance from game controls. Do not place content ads inside the playable game surface.
- Treat deployment, domain purchase, public repository creation, paid research/API calls, and production changes as separate actions. Do not perform them without the user's explicit authorization for that action and any required cost ceiling.

## Workflow

### 1. Establish the business hypothesis

Record the intended audience and country/language, the game experience, the proposed URL/domain unit, the acquisition channel, likely monetization route, budget/time limits, and the success and stop criteria. If the user has not decided whether they mean 200 domains or 200 game pages, explain the trade-off and use a small page/site pilot rather than assuming 200 domains.

Estimate the workload honestly: include research, rights review, gameplay adaptation, responsive QA, deployment, Search Console setup, ad approval, maintenance, and weekly measurement. Do not equate a successful build with a successful business experiment.

### 2. Research one demand hypothesis at a time

Use the relevant procedure in [sop-new-words.md](references/sop-new-words.md) or [sop-old-words.md](references/sop-old-words.md). Inspect current SERPs for the target market and device; record the date, intent, result types, competing solutions, and what the proposed game will do better or differently.

Use Trends as a discovery signal, not as search volume or proof of durable demand. Validate promising candidates with a second source or live SERP evidence. Keyword volume, KD, DR/UR, and AI judgments are estimates and clues, not launch permission. Cluster queries with substantially the same intent into one useful page; do not create one page per spelling or modifier.

Before running local keyword scripts, inspect their configuration and `--help`. `scripts/mine_round.py` reads DataForSEO credentials from `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`; market defaults are `DATAFORSEO_LOCATION_CODE=2840` and `DATAFORSEO_LANGUAGE_CODE=en`. It also defaults the ledger to an absolute path outside this skill, configurable with `KEYWORD_LEDGER`. Every DataForSEO workflow requires explicit `--allow-paid`; inspect the exact scope and obtain approval for expected spend first. The flag is an opt-in, not a hard dollar cap: actual endpoint charges are only known from the API response. `--trends-only` avoids DataForSEO, but its volume and SERP proxies are not substitutes for measured search volume or live SERPs. The Trends script uses an undocumented endpoint and is best-effort.

DataForSEO is the paid research source: Labs Keyword Ideas for expansion, Labs Ranked Keywords for competitor discovery, Google Ads Search Volume for volume/monthly history, Labs Bulk Keyword Difficulty for KD, Google Organic SERP for live results, and Backlinks Summary for referring-domain/backlink counts. These metrics are not interchangeable with Ahrefs DR. The API client deliberately does not automatically retry uncertain paid POST requests; check the DataForSEO dashboard before retrying a timed-out request.

### 3. Decide the site and game scope

Prefer a focused site architecture that groups related games and provides clear navigation, original value, and sensible internal links. Use separate sites only when the distinct audience/brand/domain benefit justifies the extra acquisition, maintenance, trust, and measurement cost.

Choose a game implementation only after checking license compatibility, attribution, dependencies, assets, input controls, mobile behavior, keyboard/accessibility needs, performance, and monetization rights. A permissive code license does not automatically grant rights to a game's name, characters, artwork, music, or third-party services.

Make the experience materially useful: reliable play, clear controls, responsive layout, fast first interaction, and truthful supporting information. Do not impose a universal word-count cap or viewport percentage. Keep copy concise when it helps players, but include the details necessary to resolve the query and build trust. Use FAQ only for real, answerable questions, not keyword repetition.

### 4. Build with the simplest suitable architecture

Static HTML/CSS/JavaScript is a good default for a self-contained game, not an absolute ban on backend services. Add a service only when a validated feature requires it and its cost, privacy, uptime, and maintenance are understood. Use `localStorage` for local preferences/high scores where appropriate; do not imply it syncs between devices or prevents cheating.

Use semantic HTML, responsive controls, descriptive page titles, a single accurate H1, canonical URLs, Open Graph metadata, and a sitemap/robots file when the site structure warrants them. Add structured data only when it truthfully describes visible page content; valid schema is not a ranking guarantee. Keep game assets local where licensing permits and avoid unnecessary third-party requests.

### 5. Verify before release

Follow [aesthetic-checklist.md](references/aesthetic-checklist.md) as a quality guide, not a rigid design formula. Before a production deployment, confirm:

- The game starts, restarts, pauses (if applicable), scores, and handles invalid/end states correctly.
- Desktop and mobile layouts work; touch, keyboard, focus, and reduced-motion behavior are checked where relevant.
- There are no console errors, broken assets, accidental external calls, inaccessible controls, or misleading claims.
- License, attribution, domain ownership/configuration, canonical URL, indexability, sitemap, and robots behavior are reviewed.
- A production build passes the project's available tests and is smoke-tested at its final URL. Record what was tested; do not report unrun checks as passed.
- Ads remain disabled until the chosen network approves the site and placements have been checked against its current policies.

If any blocking item fails, do not mark the site ready. Fix it, narrow scope, or record the blocker and ask the user before proceeding with a material product, cost, rights, or production decision.

### 6. Measure and decide whether to expand

Register and verify the property in Search Console and analytics when authorized and available. Track each cohort by launch date and market: build/maintenance cost, index coverage, organic impressions/clicks, engaged play or equivalent interaction, ad approval/policy status, revenue, and revenue per session/page where data exists. Separate missing data from zero performance.

Review at a consistent interval and compare like with like. First diagnose crawl/indexing, query fit, page usefulness, game engagement, and policy constraints; then decide to improve, hold, or stop. Expand only when a cohort has repeatable evidence and the marginal maintenance/economic case remains acceptable. If ranking or revenue has not matured within five months, report that plainly; do not manufacture success from deploy count.

## Output

For research-only work, deliver the evidence, assumptions, recommended experiment, and cost/rights risks without creating external resources. For a build, deliver the working site, test results, license/asset notes, SEO configuration, deployment instructions, and unresolved risks. For portfolio work, report sites/pages by status and cohort, key outcome metrics, spend, failures, and the next expand/hold/stop decision.

## References

- [Portfolio plan and stage gates](references/portfolio-gates.md)
- [New/trending keyword research](references/sop-new-words.md)
- [Established keyword research](references/sop-old-words.md)
- [Practical execution notes](references/execution-notes.md)
- [Visual and functional QA](references/aesthetic-checklist.md)
- [Design references](references/reference-sites.md)
