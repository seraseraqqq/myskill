# Track A: Established Query and Competitor Research

Use this process for queries with an established history or for competitor-based discovery. The script can collect metrics and SERP evidence; the model can classify evidence and identify uncertainty. Neither replaces product judgment.

## 1. Discover Candidates

Seed workflow:

```bash
python mine_round.py --track old --seeds "snake game,puzzle game"
```

Competitor workflow:

```bash
python mine_round.py --track old --competitor example.com
```

The script supports related terms, competitor ranking terms, keyword metrics, and SERP evidence through DataForSEO. Inspect `--help` and settings first. Configure `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, `DATAFORSEO_LOCATION_CODE` (default `2840`), and `DATAFORSEO_LANGUAGE_CODE` (default `en`). The ledger path defaults outside the skill and can be set with `KEYWORD_LEDGER`. Calls are paid and require `--allow-paid`; that flag is not a dollar cap, so approve expected scope/spend and inspect actual response costs. Prefer `--backlinks-check` only when backlink counts will materially affect the decision; it returns referring domains/backlinks, not Ahrefs DR.

## 2. Cluster by Intent

Inspect candidate SERPs in the intended market/device. Group query variants when the same pages and user task dominate. Keep separate URLs only when there is a meaningfully distinct intent and a page can satisfy it better. Modifiers such as `online`, `free`, `unblocked`, and year suffixes are hypotheses to verify, not automatic page templates.

Classify the search task as play/use, learn, compare, find a specific official product, get an answer, or another concrete intent. Record result types, SERP date/market, and whether current results satisfy the task. Do not infer a site opportunity solely from high volume, low KD, weak-looking domains, or an absent exact-match page.

## 3. Judge Evidence

The existing pipeline exports SERP evidence to `.km_checkpoints/`. Reuse the evidence while it is still representative; fetch again when market/device/date materially changes or the old file is missing.

For each candidate, fill the script's verdict JSON contract:

```json
{
  "items": {
    "snake game online": {
      "tier": "直接解决",
      "gap": "质量缺口",
      "verdict": "观察",
      "reason": "SERP contains several playable versions; a specific unmet need has not yet been demonstrated.",
      "c1": "工具页",
      "c2": "游戏",
      "c3": "keyboard-accessible controls",
      "ai_overview": false
    }
  }
}
```

Allowed `tier`: `直接解决`, `方案之一`, `受众重叠`, `无关`.

Allowed `gap`: `无缺口`, `工具缺口`, `内容缺口`, `质量缺口`.

Allowed `verdict`: `立项`, `观察`, `砍掉`.

Use `工具缺口` only when evidence indicates users want a tool/game and existing results do not provide it; absence of a dedicated result alone is insufficient. For `质量缺口`, cite a specific shortcoming visible in the results or reproducible by testing. If evidence is thin, conflicting, or based only on a metric, choose `观察` and state what must be checked.

KD thresholds may filter a large list for review but must never auto-approve or auto-reject a project. A model may make an initial classification, but a human/business owner makes the final decision when rights, domain purchase, material cost, production deployment, or strategic commitment is involved.

The script accepts the result through:

```bash
python mine_round.py --judge /tmp/verdicts_YYYY-MM-DD.json
```

Verify the output ledger and checkpoint rather than assuming a successful process exit means every candidate was correctly judged. Do not reuse a prior date's evidence as if it were current.

## 4. Project-Specific Recommendation

For each `立项` or `观察` term, recommend:

- One intent cluster and one proposed canonical URL.
- The target audience/market and the concrete game or feature to build.
- What will be materially better or different from existing solutions.
- Rights, technical, monetization, and platform risks.
- The smallest useful experiment and the metrics/window that would change the decision.

The research report should show candidate counts, evidence links/paths, market/date, limitations, planned API spend, and unresolved questions. Report metric provenance; never use DR/UR as a standalone ranking or feasibility verdict.
