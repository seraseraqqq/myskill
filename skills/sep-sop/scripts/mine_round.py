#!/usr/bin/env python3
"""关键词挖掘统一执行器（双轨）。

轨道B 新词挖掘:  --track new --from-rising rising.json  （阶段1/2/3）
轨道B 词根扫描:  --track new --roots ai,checker
轨道A 老词长尾:  --track old --seeds "ppt to notes" [--expand] [--competitor domain.com]
复判盘面:        --serp-only（读今天 sheet 的候选重新定案，省钱）

通用流程: 数据源捞词 → 量体/KD初筛 → 月趋势定出现时间 → 新词信号/意图判定
          → 盘面 SERP 定案 → 台账 Excel 当天 sheet（重跑覆盖）。

环境: 轨道B（新词）全程直连 Google Trends；轨道A 使用 DataForSEO API（付费）。
所有付费模式必须显式传 --allow-paid；--trends-only 为免费但近似的降级模式。
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

try:
    from dataforseo_client import Client as DataForSEOClient
    _HAS_DATAFORSEO = True
except ImportError:
    _HAS_DATAFORSEO = False
    DataForSEOClient = None
    print("# 注意：dataforseo_client 不可用，付费关键词研究不可用", file=sys.stderr)

SKILL_DIR = Path(__file__).resolve().parent.parent
LEDGER = Path(os.environ.get(
    "KEYWORD_LEDGER",
    "/Users/xg/Projects/SEO-Projects/新词挖掘台账.xlsx"))

# 轨道阈值（可调）
TRACKS = {
    "new": {"min_volume": 100, "max_kd": None},  # 新词：概念层不看 KD（SOP 禁用硬砍）
    "old": {"min_volume": 10, "max_kd": 30},     # 老词：SOP 标准，KD≤30
}
RECENT_MONTHS = 3
BASELINE_MONTHS = 12
EMERGE_RATIO = 0.1
MAX_AUTO_KEYWORDS = 700  # Google Ads Search Volume 单次最多 700 个关键词
_DATAFORSEO: DataForSEOClient | None = None

# 老词轨道长尾扩展用的意图修饰词（对应 SOP 第一步第4条）
MODIFIERS = ["vs", "best", "alternatives", "pricing", "how", "why", "online",
             "free", "generator", "tool", "template", "no sign up"]

# 噪声模式里可自动化的部分（对应 sop-new-words.md）：菠菜/SEO 公司刷榜词
NOISE_PATTERNS = (".com", ".net", ".org", "www.", "regalseo")


def is_noise(kw: str) -> bool:
    """飙升词噪声过滤：词里直接带域名或 SEO 公司名的 = 刷榜，自动砍。"""
    return any(p in kw for p in NOISE_PATTERNS)


# ── 概念层配额保护（非语义过滤；语义噪音由 LLM 在阶段0.5 过滤，见 SKILL.md） ──
PER_ROOT_CAP = 15   # 每个词根最多留 15 个飙升词（防 trivia 词根刷量，Breakout 优先）


def cap_per_root(rising: list[dict], per_root_cap: int = PER_ROOT_CAP) -> list[dict]:
    """配额保护：按飙升幅度排序，每词根最多留 per_root_cap 个。不做任何语义判断。"""
    rows = sorted(rising, key=lambda r: -(999999 if r.get("value") == "Breakout"
                                          else r.get("value") or 0))
    root_count: dict[str, int] = {}
    kept = []
    for r in rows:
        roots = r.get("roots") or ["?"]
        if all(root_count.get(x, 0) >= per_root_cap for x in roots):
            continue
        for x in roots:
            root_count[x] = root_count.get(x, 0) + 1
        kept.append(r)
    return kept


# ── 长尾层主题漂移检测 ──
_DRIFT_STOP = {"meaning", "mean", "anime", "manga", "prompt", "list", "codes", "code",
               "online", "free", "generator", "tool", "template", "best", "how", "why",
               "movie", "what", "is", "the", "and", "for", "download", "converter",
               "2026", "2025", "2027"}


def _content_tokens(s: str) -> set:
    import re as _re
    return {t for t in _re.findall(r"[a-z0-9]+", s.lower())
            if t not in _DRIFT_STOP and len(t) > 2}


def drop_drifted(survivors: dict[str, dict]) -> list[dict]:
    """research 行主题漂移检测：同来源 ≥8 行里，含种子主题词的行 <50%
    = 关键词研究返回的弱概念退化成模式匹配，整组砍掉（不查趋势，省 API 费用）。
    联想行（长尾: 前缀）强制含种子词，不参与检测。返回被砍的记录。"""
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for s in survivors.values():
        if not s["root"].startswith("长尾:"):
            groups[s["root"]].append(s)
    drifted = []
    for src, items in groups.items():
        if len(items) < 8:
            continue
        seed_tokens = _content_tokens(src)
        if not seed_tokens:
            continue
        related = sum(1 for s in items if _content_tokens(s["kw"]) & seed_tokens)
        if related / len(items) < 0.5:
            for s in items:
                s["first"], s["signal"] = "n/a", "未查趋势（漂移预砍）"
                s["serp"] = ""
                s["judge"] = s["final"] = "砍掉：主题漂移（research行与种子不相关）"
                drifted.append(s)
                del survivors[s["kw"]]
    return drifted

# 盘面验证域名分类
BIG_BRANDS = {
    "wikipedia.org", "ticketmaster.com", "espn.com", "amazon.com", "youtube.com",
    "google.com", "facebook.com", "instagram.com", "netflix.com", "imdb.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "forbes.com", "nytimes.com", "apple.com",
    "microsoft.com", "nfl.com", "nba.com", "fifa.com", "yahoo.com", "yelp.com",
    "tripadvisor.com", "booking.com", "walmart.com", "target.com", "bestbuy.com",
    "linkedin.com", "twitter.com", "x.com", "twitch.tv", "spotify.com",
}
UGC_PLATFORMS = {
    "reddit.com", "quora.com", "pinterest.com", "tiktok.com", "discord.com",
    "medium.com", "tumblr.com", "substack.com", "stackexchange.com",
}


# ── 基础工具 ─────────────────────────────

def paid_client() -> DataForSEOClient:
    if not _HAS_DATAFORSEO or _DATAFORSEO is None:
        raise RuntimeError("付费数据源未启用；配置 API 凭据并传入 --allow-paid。")
    return _DATAFORSEO


def unpack_item(item: dict) -> dict:
    """Normalize DataForSEO Labs and Google Ads rows to the ledger schema."""
    data = item.get("keyword_data") or item
    keyword = data.get("keyword") or item.get("keyword") or ""
    info = data.get("keyword_info") or item.get("keyword_info") or {}
    props = data.get("keyword_properties") or item.get("keyword_properties") or {}
    intent_info = data.get("search_intent_info") or item.get("search_intent_info") or {}
    return {
        "keyword": keyword,
        "search_volume": info.get("search_volume", item.get("search_volume", 0)) or 0,
        "keyword_difficulty": props.get("keyword_difficulty", item.get("keyword_difficulty")),
        "cpc": info.get("cpc", item.get("cpc")),
        "competition": info.get("competition", item.get("competition")),
        "intent": intent_info.get("main_intent") or intent_info.get("intent") or "",
        "monthly_searches": info.get("monthly_searches", item.get("monthly_searches", [])) or [],
    }


def pick_words(spec: str | None, use_all: bool) -> list[str]:
    lib = [r.strip() for r in (SKILL_DIR / "assets" / "词根库.txt").read_text().splitlines()
           if r.strip()]
    if use_all:
        return lib
    if spec:
        seen, out = set(), []
        for s in spec.split(","):
            s = s.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out
    return lib[:5]


# ── 数据源（轨道A） ─────────────────────────

def research_words(words: list[str]) -> list[dict]:
    """种子词 → DataForSEO Labs Keyword Ideas。"""
    client = paid_client()
    rows = []
    for seed in words:
        try:
            tasks = client.keyword_ideas([seed], limit=100)
            items = client.items(tasks)
            for item in items:
                row = unpack_item(item)
                if row["keyword"]:
                    row["_root"] = seed
                    rows.append(row)
            print(f"# keyword ideas {seed}: {len(items)} rows", file=sys.stderr)
        except Exception as exc:
            print(f"# 种子 {seed} 失败: {exc}", file=sys.stderr)
    print(f"# DataForSEO 累计请求 {client.calls} 次，实际返回费用 ${client.cost_usd:.4f}",
          file=sys.stderr)
    return rows


def competitor_words(domains: list[str], min_vol: int) -> list[dict]:
    """对手域名 → DataForSEO Labs 排名关键词。"""
    client = paid_client()
    rows = []
    for d in domains:
        target = d.removeprefix("https://").removeprefix("http://").removeprefix("www.")
        try:
            items = client.items(client.ranked_keywords(target, limit=100, min_volume=min_vol))
            for item in items:
                row = unpack_item(item)
                if row["keyword"]:
                    row["_root"] = f"对手:{d}"
                    rows.append(row)
            print(f"# 对手 {d}: {len(items)} 行", file=sys.stderr)
        except Exception as exc:
            print(f"# 对手 {d} 查询失败: {exc}", file=sys.stderr)
    print(f"# DataForSEO 累计请求 {client.calls} 次，实际返回费用 ${client.cost_usd:.4f}",
          file=sys.stderr)
    return rows


def autocomplete_expand(seeds: list[str]) -> list[dict]:
    """SOP 第一步第4条：种子 × 意图修饰词 → Google 联想词扩长尾（免费接口，8 并发）。"""
    from concurrent.futures import ThreadPoolExecutor

    queries = [(f"{seed} {m}", seed) for seed in seeds for m in MODIFIERS]

    def fetch(item: tuple[str, str]) -> list[dict]:
        q, seed = item
        url = ("https://suggestqueries.google.com/complete/search?"
               f"client=firefox&q={urllib.parse.quote(q)}")
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            return [{"keyword": s.strip().lower(), "_root": f"长尾:{seed}"}
                    for s in data[1] if seed.lower() in s.strip().lower()]
        except Exception as e:
            print(f"# 联想词 {q} 失败: {e}", file=sys.stderr)
            return []

    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for rows in pool.map(fetch, queries):
            out += rows
    return out



# ── P3: KGR 免费实查（intitle: "kw" 结果数 ÷ 月搜索量，<0.25 = 蓝海） ──────────
def kgr_check(keyword: str, monthly_vol: int) -> dict:
    """免费 KGR（Keyword Golden Ratio）：intitle:"kw" 结果数 ÷ 月搜索量。

    数据源：Bing HTML（免费接口，能稳定拿到 "About N results"）。
    Google 2024 起对无登录客户端返回 JS-only 页面，intitle 结果数拿不到。
    口径：<0.25 蓝海 / 0.25–1.0 观察 / >1.0 饱和。
    Bing 口径与 Google 有偏差，作为方向参考，不单独硬砍。
    返回 {"kgr": float|None, "supply": int|None, "note": str}"""
    q = f'intitle:"{keyword}"'
    url = ("https://www.bing.com/search?q=" + urllib.parse.quote(q)
           + "&form=QBLH&cc=us&setlang=en")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": "SRCHHPGUSR=SRCHLANG=en"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "ignore")
        m = re.search(r'([\d,\.]+)\s*results', html)
        if not m:
            return {"kgr": None, "supply": None, "note": "intitle 结果数抓不到"}
        supply = int(re.sub(r"[,\.]", "", m.group(1)))
        kgr = supply / monthly_vol if monthly_vol > 0 else None
        return {"kgr": kgr, "supply": supply, "note": f"intitle≈{supply}"}
    except Exception as e:
        return {"kgr": None, "supply": None, "note": f"intitle 查询失败: {e}"}


# ── P4: Google Autocomplete 字母轮询（Ahrefs 式免费扩长��，比 13 修饰词厚得多） ──
_AC_ALPHABET = "*abcdefghijklmnopqrstuvwxyz0123456789"
_AC_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
          "AppleWebKit/536.30.1 (KHTML, like Gecko) Version/17.4 Safari/605.1.15")


def autocomplete_alphabet_ramp(word: str, max_count: int = 60) -> list[str]:
    """Google Autocomplete 字母轮询：seed+char 请求一次，返回完整联想列表。

    Ahrefs/Keywords Everywhere 等三方工具同款玩法，能捞到 13 修饰词碰不到的词形。
    纯免费接口，8 并发；max_count 控单种子上限（默认 60，防刷）。"""
    from concurrent.futures import ThreadPoolExecutor
    out: set[str] = set()
    word_l = word.lower().strip()

    def fetch(char: str) -> list[str]:
        q = f"{word_l} {char}".strip()
        url = ("https://suggestqueries.google.com/complete/search?"
               f"client=firefox&q={urllib.parse.quote(q)}")
        req = urllib.request.Request(url, headers={"User-Agent": _AC_UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            sugg = data[1] if isinstance(data, list) and len(data) > 1 else []
            return [s.strip().lower() for s in sugg
                    if word_l in s.strip().lower()]
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=8) as pool:
        for suggestions in pool.map(fetch, _AC_ALPHABET):
            out.update(suggestions)
    return sorted(out)[:max_count]
# ── 阶段 2/3（两轨共用） ─────────────────────────

def multiramp_trends(keywords: list[str], rate_limit: float = 1.2) -> dict[str, dict]:
    """--trends-only：不调 DataForSEO，批量通过 Google Trends 12 月曲线验证词。

    输出格式兼容 fetch_trends() 返回值（key=小写词，value=字典），使下游 emerge_info()
    和 judge() 不需要变化。search_volume 用 trends 0-100 热度近似（标 vol_quality=trends_proxy）。
    """
    out: dict[str, dict] = {}
    # 使用 trends_pull 的 multiramp 逻辑内联调用
    from trends_pull import multiramp, _new_opener
    rows = multiramp(keywords, out_file=None, rate_limit=rate_limit)
    for r in rows:
        kw = str(r["word"]).strip().lower()
        # trends 热度是 0-100 相对值，不是绝对搜索量；用 peak/10 近似给下游一个可排序的 proxy
        recent = float(r.get("recent30_avg") or 0)
        peak = float(r.get("peak_v") or 0)
        proxy_vol = int(peak * 100) if peak > 0 else 0
        out[kw] = {
            "search_volume": proxy_vol,
            "keyword_difficulty": None,
            "monthly_searches": [],
            "vol_quality": "trends_proxy",
            "recent30_avg": r.get("recent30_avg"),
            "baseline_avg": r.get("baseline_avg"),
            "first_nonzero": r.get("first_nonzero"),
            "peak_v": r.get("peak_v"),
            "peak_t": r.get("peak_t"),
            "signal": r.get("signal"),
            "monthly_series": r.get("monthly") or {},
        }
    return out


def fetch_trends(keywords: list[str]) -> dict[str, dict]:
    client = paid_client()
    out, total = {}, 0
    too_long = [k for k in keywords if len(k) > 250]
    if too_long:
        print(f"# 跳过 {len(too_long)} 个超长词（>250字符）", file=sys.stderr)
    keywords = [k for k in keywords if len(k) <= 250]
    for i in range(0, len(keywords), MAX_AUTO_KEYWORDS):
        batch = keywords[i:i + MAX_AUTO_KEYWORDS]
        volume_tasks = client.search_volume(batch)
        for item in client.items(volume_tasks):
            row = unpack_item(item)
            if row["keyword"]:
                out[row["keyword"].lower()] = row
        # KD is a separate Labs metric; failures leave KD unknown without discarding volume.
        try:
            difficulty_tasks = client.bulk_keyword_difficulty(batch)
            for item in client.items(difficulty_tasks):
                keyword = str(item.get("keyword") or "").lower()
                if keyword in out:
                    out[keyword]["keyword_difficulty"] = item.get("keyword_difficulty")
        except Exception as exc:
            print(f"# KD 批次失败（搜索量保留，KD未知）: {exc}", file=sys.stderr)
        total += 1
        print(f"# 趋势批次 {i}-{i + len(batch)}: 累计 {len(out)} 词", file=sys.stderr)
    print(f"# DataForSEO 累计请求 {client.calls} 次，实际返回费用 ${client.cost_usd:.4f}",
          file=sys.stderr)
    return out


def chronologic(monthly: list[dict]) -> list[tuple[str, int]]:
    seq = [(f"{m.get('year')}-{int(m.get('month', 0)):02d}", int(m.get("search_volume") or 0))
           for m in monthly or []]
    return sorted(seq)


def _first_nonzero_month(seq: list[tuple[str, int]]) -> str:
    """哥飞口径：12个月月度序列里，第一个非零月份 = 出现时间参照点。"""
    for m, v in seq:
        if v > 0:
            return m
    return "未知"


def emerge_info(trend: dict) -> tuple[str, str]:
    """出现时间判定（哥飞口径重写，P1 修复）：
    --trends-only 模式下 trend 含 vol_quality=trends_proxy + signal 字段，直接透传。
    1. 月度序列中第一个非零月份 = 参照出现月份（不是占比反推）
    2. 近3月均量 ≥ 前9月均量 × 3 → 近期起量（新词或二次爆火信号）
    3. 前9月全零 + 近期有量 → 从无到有（最纯新词）
    4. 前9月有量且基线占峰值 ≤20% → 老词热点（暴涨≠新词，降观察）
    说明：DataForSEO monthly_searches 通常只覆盖最近12个月，13个月前的词
    在窗口内已非零——判定的是窗口内起点，不是绝对首发日。
    """
    # --trends-only：trends proxy 信号直接用（先于 monthly_searches 判定）
    if trend.get("vol_quality") == "trends_proxy":
        signal = str(trend.get("signal") or "")
        first = str(trend.get("first_nonzero") or "未知")
        return (first, signal)
    seq = chronologic(trend.get("monthly_searches"))
    if not seq:
        return ("未知", "无月趋势数据")
    first = _first_nonzero_month(seq)
    peak = max(v for _, v in seq) or 1
    recent = seq[-RECENT_MONTHS:]
    if len(seq) <= RECENT_MONTHS:
        baseline = seq[:-RECENT_MONTHS]
    else:
        baseline = seq[:-RECENT_MONTHS][-BASELINE_MONTHS:]
    recent_avg = int(sum(v for _, v in recent) / len(recent)) if recent else 0
    base_avg = int(sum(v for _, v in baseline) / len(baseline)) if baseline else 0
    n_baseline = len(baseline)

    if n_baseline == 0 or (n_baseline and all(v == 0 for _, v in baseline)):
        if recent_avg > 0:
            return (first, f"新词：前{n_baseline or 0}月全零，近{RECENT_MONTHS}月≈{recent_avg}")
        return (first, "观察：全部月份无量")
    if recent_avg >= base_avg * 3:
        return (first, f"近期起量：近{RECENT_MONTHS}月≈{recent_avg}，前9月≈{base_avg}")
    if base_avg <= peak * 0.2:
        return (first, f"老词热点：基线≈{base_avg} 占峰值≤20%，近{RECENT_MONTHS}月≈{recent_avg}")
    return (first, f"非新词形态：基线≈{base_avg}，近{RECENT_MONTHS}月≈{recent_avg}")


def export_monthly(trends_list: list[dict], path: str) -> int:
    """导出 {词: {年月: 量}} 给 library.py --monthly enrich（二次爆火/长期大词判定用）。"""
    out: dict[str, dict] = {}
    for trends in trends_list:
        for kw, t in trends.items():
            seq = chronologic(t.get("monthly_searches")) or sorted(
                (t.get("monthly_series") or {}).items())
            if seq:
                out[kw] = {m: v for m, v in seq}
    Path(path).write_text(json.dumps(out, ensure_ascii=False))
    print(f"# 月趋势已导出 {len(out)} 词 -> {path}", file=sys.stderr)
    return len(out)


def judge(track: str, vol: int, kd: int | None, signal: str,
          vol_quality: str = "") -> str:
    th = TRACKS[track]
    # --trends-only：trends proxy 信号即初判，不需要 vol/KD
    if vol_quality == "trends_proxy" and signal:
        if "新词" in signal or "近期起量" in signal:
            return "候选：trends proxy 新词/起量形态"
        if "老词热点" in signal:
            return "观察：老词热点（Ghibli 型，非新词）"
        if "无量" in signal or "拉取失败" in signal:
            return "观察：trends proxy 无趋势数据"
        return "观察：trends proxy 平淡（老词或无增量）"
    if track == "new":
        # 轨道 B 概念层：SOP 禁用 volume/KD 硬砍，只看新词信号
        if "非新词形态" in signal:
            return "观察：不是新词形态"
        if "老词热点" in signal:
            return "观察：老词热点（Ghibli 型）"
        if vol == 0:
            return "候选：Google Ads 口径无量（新词未收录，以趋势+SERP为准）"
        return "候选：新词窗口"
    # 老词轨道：看缺口而不是起量（缺口由 AI 判定步给出，脚本先放行）
    if vol < th["min_volume"]:
        return "砍掉：体量不足"
    max_kd = th.get("max_kd")
    if max_kd is not None and kd is not None and kd > max_kd:
        return "砍掉：KD 过高"
    return "候选：量/KD 达标，待AI判定（意图/缺口）"


def classify_domain(domain: str | None) -> str:
    if not domain or domain == "?":
        return "unknown"
    d = domain.lower()
    if d.startswith("www."):
        d = d[4:]
    if any(d == b or d.endswith("." + b) for b in BIG_BRANDS):
        return "big"
    if any(d == u or d.endswith("." + u) for u in UGC_PLATFORMS):
        return "ugc"
    return "other"


def evidence_file_for(tag: str) -> Path:
    ckpt_dir = LEDGER.parent / ".km_checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    return ckpt_dir / f"serp_{dt.date.today().isoformat()}_{tag}.json"


def find_today_evidence() -> dict | None:
    """自动定位今天导出的 SERP 证据文件（--judge 默认用）。"""
    ckpt_dir = LEDGER.parent / ".km_checkpoints"
    if not ckpt_dir.exists():
        return None
    today = dt.date.today().isoformat()
    ev: dict = {}
    for f in sorted(ckpt_dir.glob(f"serp_{today}_*.json")):
        try:
            ev.update(json.load(open(f)))
        except Exception as e:
            print(f"# 证据文件 {f.name} 读取失败: {e}", file=sys.stderr)
    return ev or None


def phase3_serp(candidates: list[dict], evidence_path: Path | None = None) -> dict[str, dict]:
    if not candidates:
        return {}
    client = paid_client()
    out, kws = {}, [c["kw"] for c in candidates]
    evidence: dict[str, dict] = {}
    from collections import Counter
    for i, keyword in enumerate(kws, 1):
        kw = keyword.lower()
        try:
            tasks = client.serp(keyword, depth=10)
            raw = [item for item in client.items(tasks)
                   if item.get("type") in (None, "organic")]
            items_raw = [{
                **item,
                "rank": item.get("rank_group") or item.get("rank_absolute"),
                "domain": item.get("domain") or "",
                "title": item.get("title") or "",
                "url": item.get("url") or "",
            } for item in raw]
        except Exception as exc:
            print(f"# SERP {keyword} 失败: {exc}", file=sys.stderr)
            out[kw] = {"verdict": "观察：SERP 拉取失败", "serp": ""}
            continue
        if items_raw:
            rows = sorted(items_raw, key=lambda r: r.get("rank") or 99)[:10]
            counts = {"big": 0, "ugc": 0, "other": 0, "unknown": 0}
            dom_count = Counter()
            kw_tokens = _content_tokens(kw)
            dedicated = inner = 0   # 哥飞标准：标题含关键词主题=专门页面，否则=内页候选
            for r in rows:
                cls = classify_domain(r.get("domain"))
                counts[cls] += 1
                if cls != "unknown":
                    dom_count[(r.get("domain") or "").lower().removeprefix("www.")] += 1
                title_tokens = _content_tokens(str(r.get("title") or ""))
                if kw_tokens and (title_tokens & kw_tokens):
                    dedicated += 1
                else:
                    inner += 1
            note = ", ".join((r.get("domain") or "?") for r in rows[:6])
            top_dom, top_n = (dom_count.most_common(1) or [("", 0)])[0]
            if counts["unknown"] >= 5:
                verdict = "观察：SERP 特征位多，待AI判定"
            elif top_n >= 3:
                verdict = f"观察：单站占位（{top_dom}）"
            elif counts["big"] >= 4:
                verdict = "砍掉：SERP 大站垄断"
            elif counts["ugc"] >= 2:
                verdict = "候选：SERP 有 UGC 弱对手"
            elif counts["big"] == 0:
                verdict = "候选：前排无大牌"
            else:
                verdict = "观察：SERP 混合，待AI判定"
            out[kw] = {"verdict": verdict, "serp": note,
                       "dedicated": dedicated, "inner": inner}
            # 完整证据落盘：供模型做意图四档/缺口/C1C2C3 判定（不重复付费）
            evidence[kw] = {"items": items_raw, "domains": note}
        else:
            out[kw] = {"verdict": "观察：SERP 无可用自然结果", "serp": ""}
        print(f"# SERP {i}/{len(kws)}: {keyword}", file=sys.stderr)
    print(f"# DataForSEO SERP 累计请求 {client.calls} 次，实际返回费用 ${client.cost_usd:.4f}",
          file=sys.stderr)
    if evidence_path and evidence:
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False))
        print(f"# SERP 证据已导出 {evidence_path}", file=sys.stderr)
    return out


# ── SOP 判断步骤自动化（原标注「人工」的部分） ─────────────────────────

def cluster_keywords(kws: list[str], evidence: dict, threshold: float = 0.5) -> dict[str, str]:
    """同义词归并（SOP 方式一-5）自动化：SERP 前排域名重合度（overlap 系数）
    ≥ threshold 的词并入同簇（如 how to add/enable/access 前排大量重合）。
    只做机械聚类，簇名/取舍由模型在判定阶段确认。"""
    sets: dict[str, set] = {}
    for kw in kws:
        doms = []
        for it in evidence.get(kw, {}).get("items", []):
            d = (it.get("domain") or "").lower().removeprefix("www.")
            if d:
                doms.append(d)
        sets[kw] = set(doms[:10])
    parent = {kw: kw for kw in kws}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(kws):
        if not sets[a]:
            continue
        for b in kws[i + 1:]:
            if not sets[b]:
                continue
            inter = len(sets[a] & sets[b])
            if inter and inter >= threshold * min(len(sets[a]), len(sets[b])):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    groups: dict[str, list] = {}
    for kw in kws:
        groups.setdefault(find(kw), []).append(kw)
    labels: dict[str, str] = {}
    for n, (_, members) in enumerate(
            sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
        if len(members) > 1:
            for kw in members:
                labels[kw] = f"簇{n:02d}"
    return labels


def backlinks_check(evidence: dict, cap: int) -> dict[str, dict]:
    """查 DataForSEO 可提供的反向链接与引用域名规模，不推算或伪称 DR。 
    域名去重后按出现频次取前 cap 个。"""
    from collections import Counter
    doms = Counter()
    for ev in evidence.values():
        for it in ev.get("items", []):
            d = (it.get("domain") or "").lower().removeprefix("www.")
            if d and classify_domain(d) == "other":
                doms[d] += 1
    client = paid_client()
    out: dict[str, dict] = {}
    for d, _ in doms.most_common(cap):
        try:
            tasks = client.backlinks_summary(d)
            result = next(iter(tasks[0].get("result") or []), {}) if tasks else {}
            out[d] = result
        except Exception as e:
            print(f"# 外链摘要查询 {d} 失败: {e}", file=sys.stderr)
        print(f"# 外链摘要 {d} 完成（{len(out)}/{min(cap, len(doms))}）", file=sys.stderr)
    print(f"# DataForSEO 外链累计请求 {client.calls} 次，实际返回费用 ${client.cost_usd:.4f}",
          file=sys.stderr)
    return out


def extract_backlinks(overview: dict) -> str:
    if not isinstance(overview, dict):
        return "?"
    backlinks = overview.get("backlinks") or overview.get("total_backlinks")
    referring = overview.get("referring_domains")
    if backlinks is None and referring is None:
        return "?"
    return f"RD:{referring if referring is not None else '?'} / BL:{backlinks if backlinks is not None else '?'}"


def annotate_backlinks(records: list[dict], evidence: dict, backlink_map: dict[str, dict]) -> None:
    """把前排首个可查域名的引用域名/反向链接规模写入表格。"""
    for r in records:
        ev = evidence.get(str(r["kw"]).lower())
        if not ev:
            continue
        for it in sorted(ev.get("items", []), key=lambda x: x.get("rank") or 99):
            d = (it.get("domain") or "").lower().removeprefix("www.")
            if d in backlink_map:
                r["backlinks"] = f"{d}({extract_backlinks(backlink_map[d])})"
                break


def run_judge(verdicts_file: str, evidence: dict | None, args) -> None:
    """AI 判定回填：吃模型按 rubric 写的 verdicts JSON，合并进今天 sheet。

    verdicts 格式：{"items": {"<候选词小写>": {"tier": "直接解决|方案之一|受众重叠|无关",
      "gap": "无缺口|工具缺口|内容缺口|质量缺口", "verdict": "立项|观察|砍掉",
      "reason": "一句话依据", "c1": "...", "c2": "...", "c3": "...",
      "ai_overview": true/false}}}
    同义词聚类与 TP 由脚本机械计算。整步不调用 DataForSEO（外链检查除外）。
    """
    records = load_today_candidates()
    verdicts = json.load(open(verdicts_file))
    items = verdicts.get("items", verdicts)

    # 同义词归并 + TP（父主题词量≈同簇最大量）
    serp_kws = [r["kw"] for r in records if r.get("serp")]
    clusters = cluster_keywords(serp_kws, evidence) if evidence else {}

    def _vol(r) -> int:
        try:
            return int(r.get("vol") or 0)
        except (TypeError, ValueError):
            return 0

    by_cluster: dict[str, list[str]] = {}
    for kw, c in clusters.items():
        by_cluster.setdefault(c, []).append(kw)
    vols = {r["kw"]: _vol(r) for r in records}
    tp: dict[str, int] = {}
    for c, members in by_cluster.items():
        mtp = max((vols.get(m, 0) for m in members), default=0)
        for m in members:
            tp[m] = mtp
    for r in records:
        r["tp"] = tp.get(r["kw"], _vol(r))
        if r["kw"] in clusters:
            r["cluster"] = clusters[r["kw"]]

    # 模型判定回填
    n_hit = 0
    for r in records:
        v = items.get(r["kw"])
        if not v:
            continue
        n_hit += 1
        r["tier"] = v.get("tier", "")
        r["gap"] = v.get("gap", "")
        r["c1"] = v.get("c1", "")
        r["c2"] = v.get("c2", "")
        r["c3"] = v.get("c3", "")
        r["aiov"] = "有风险" if v.get("ai_overview") else ""
        verdict, reason = str(v.get("verdict", "")).strip(), str(v.get("reason", "")).strip()
        if verdict in ("立项", "观察", "砍掉"):
            r["final"] = f"{verdict}：AI判定 {reason}" if reason else f"{verdict}：AI判定"

    if args.dr_check and evidence:
        annotate_backlinks(records, evidence, backlinks_check(evidence, args.dr_check))

    records.sort(key=lambda x: (0 if str(x["final"]).startswith(("立项", "候选")) else
                                1 if str(x["final"]).startswith("观察") else 2,
                                -_vol(x)))
    sheet = write_sheet(records, "AI", f"AI判定回填:{Path(verdicts_file).name}", len(records))
    n_clustered = len([r for r in records if r.get("cluster")])
    print(json.dumps({"ledger": str(LEDGER), "sheet": sheet, "judged": n_hit,
                      "clustered": n_clustered, "n": len(records)}, ensure_ascii=False))


# ── 台账 ─────────────────────────────

def write_sheet(records: list[dict], track: str, source_note: str, raw_rows: int) -> str:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    today = dt.date.today().isoformat()
    headers = ["状态", "候选词", "来源", "轨道", "月搜索量", "KD", "意图", "CPC", "竞争度",
               "出现月份", "信号", "初判", "盘面验证", "定案", "意图匹配", "缺口", "TP",
               "同义簇", "C1类型", "C2形式", "C3角度", "AI概览", "对手外链规模", "释义",
               "内页候选", "专门页面", "备注"]

    if LEDGER.exists():
        wb = load_workbook(LEDGER)
        if today in wb.sheetnames:
            del wb[today]
    else:
        wb = Workbook()
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ws = wb.create_sheet(today)
    ws.append(headers + [f"轨道: {track}", f"来源: {source_note}", f"原始行数: {raw_rows}"])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    color = {"候选": "C6EFCE", "观察": "FFEB9C", "砍掉": "FFC7CE", "立项": "C6EFCE",
             "过滤": "D9D9D9"}
    for r in records:
        final = str(r.get("final", r["judge"]))
        status = final.split("：")[0]          # 首列状态，可直接筛选
        ws.append([status, r["kw"], r["root"], r.get("track", track), r["vol"],
                   r["kd"] if r["kd"] is not None else "n/a", r["intent"], r["cpc"],
                   r["competition"], r["first"], r["signal"], r["judge"],
                   r.get("serp", ""), final, r.get("tier", ""), r.get("gap", ""),
                   r.get("tp", ""), r.get("cluster", ""), r.get("c1", ""), r.get("c2", ""),
                   r.get("c3", ""), r.get("aiov", ""), r.get("backlinks", ""), r.get("expl", ""),
                   r.get("dedicated", ""), r.get("inner", ""), r.get("note", "")])
        fill = next((v for k, v in color.items() if final.startswith(k)), None)
        if fill:
            for cell in ws[ws.max_row]:
                cell.fill = PatternFill("solid", fgColor=fill)
    for i, w in enumerate([8, 40, 14, 6, 10, 6, 12, 8, 9, 12, 40, 34, 32, 34, 12, 16,
                           8, 8, 10, 10, 14, 8, 20, 44, 9, 9, 24], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    wb.save(LEDGER)
    return ws.title


def load_today_candidates() -> list[dict]:
    """按表头名读今天 sheet 的全部列（--serp-only / --judge 共用），不丢已回填的 AI 判定列。"""
    from openpyxl import load_workbook
    today = dt.date.today().isoformat()
    wb = load_workbook(LEDGER)
    if today not in wb.sheetnames:
        sys.exit(f"今天的 sheet {today} 不存在，先跑完整流程")
    rows = list(wb[today].iter_rows(values_only=True))
    header = {str(h): i for i, h in enumerate(rows[0]) if h is not None}

    def g(row, name, default=""):
        i = header.get(name)
        v = row[i] if i is not None and i < len(row) else None
        return default if v is None else v

    records = []
    for row in rows[1:]:
        kw = str(g(row, "候选词", "")).strip().lower()
        if not kw:
            continue
        records.append({"kw": kw, "root": g(row, "来源"), "track": g(row, "轨道"),
                        "vol": g(row, "月搜索量", 0), "kd": g(row, "KD"), "intent": g(row, "意图"),
                        "cpc": g(row, "CPC"), "competition": g(row, "竞争度"),
                        "first": g(row, "出现月份"), "signal": g(row, "信号"),
                        "judge": g(row, "初判"), "serp": g(row, "盘面验证"),
                        "final": g(row, "定案"), "tier": g(row, "意图匹配"),
                        "gap": g(row, "缺口"), "tp": g(row, "TP"), "cluster": g(row, "同义簇"),
                        "c1": g(row, "C1类型"), "c2": g(row, "C2形式"), "c3": g(row, "C3角度"),
                        "aiov": g(row, "AI概览"), "backlinks": g(row, "对手外链规模"),
                        "expl": g(row, "释义"), "dedicated": g(row, "专门页面"),
                        "inner": g(row, "内页候选"), "note": g(row, "备注")})
    return records


# ── 轨道 B 新流程：概念层 → 长尾层（会师内置） ─────────────────────────

def run_rising_pipeline(rising: list[dict], args) -> None:
    """飙升词两段式挖掘。

    概念层：飙升词先做趋势验证（语义噪音已在阶段 0.5 由 LLM 过滤）。
    通过的概念自动会师进轨道 A 流水线。
    长尾层：DataForSEO 相关词 + 联想扩长尾 → 主题漂移预砍 → vol≥10、KD≤30 初筛 → SERP 定案。
    """
    rising = cap_per_root(rising)
    print(f"# 配额保护后概念 {len(rising)} 个（语义过滤应在阶段 0.5 完成）", file=sys.stderr)
    # 注意：概念层进入 mine 后 vol 可能仍是 0，但 judge("new") 不再因 vol=0 砍掉（P2a 已修）

    concepts: dict[str, dict] = {}
    for r in rising:
        kw = str(r.get("query", "")).strip().lower()
        if kw and kw not in concepts:
            concepts[kw] = {"kw": kw, "root": "+".join(r.get("roots", [])),
                            "vol": 0, "kd": None, "cpc": None, "competition": None,
                            "intent": "", "track": "B概念", "expl": r.get("note", ""),
                            "gpts": r.get("gpts")}

    # 检查点：概念验证和扩词结果落盘，超时/报错后重跑直接从断点续（省 API 费用）
    import hashlib
    ckpt_dir = LEDGER.parent / ".km_checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    ckpt_file = ckpt_dir / f"ckpt_{hashlib.md5('|'.join(sorted(concepts)).encode()).hexdigest()[:12]}.json"
    ckpt: dict = {}
    if ckpt_file.exists():
        try:
            ckpt = json.load(open(ckpt_file))
            print(f"# 命中检查点 {ckpt_file.name}（stage={ckpt.get('stage')}），断点续跑",
                  file=sys.stderr)
        except Exception as e:
            print(f"# 检查点损坏，重算: {e}", file=sys.stderr)
            ckpt = {}

    # 概念层：趋势验证（--trends-only 时用免费 Google Trends 直连）
    if ckpt.get("stage") in ("concepts", "tails"):
        trends = ckpt["concepts_trends"]
    elif args.trends_only:
        trends = multiramp_trends(sorted(concepts))
        ckpt = {"stage": "concepts", "concepts_trends": trends}
        ckpt_file.write_text(json.dumps(ckpt, ensure_ascii=False))
    else:
        trends = fetch_trends(sorted(concepts))
        ckpt = {"stage": "concepts", "concepts_trends": trends}
        ckpt_file.write_text(json.dumps(ckpt, ensure_ascii=False))
    passed: list[dict] = []
    records: list[dict] = []
    for kw, s in concepts.items():
        t = trends.get(kw, {})
        if t:
            s["vol"] = int(t.get("search_volume") or 0)
            s["kd"] = t.get("keyword_difficulty")
            s["intent"] = t.get("main_intent") or ""
            s["competition"] = t.get("competition")
        s["first"], s["signal"] = emerge_info(t)
        s["serp"] = "概念层不做SERP，盘面在长尾层定案"
        if is_noise(kw):
            s["judge"] = s["final"] = "砍掉：噪声模式（域名/刷榜词）"
        elif "非新词形态" in s["signal"]:
            # 老词形态走轨道 A 即可，不占用概念层扩长尾的 API 费用
            s["judge"] = s["final"] = "观察：不是新词形态（要挖走轨道A）"
        elif kw not in trends:
            s["judge"] = s["final"] = "观察：趋势数据缺失（最新鲜信号，照样扩长尾）"
            passed.append(s)
        else:
            s["judge"] = s["final"] = "立项：概念入池，已扩长尾"
            passed.append(s)
        records.append(s)

    # 阶段0.5 被 LLM 过滤掉的词：写进台账标灰存档（不调用外部付费 API）
    if args.llm_dropped:
        for r in json.load(open(args.llm_dropped)):
            kw = str(r.get("query", "")).strip().lower()
            if not kw:
                continue
            records.append({"kw": kw, "root": "+".join(r.get("roots", [])),
                            "vol": 0, "kd": None, "cpc": None, "competition": None,
                            "intent": "", "track": "B过滤", "first": "-", "signal": "-",
                            "judge": "过滤：阶段0.5 LLM语义过滤",
                            "serp": "未查趋势（过滤，未调用付费 API）",
                            "final": "过滤：阶段0.5 LLM语义过滤"})

    # 优先扩有趋势数据的概念，量高的排前
    passed.sort(key=lambda x: (0 if x["kw"] in trends else 1, -x["vol"]))

    seeds: list[str] = [] if args.no_bridge else [s["kw"] for s in passed[:args.max_expand]]
    print(f"# 概念 {len(concepts)} 个，通过 {len(passed)} 个，本轮扩长尾 {len(seeds)} 个",
          file=sys.stderr)

    # 长尾层：会师进轨道 A 流水线
    drifted: list[dict] = []
    trends2: dict = {}
    if seeds and ckpt.get("stage") == "tails":
        tails = ckpt["tails"]
        print(f"# 长尾层从检查点恢复：{len(tails)} 词，直接进 SERP 定案", file=sys.stderr)
    elif seeds:
        th = TRACKS["old"]
        if args.trends_only:
            print("# --trends-only：轨道B 长尾跳过 DataForSEO research，只用 Google Autocomplete 联想", file=sys.stderr)
            raw = autocomplete_expand(seeds)
        else:
            raw = research_words(seeds) + autocomplete_expand(seeds)
        survivors: dict[str, dict] = {}
        for r in raw:
            kw = str(r.get("keyword", "")).strip().lower()
            vol = int(r.get("searchVolume") or r.get("search_volume") or 0)
            if not kw or kw in survivors or vol < th["min_volume"]:
                continue
            survivors[kw] = {"kw": kw, "root": r["_root"], "vol": vol,
                             "kd": r.get("keywordDifficulty") or r.get("keyword_difficulty"),
                             "cpc": r.get("cpc"), "competition": r.get("competition"),
                             "intent": r.get("intent") or r.get("main_intent") or "",
                             "track": "A会师"}
        print(f"# 会师捞词 {len(raw)} 行，初筛后 {len(survivors)} 词", file=sys.stderr)
        # 主题漂移预砍（不查趋势，省 API 费用）：research 行与种子主题重合率 <50% 的整组砍
        drifted = drop_drifted(survivors)
        if drifted:
            print(f"# 主题漂移砍掉 {len(drifted)} 词（未查趋势）", file=sys.stderr)
        trends2 = multiramp_trends(sorted(survivors)) if args.trends_only else (
            fetch_trends(sorted(survivors)) if survivors else {})
        tails = []
        for kw, s in survivors.items():
            t = trends2.get(kw, {})
            if t:
                s["vol"] = int(t.get("search_volume") or s["vol"])
                s["kd"] = t.get("keyword_difficulty", s["kd"])
                s["intent"] = t.get("main_intent") or s["intent"]
                s["competition"] = t.get("competition", s["competition"])
            s["first"], s["signal"] = emerge_info(t)
            s["judge"] = judge("old", s["vol"], s["kd"], s["signal"],
                                vol_quality=t.get("vol_quality") if t else "")
            if kw not in trends2:
                s["judge"] = "观察：趋势数据缺失"
            tails.append(s)
        ckpt.update({"stage": "tails", "seeds": seeds, "tails": tails})
        ckpt_file.write_text(json.dumps(ckpt, ensure_ascii=False))
    else:
        tails = []
    records += drifted

    if tails:
        cands = [r for r in tails if r["judge"].startswith("候选")]
        cands.sort(key=lambda x: -x["vol"])
        to_check = cands[:args.top_serp]
        if args.trends_only:
            print("# --trends-only：轨道B SERP 跳过 DataForSEO（留待人工/AI判定）", file=sys.stderr)
            serp = {}
            for r in to_check:
                serp[r["kw"]] = {"verdict": "候选：trends-only 不做SERP，须AI判定",
                                 "serp": "跳过（trends-only）"}
        else:
            serp = phase3_serp(to_check, evidence_file_for("rising"))
        for r in tails:
            if r in to_check and r["kw"] in serp:
                r["serp"], r["final"] = serp[r["kw"]]["serp"], serp[r["kw"]]["verdict"]
                r["dedicated"], r["inner"] = serp[r["kw"]]["dedicated"], serp[r["kw"]]["inner"]
            else:
                r["final"] = r["judge"]
        records += tails
        if args.export_monthly:
            export_monthly([trends, trends2], args.export_monthly)

    records.sort(key=lambda x: (0 if str(x["final"]).startswith(("立项", "候选")) else
                                1 if str(x["final"]).startswith("观察") else 2, -x["vol"]))
    sheet = write_sheet(records, "B→A", f"飙升词{len(concepts)}→会师种子{len(seeds)}",
                        len(concepts))
    final: dict[str, int] = {}
    for r in records:
        key = str(r["final"]).split("：")[0]
        final[key] = final.get(key, 0) + 1
    print(json.dumps({"ledger": str(LEDGER), "sheet": sheet, "final": final,
                      "n": len(records)}, ensure_ascii=False))


# ── 主流程 ─────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=["new", "old"], default="new")
    ap.add_argument("--roots", help="词根/种子词，逗号分隔")
    ap.add_argument("--all", action="store_true", help="全部词根")
    ap.add_argument("--seeds", help="轨道A种子词（同 --roots，语义更清晰）")
    ap.add_argument("--competitor", help="对手域名，逗号分隔（方式二）")
    ap.add_argument("--no-expand", action="store_true", help="轨道A关闭联想词长尾扩展")
    ap.add_argument("--from-rising", metavar="FILE", help="轨道B：吃 trends_pull.py 的飙升词 JSON（概念验证+自动会师扩长尾）")
    ap.add_argument("--llm-dropped", metavar="FILE", help="轨道B：阶段0.5 被LLM过滤掉的词 JSON，写进台账标灰存档（不调用付费 API）")
    ap.add_argument("--export-monthly", metavar="FILE", help="把本轮查到的月趋势导出 {词: {年月: 量}}，喂 library.py --monthly")
    ap.add_argument("--serp-only", action="store_true", help="只复判今天候选的盘面")
    ap.add_argument("--judge", metavar="FILE", help="AI 判定回填：吃模型按 rubric 写的 verdicts JSON，合并进今天 sheet（不调用付费 API，含同义词聚类/TP）")
    ap.add_argument("--evidence", metavar="FILE", help="SERP 证据文件（--judge 时默认自动找今天导出的）")
    ap.add_argument("--dr-check", type=int, nargs="?", const=8, default=0, metavar="N",
                    help="兼容旧参数：查询引用域名/反向链接数量（付费，默认关闭）")
    ap.add_argument("--backlinks-check", type=int, nargs="?", const=8, default=0, metavar="N",
                    help="查询 SERP 前排域名的引用域名/反向链接数量（付费，最多 N 个域名）")
    ap.add_argument("--reflow", type=int, default=8,
                    help="方式二闭环：对手 top 词自动回流当种子扩长尾的数量（默认 8，0 关闭）")
    ap.add_argument("--reflow-research", action="store_true",
                    help="回流种子也走 DataForSEO Keyword Ideas（付费，默认只走免费联想接口）")
    ap.add_argument("--top-serp", type=int, default=20,
                    help="只对量最高的前 N 个候选做盘面验证（默认 20，控成本/耗时）")
    ap.add_argument("--max-expand", type=int, default=40,
                    help="轨道B：本轮最多拿多少个通过的概念去扩长尾（默认 40，控 API 费用）")
    ap.add_argument("--no-bridge", action="store_true",
                    help="轨道B：只验证概念层，不自动会师扩长尾")
    ap.add_argument("--allow-paid", action="store_true",
                    help="明确允许本次运行调用 DataForSEO 付费 API；实际费用响应后报告，无法设置硬美元上限")
    ap.add_argument("--trends-only", action="store_true",
                    help="不调用 DataForSEO：趋势/量/KD/SERP 全部改走 Google Trends + 免费接口。"
                         "量用 trends proxy（不可精确），SERP 用 Google Autocomplete 联想近似。"
                         "适合 0-credit 快速判断概念可行性")
    ap.add_argument("--kgr", action="store_true",
                    help="对拟立项词免费跑 KGR（intitle:'kw' 结果数 ÷ 月搜索量，<0.25 蓝海）")
    ap.add_argument("--alphabet", action="store_true",
                    help="长尾扩展用 Google Autocomplete 字母轮询（免费，比 13 修饰词厚得多）")
    args = ap.parse_args()

    if args.backlinks_check:
        args.dr_check = args.backlinks_check
    if args.serp_only and args.trends_only:
        ap.error("--serp-only 会重新抓取实时 SERP；移除 --trends-only 或不要使用 --serp-only。")
    uses_paid_api = not args.trends_only and (not args.judge or bool(args.dr_check))
    if uses_paid_api and not args.allow_paid:
        ap.error("该流程将调用 DataForSEO 付费 API；需显式添加 --allow-paid，或改用 --trends-only。")
    if uses_paid_api:
        if not _HAS_DATAFORSEO:
            ap.error("未找到 scripts/dataforseo_client.py，无法启用 DataForSEO。")
        try:
            _DATAFORSEO = DataForSEOClient()
        except Exception as exc:
            ap.error(str(exc))

    if args.judge:
        evidence = json.load(open(args.evidence)) if args.evidence else find_today_evidence()
        if not evidence:
            print("# 警告：没找到今天的 SERP 证据文件，同义词聚类/TP 将跳过（仍可回填判定列）",
                  file=sys.stderr)
        return run_judge(args.judge, evidence, args)

    if args.serp_only:
        records = load_today_candidates()
        cands = [r for r in records if str(r["judge"]).startswith("候选")]
        serp = phase3_serp(cands, evidence_file_for("serponly"))
        for r in records:
            if r in cands and r["kw"] in serp:
                r["serp"], r["final"] = serp[r["kw"]]["serp"], serp[r["kw"]]["verdict"]
                r["dedicated"], r["inner"] = serp[r["kw"]]["dedicated"], serp[r["kw"]]["inner"]
            else:
                r["final"] = r["judge"]
        if args.dr_check and serp:
            ev = json.load(open(evidence_file_for("serponly")))
            annotate_backlinks(records, ev, backlinks_check(ev, args.dr_check))
        sheet = write_sheet(records, "?", "serp-only 复判", len(records))
        print(json.dumps({"sheet": sheet, "n": len(records),
                          "evidence": str(evidence_file_for("serponly"))}, ensure_ascii=False))
        return

    if args.from_rising:
        return run_rising_pipeline(json.load(open(args.from_rising)), args)

    th = TRACKS[args.track]

    # 1) 数据源捞词
    raw: list[dict] = []
    source_parts = []
    if args.seeds or args.roots:
        words = pick_words(args.seeds or args.roots, args.all)
        if not args.trends_only:
            raw += research_words(words)
        source_parts.append(f"种子{len(words)}")
        if args.track == "old" and not args.no_expand:
            expanded = autocomplete_expand(words)
            raw += expanded
            source_parts.append(f"长尾{len(expanded)}")
    if args.competitor:
        if args.trends_only:
            ap.error("--trends-only 不支持竞品排名词数据；移除 --competitor 或启用 --allow-paid。")
        domains = [d.strip() for d in args.competitor.split(",") if d.strip()]
        comp_rows = competitor_words(domains, th["min_volume"])
        raw += comp_rows
        source_parts.append(f"对手{len(domains)}")
        # 方式二闭环（SOP 方式二）：对手 top 词自动回流当种子扩长尾（重复方式一 2/4 步）
        if args.track == "old" and not args.no_expand and args.reflow > 0:
            seen: set[str] = set()
            reflow_seeds: list[str] = []
            for r in sorted(comp_rows, key=lambda x: -int(x.get("searchVolume") or 0)):
                k = str(r.get("keyword", "")).strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    reflow_seeds.append(k)
                if len(reflow_seeds) >= args.reflow:
                    break
            if reflow_seeds:
                rb = autocomplete_expand(reflow_seeds)
                for r in rb:
                    r["_root"] = "回流:" + r["_root"].removeprefix("长尾:")
                raw += rb
                source_parts.append(f"回流长尾{len(rb)}")
                print(f"# 方式二回流：top{len(reflow_seeds)} 对手词 → 联想扩出 {len(rb)} 长尾",
                      file=sys.stderr)
                if args.reflow_research:
                    rr = research_words(reflow_seeds)
                    for r in rr:
                        r["_root"] = "回流研究:" + r["_root"]
                    raw += rr
                    source_parts.append(f"回流研究{len(rr)}")

    if not raw:
        sys.exit("没有数据源：请给 --seeds/--roots/--competitor 之一（--from-rising 走两段式流程）")

    # 2) 初筛（轨道B 的 from-rising 词量未知，进趋势阶段再判）
    survivors: dict[str, dict] = {}
    for r in raw:
        kw = str(r.get("keyword", "")).strip().lower()
        vol = int(r.get("searchVolume") or r.get("search_volume") or 0)
        if not kw or kw in survivors:
            continue
        if args.track == "old" and vol < th["min_volume"] and not args.trends_only:
            continue
        survivors[kw] = {"kw": kw, "root": r["_root"], "vol": vol,
                         "kd": r.get("keywordDifficulty") or r.get("keyword_difficulty"),
                         "cpc": r.get("cpc"), "competition": r.get("competition"),
                         "intent": r.get("intent") or r.get("main_intent") or ""}
    print(f"# 捞词 {len(raw)} 行，初筛后 {len(survivors)} 词", file=sys.stderr)

    # 3) 月趋势 + 判定（--trends-only 时用免费 Google Trends 直连替代 DataForSEO）
    if args.trends_only:
        trends = multiramp_trends(sorted(survivors)) if survivors else {}
    else:
        trends = fetch_trends(sorted(survivors)) if survivors else {}
    records = []
    for kw, s in survivors.items():
        t = trends.get(kw, {})
        if t:
            s["vol"] = int(t.get("search_volume") or s["vol"])
            s["kd"] = t.get("keyword_difficulty", s["kd"])
            s["intent"] = t.get("main_intent") or s["intent"]
            s["competition"] = t.get("competition", s["competition"])
        s["first"], s["signal"] = emerge_info(t)
        s["judge"] = judge(args.track, s["vol"], s["kd"], s["signal"],
                            vol_quality=t.get("vol_quality") if t else "")
        if kw not in trends:
            s["judge"] = "观察：趋势数据缺失"
        records.append(s)

    # 4) 盘面验证（--trends-only 则跳过 DataForSEO SERP）
    cands = [r for r in records if r["judge"].startswith("候选")]
    cands.sort(key=lambda x: -x["vol"])
    to_check = cands[:args.top_serp]
    ev_path = evidence_file_for(args.track)
    if args.trends_only:
        print("# --trends-only：跳过 DataForSEO SERP 盘面（留待人工/AI判定）", file=sys.stderr)
        serp = {}
        for r in to_check:
            serp[r["kw"]] = {"verdict": "候选：trends-only 不做SERP，须AI判定",
                             "serp": "跳过（trends-only）"}
    else:
        serp = phase3_serp(to_check, ev_path)
    for r in records:
        if r in to_check and r["kw"] in serp:
            r["serp"], r["final"] = serp[r["kw"]]["serp"], serp[r["kw"]]["verdict"]
            r["dedicated"], r["inner"] = serp[r["kw"]]["dedicated"], serp[r["kw"]]["inner"]
        else:
            r["final"] = r["judge"]
    if args.export_monthly:
        export_monthly([trends], args.export_monthly)
    if args.dr_check and serp:
        evidence = json.load(open(ev_path))
        annotate_backlinks(records, evidence, backlinks_check(evidence, args.dr_check))

    records.sort(key=lambda x: (0 if str(x["final"]).startswith(("立项", "候选")) else
                                1 if str(x["final"]).startswith("观察") else 2, -x["vol"]))

    # P3/P4：拟立项 / 候选 → 字母轮询扩长尾（免费）+ KGR 免费校验（免费）
    if args.alphabet:
        from collections import OrderedDict
        seeds_for_alphabet = [r["kw"] for r in records
                              if str(r["final"]).startswith(("立项", "候选"))][:10]
        for seed in seeds_for_alphabet:
            suggestions = autocomplete_alphabet_ramp(seed)
            new_words = [s for s in suggestions
                         if s not in {r["kw"] for r in records}]
            for s in new_words[:30]:
                records.append({"kw": s, "root": f"字母轮询:{seed}",
                                "track": args.track, "vol": 0, "kd": None,
                                "intent": "", "cpc": None, "competition": None,
                                "first": "", "signal": "待查趋势",
                                "judge": "候选：字母轮询扩展（待查量）", 
                                "serp": "", "final": "候选：字母轮询扩展"})
        print(f"# 字母轮询新增 {sum(1 for r in records if str(r.get('root','')).startswith('字母轮询'))} 词", file=sys.stderr)

    if args.kgr:
        n_kgr = 0
        for r in records:
            if str(r["final"]).startswith(("立项", "候选")) and (r.get("vol") or 0) > 0:
                kgr = kgr_check(r["kw"], int(r["vol"]))
                if kgr["kgr"] is not None:
                    note = f"KGR={kgr['kgr']:.2f}"
                    if kgr["kgr"] < 0.25:
                        note += "（蓝海）"
                    elif kgr["kgr"] < 1.0:
                        note += "（观察）"
                    else:
                        note += "（饱和，降观察）"
                    r["note"] = str(r.get("note", "")) + " | " + note if r.get("note") else note
                    if kgr["kgr"] >= 1.0:
                        r["final"] = str(r["final"]).replace("立项", "观察").replace("候选", "观察")
                    n_kgr += 1
        print(f"# KGR 校验 {n_kgr} 词", file=sys.stderr)

    sheet = write_sheet(records, args.track, "+".join(source_parts), len(raw))
    final = {}
    for r in records:
        key = str(r["final"]).split("：")[0]
        final[key] = final.get(key, 0) + 1
    print(json.dumps({"ledger": str(LEDGER), "sheet": sheet, "final": final,
                      "n": len(records), "evidence": str(ev_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
