# Practical Execution Notes

## Portfolio and SEO

- A domain, site, game, and indexable page are separate portfolio units. Record which one the target count refers to.
- Trends detects movement in its own normalized series; it is not a direct monthly search-volume estimate. Confirm a candidate with current-market SERPs and, where available, a second keyword source.
- SERP evidence is time- and location-sensitive. Save the query, country/language, device, date, top result types/domains, and intent. Use difficulty metrics as directional estimates, not deterministic thresholds.
- Prefer one useful URL for one intent cluster. Make pages distinct because they solve different user needs, not because their keyword strings differ.
- Use relevant, crawlable internal links within a site. Do not generate random cross-domain footer links, link wheels, or pages whose main purpose is passing ranking signals.
- IndexNow is an optional notification channel for participating search engines. A successful submission is not a guarantee of crawling, indexing, or ranking. Verify Google's discovery/index status through Search Console when available.

## Build and Rights

- Static delivery is a sensible default for a standalone game, but does not guarantee a fixed TTFB, Core Web Vitals score, ranking, zero cost, or zero maintenance.
- Use local persistence only for data that should remain on that browser/device. Explain limitations if the UI could imply account sync or competitive integrity.
- Record source repository, commit/release, license text, asset origins, required notices, modifications, and monetization permission. Check trademarks and non-code assets separately.
- Do not remove attribution or outbound notices that a license or upstream project requires.
- Avoid claims such as "official", "unblocked at school", "works everywhere", "100% safe", or guaranteed compatibility unless verified and authorized.

## Ads and Privacy

- Keep ads disabled until the site is eligible and the ad provider has approved it.
- Recheck the provider's current content, placement, consent, and traffic policies immediately before enabling ads. Keep content ads outside the interactive game surface and clear of controls.
- Do not fake gameplay, clicks, engagement, or traffic. Do not obscure game controls with ads or deceptive buttons.
- Determine whether cookies, analytics, personalized ads, or third-party embeds trigger privacy/consent obligations for the selected markets. Do not claim compliance without checking the current applicable requirements.

## Existing Local Tooling Caveats

- `scripts/trends_pull.py` calls an undocumented Google Trends web endpoint. It has no guaranteed API stability or service level; handle throttling/errors and keep the source/date with the result.
- `scripts/mine_round.py` uses DataForSEO direct API credentials from `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`; its market is configured by `DATAFORSEO_LOCATION_CODE` / `DATAFORSEO_LANGUAGE_CODE`. The keyword ledger defaults outside this skill directory; set `KEYWORD_LEDGER` explicitly when needed.
- DataForSEO calls are paid. Every paid workflow requires `--allow-paid`, but this is not a dollar cap: charges are reported after responses. Avoid unnecessary calls, keep `--max-expand` and `--top-serp` small, and reuse valid checkpoint/SERP evidence. A timed-out paid POST is not retried automatically; check provider usage before retrying.
- The optional competitor metric is referring-domain/backlink counts from DataForSEO, not Ahrefs DR or an equivalent authority score.
- The current skill directory contains keyword research scripts, not a complete game generator/deployment/analytics system. A described step is not automated unless an executable implementation exists and has been tested.
- Do not assume a scheduled automation is active just because a reference describes one. Verify the automation configuration and latest successful run before relying on it.

## Portfolio Ledger

Use the root `matrix-sites.json` as an inventory only; keep its records truthful and validate schema changes before writing. For each asset, track at minimum: stable ID, unit type, domain/URL, repo, primary intent, target market, game/source/license record, owner, created/deployed date, status, canonical/indexing state, ad approval state, analytics/Search Console connection state, costs, latest metrics date, and next decision. Never use `planned` as equivalent to deployed, indexed, or earning.

Use explicit states such as `idea`, `researching`, `rights-check`, `building`, `qa`, `deployed`, `indexing-observed`, `monetization-pending`, `earning`, `hold`, and `retired`. Record transition dates and failure reasons. Do not delete historical outcomes when retiring an asset.
