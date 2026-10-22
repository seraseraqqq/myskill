# Track B: Emerging Demand Research

Use this process to discover emerging game concepts. A rising query is a research lead, not proof of durable demand, monthly volume, ranking opportunity, or a viable standalone site.

## 1. Collect Signals

The current helper is `scripts/trends_pull.py`:

```bash
cd /path/to/GameHubs/.agents/skills/sep-sop/scripts
python trends_pull.py --roots "browser game,puzzle game,snake game" --days 7 --out /tmp/rising.json
```

Use a small relevant root set first. `--all` can make many requests; use it only when needed and inspect its rate-limit/error output. The script uses an undocumented Trends web endpoint, so results may be partial, delayed, or unavailable. It currently hard-codes the US market; do not use its results as evidence for another country. Save the collection date, roots, market, and errors with the result. Do not describe Trends index values as search volume.

## 2. Triage the Query

For each candidate, record:

- What the query appears to mean and whether it describes a playable game, a brand, a current event, a code/answer lookup, or something else.
- The likely player and the exact task they want to complete.
- Whether the need is recurring or likely to disappear with the event/trend.
- Whether the proposed game can satisfy the intent legally and with a real product difference.
- Any uncertainty or conflicting interpretations.

Filter irrelevant or unsuitable queries with a reason, but do not use a fixed expected rejection percentage. Save retained and rejected terms separately if using `library.py merge`:

```bash
python library.py merge --rising /tmp/rising_clean.json --dropped /tmp/rising_dropped.json
```

Each retained item should include a concise `note`; each rejected item should include a `reason`. Preserve ambiguous terms as `observe`/review candidates rather than making unsupported claims.

## 3. Validate Before Planning a Page

For promising terms, inspect a fresh Google SERP for the intended country/language and device. Record date, query, intent, dominant result types, competing pages, and whether the results actually satisfy the need. Confirm trend-only candidates through Search Console, another keyword source, related searches, or repeated observations when possible.

Use volume and KD only as estimates when the source supplies them. Low or missing volume on a new query is not proof of opportunity; low KD is not sufficient reason to build. A SERP with no dedicated game is a possible clue, not automatically a product or content gap. Decide whether the game can be more useful than the current results and what evidence will test that hypothesis.

When a candidate passes initial triage, the existing pipeline can expand and record it. DataForSEO calls are paid; use a small `--max-expand` and `--top-serp` first, then rerun with `--allow-paid` only after reviewing expected spend:

```bash
python mine_round.py --track new --from-rising /tmp/rising_clean.json --max-expand 10
```

Start with a small `--max-expand`. Set `DATAFORSEO_LOGIN` and `DATAFORSEO_PASSWORD`, confirm the location/language and external ledger path, and approve the expected API spend. `--allow-paid` explicitly enables billing but cannot enforce a dollar ceiling; review response costs and DataForSEO account usage. A request timeout is not automatically retried because the provider may already have processed and billed it.

The pipeline's evidence export can be reviewed and fed into its judge step. Keep decisions evidence-based and ensure the exact candidate key and allowed fields match the script contract:

```bash
python mine_round.py --judge /tmp/verdicts_YYYY-MM-DD.json
```

Do not judge from a summary alone when the SERP evidence file is available. Mark fields unknown when evidence is insufficient. Do not let the model invent volume, competition, user pain, or game mechanics.

## 4. Prioritize and Report

Rank candidates using a short written rationale across:

- Intent fit: is a playable game the expected answer?
- Demand evidence: Trends shape plus independent/current-market confirmation.
- Product gap: a concrete missing or better experience, not merely weak-looking competitors.
- Rights and feasibility: game/code/assets/name are usable and adaptation cost is acceptable.
- Portfolio fit: does this strengthen an existing site or justify a separate brand/domain?
- Testability: can a small release produce a measurable signal within the available budget/time?

Each research report should list the source/date/market, candidate and interpretation, evidence, uncertainty, proposed test, expected cost, and `build`, `observe`, or `reject` recommendation. Do not present candidate count, a Trends breakout label, or an AI verdict as forecast traffic or revenue.
