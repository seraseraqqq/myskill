#!/usr/bin/env python3
"""阶段 0：词根 → 谷歌趋势飙升相关查询（Google Trends 官方前端，免登录，$0）。

对应哥飞流程第 1 步「词根捞上升」的自动化实现：逐词根拉过去 N 天的
related queries → rising 榜，合并去重后交给后续阶段验体量/盘面。

所有数据直连 trends.google.com 前端内部接口（/trends/api/*），不通过任何
第三方平台取趋势——保证天级新鲜度，不受平台收录
滞后影响。被限流（429）时按 SKILL.md 的接管规则退避，不花钱。

用法:
  python trends_pull.py --roots ai,checker          # 指定词根，默认 7 天窗口
  python trends_pull.py --all --days 30             # 全量词根，30 天窗口
  python trends_pull.py --roots flux --days 90      # 最长支持 90 天（3 个月窗口）
  python trends_pull.py --roots ai --min-pct 1000   # 只留上升 ≥1000% 的

输出: JSON 到 stdout（{query, value, roots[]} 列表，按上升幅度降序），
stderr 打印词根进度。可用 --out 存文件。
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

FREE_HOST = "https://trends.google.com"
BREAKOUT = 999999   # "Breakout" 的内部排序值

# Google Trends 网页端时间窗（days 越小越新鲜，90 上限）
WINDOWS = {
    7: "now 7-d",
    30: "today 1-m",
    90: "today 3-m",
}


def _free_get(path: str, params: dict, opener, headers: dict, tries: int = 3) -> dict:
    """抓 Google Trends 网页前端的未公开内部接口（免费，无官方 SLA）。

    响应统一带 XSSI 前缀 ")]}'"，剥掉再解析。
    429 时退避（3/6/12 秒），仍然 429 抛给上层跳过并计数。"""
    url = FREE_HOST + path + "?" + urllib.parse.urlencode(
        {"hl": "en-US", "tz": "-480", **params})
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", "ignore")
            if raw.startswith(")]}'"):
                raw = raw.split("\n", 1)[1]
            return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 3 * (2 ** attempt)   # 3/6/12s
                print(f"# 429 {path}，退避 {wait}s (attempt {attempt+1})", file=sys.stderr)
                time.sleep(wait)
                last = e
            else:
                raise
    raise last


def _new_opener():
    """带 cookie jar 的 opener：先访问 /trends/ 拿初始化 cookie，再调内部接口。"""
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open(FREE_HOST + "/trends/", timeout=30).read()
    return opener


def pull_free(roots: list[str], days: int) -> tuple[list[dict], float]:
    """免费通道主流程：explore → RELATED_QUERIES widget → relatedsearches → rising 榜。

    与旧版（DataForSEO）返回同格式（query/value/roots），cost 恒 0。
    每词根间隔 1.2s：Google 限流按行为频率而非绝对次数，住宅 IP 日频 115 词根实测可跑。
    失败词根跳过并计数；失败率 >30% 时提示 1 小时后重试（无付费退路——数据只走 Google Trends）。"""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    window = WINDOWS.get(min(days, 90), "now 7-d" if days <= 7 else "today 1-m")
    opener = _new_opener()   # cookie 初始化，降低 429
    merged: dict[str, dict] = {}
    fails = 0
    for root in roots:
        try:
            exp = _free_get("/trends/api/explore", {"req": json.dumps({
                "comparisonItem": [{"keyword": root, "geo": "US", "time": window}],
                "category": 0, "property": ""})}, opener, headers)
            rel = next((w for w in exp.get("widgets", [])
                        if w.get("id") == "RELATED_QUERIES"), None)
            if not rel:
                fails += 1
                print(f"# {root}: 无 RELATED_QUERIES widget", file=sys.stderr)
                continue
            wreq = rel.get("request") or {}
            wreq["metric"] = ["TOP", "RISING"]   # 明确两个榜都拉，返回顺序 [TOP, RISING]
            data = _free_get("/trends/api/widgetdata/relatedsearches",
                             {"token": rel.get("token"), "req": json.dumps(wreq)},
                             opener, headers)
            ranked = (data.get("default") or {}).get("rankedList") or []
            rising = ranked[1] if len(ranked) >= 2 else (ranked[0] if ranked else {})
            n = 0
            for rk in rising.get("rankedKeyword") or []:
                query = str(rk.get("query", "")).strip().lower()
                value = rk.get("value")
                if not query or value is None:
                    continue
                pct = BREAKOUT if value == "Breakout" else int(value)
                n += 1
                if query in merged:
                    merged[query]["roots"].append(root)
                    merged[query]["pct"] = max(merged[query]["pct"], pct)
                else:
                    merged[query] = {"query": query, "pct": pct, "roots": [root]}
            print(f"# {root}: rising {n} 个", file=sys.stderr)
        except Exception as e:
            fails += 1
            print(f"# {root} 失败: {e}", file=sys.stderr)
        time.sleep(1.2)
    rows = sorted(merged.values(), key=lambda x: -x["pct"])
    if fails > max(3, len(roots) * 0.3):
        print(f"# 警告：{fails}/{len(roots)} 词根失败，Google 在限流。"
              f"1 小时后重试，或减少词根数量/换 IP", file=sys.stderr)
    return rows, 0.0


# ── GPTs 倍数（哥飞标准：近 N 天热度是 GPTs 的多少倍，同样直连 Google Trends） ──
COMPARE_PER_BATCH = 4   # Google Trends 对比上限 5 个词 = 4 个待测词 + "gpts" 基准


def pull_heat(words: list[str], days: int, base: str = "gpts") -> tuple[dict[str, float], float]:
    """逐批把待测词与基准词（默认 "gpts"）放同一请求对比。

    Google Trends multiline endpoint 同一请求内归一化，比值即「GPTs 倍数」。
    返回 {词: GPTs倍数}：近 days 天该词趋势均值 / 同窗口基准词趋势均值。
    直连 Google Trends，$0；与 trends_pull 主流程共用同一个 opener（共享 cookie 降低限流）。"""
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    _opener = _new_opener()  # heat 也走同一个入口，共用 cookie jar
    window = WINDOWS.get(min(days, 90), "now 7-d" if days <= 7 else "today 1-m")
    out: dict[str, float] = {}
    for i in range(0, len(words), COMPARE_PER_BATCH):
        batch = [w for w in words[i:i + COMPARE_PER_BATCH] if w and w != base]
        if not batch:
            continue
        keywords = batch + [base]
        try:
            exp = _free_get("/trends/api/explore", {"req": json.dumps({
                "comparisonItem": [{"keyword": k, "geo": "US", "time": window}
                                   for k in keywords],
                "category": 0, "property": ""})}, _opener, headers)
            ts = next((w for w in exp.get("widgets", [])
                       if w.get("id") == "TIMESERIES"), None)
            if not ts:
                print(f"# heat 批次 {batch}: 无 TIMESERIES widget（对比词太多或太冷门）",
                      file=sys.stderr)
                continue
            data = _free_get("/trends/api/widgetdata/multiline",
                             {"token": ts.get("token"),
                              "req": json.dumps(ts.get("request") or {})},
                             _opener, headers)
            tl = (data.get("default") or {}).get("timelineData") or []
            if not tl:
                print(f"# heat 批次 {batch}: 无图数据", file=sys.stderr)
                continue
            sums = [0.0] * len(keywords)
            cnts = [0] * len(keywords)
            for point in tl:
                vals = point.get("value") or []
                for j, v in enumerate(vals[:len(keywords)]):
                    if isinstance(v, (int, float)):
                        sums[j] += v
                        cnts[j] += 1
            base_avg = (sums[-1] / cnts[-1]) if cnts[-1] else 0
            for j, w in enumerate(batch):
                avg = (sums[j] / cnts[j]) if cnts[j] else 0
                if base_avg > 0 and avg > 0:
                    out[w] = round(avg / base_avg, 3)
        except Exception as e:
            print(f"# heat 批次 {batch} 失败: {e}", file=sys.stderr)
            continue
        print(f"# heat 批次 {i}-{i + len(batch)}: 累计 {len(out)} 个倍数", file=sys.stderr)
        time.sleep(1.0)
    return out, 0.0


def timeline_12m(word: str, window: str = "today 12-m", opener=None, headers=None) -> list[dict]:
    """拉一个词的 12 个月趋势曲线，用于出现时间判定（哥飞：12 个月找起点）。

    返回[{ts, v, t, hasData}]，t 为周窗区间（如 Oct 5 – 11, 2025），v 为 0-100 热度。
    首个非零点即哥飞定义的「出现时间」参照点。$0。"""
    if opener is None:
        opener = _new_opener()
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                  "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    exp = _free_get("/trends/api/explore", {"req": json.dumps({
        "comparisonItem": [{"keyword": word, "geo": "US", "time": window}],
        "category": 0, "property": ""})}, opener, headers)
    ts = next((w for w in exp.get("widgets", [])
               if w.get("id") == "TIMESERIES"), None)
    if not ts:
        return []
    data = _free_get("/trends/api/widgetdata/multiline",
                     {"token": ts.get("token"),
                      "req": json.dumps(ts.get("request") or {})},
                     opener, headers)
    tl = (data.get("default") or {}).get("timelineData") or []
    return [{"ts": p["time"], "v": p["value"][0], "t": p["formattedTime"],
             "hasData": p.get("hasData", [False])[0]} for p in tl]



def multiramp(words: list[str], out_file: str | None = None,
              rate_limit: float = 1.5, geo: str = "US") -> list[dict]:
    """批量词根拉 12 个月趋势曲线（轨道A --trends-only 的核心数据源，$0）。

    每词 1 次 explore + 1 次 multiline 请求（共 2 次 HTTP），间隔 rate_limit 秒。
    输出[{word, first_nonzero, first_v, peak_v, peak_t, recent30_avg, baseline_avg,
          signal}]，signal 判定同哥飞口径：
      - 新词：前9月全零/近零 + 近期有量
      - 近期起量：近3月 ≥ 前9月×3
      - 老词热点：基线低 + 近期有量（Ghibli 型，非新词）
      - 平稳：无明显起量
    可 --out 落盘中断续跑（跳过 word 列已有的）。"""
    opener = _new_opener()
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
    done: set = set()
    rows: list[dict] = []
    if out_file and os.path.exists(out_file):
        try:
            rows = json.load(open(out_file))
            done = {r["word"] for r in rows}
            print(f"# 续跑：已完成 {len(done)} 词", file=sys.stderr)
        except Exception:
            rows = []
    for i, w in enumerate(words, 1):
        if w in done:
            continue
        try:
            tl = timeline_12m(w, "today 12-m", opener=opener, headers=headers)
        except Exception as e:
            print(f"# {w} 拉取失败: {e}", file=sys.stderr)
            rows.append({"word": w, "first_nonzero": None, "first_v": 0,
                         "peak_v": 0, "peak_t": "", "recent30_avg": 0,
                         "baseline_avg": 0, "signal": "拉取失败"})
            continue
        vals = [p["v"] or 0 for p in tl]
        nonzero = [j for j, v in enumerate(vals) if v > 0]
        if not nonzero:
            rows.append({"word": w, "first_nonzero": None, "first_v": 0,
                         "peak_v": 0, "peak_t": "", "recent30_avg": 0,
                         "baseline_avg": 0, "signal": "无量：12月趋势全零"})
        else:
            first_i = nonzero[0]
            first = tl[first_i]
            peak_i = max(range(len(vals)), key=lambda j: vals[j])
            # 现在以周为单位（12m 窗口约 52 点）
            recent_pts = len(vals) * 30 // 365  # 近 30 天约合多少个周点
            recent = vals[-max(recent_pts, 2):]
            # baseline = 第一个非零点之前的全零段 + 起量后前半段
            n_pre = first_i
            n_post = len(vals) - first_i
            base_pts = vals[first_i:first_i + max(n_post // 2, 1)]  # 起量后前半段
            base_avg = sum(base_pts) / len(base_pts) if base_pts else 0
            recent_avg = sum(recent) / len(recent) if recent else 0
            if n_pre / max(len(vals), 1) >= 0.8:
                sig = "新词：12个月的80%时间为零，近期才起来"
            elif recent_avg >= base_avg * 3:
                sig = "近期起量：近30天均 ≥ 起量后前半均×3"
            elif base_avg > 0 and recent_avg < base_avg * 1.2:
                sig = "平淡：近期与起量后前半差不多"
            else:
                sig = "观察：趋势形态混合"
            rows.append({"word": w, "first_nonzero": first["t"], "first_v": first["v"],
                         "peak_v": vals[peak_i], "peak_t": tl[peak_i]["t"],
                         "recent30_avg": round(recent_avg, 1),
                         "baseline_avg": round(base_avg, 1), "signal": sig})
        print(f"# [{i}/{len(words)}] {w} → {rows[-1]['signal'][:30]}", file=sys.stderr)
        if out_file:
            with open(out_file, "w") as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)
        time.sleep(rate_limit)
    return rows



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", help="逗号分隔词根，默认词根库前 5 个")
    ap.add_argument("--all", action="store_true", help="全部词根")
    ap.add_argument("--days", type=int, default=7, choices=[7, 30, 90],
                    help="时间窗天数，Google Trends 网页端支持 7/30/90，默认 7")
    ap.add_argument("--min-pct", type=int, default=0, help="上升幅度下限，默认全留")
    ap.add_argument("--out", help="结果另存到文件")
    ap.add_argument("--heat", metavar="FILE", help="给飙升词 JSON 算 GPTs 倍数（与 gpts 对比）")
    ap.add_argument("--heat-days", type=int, default=7, choices=[7, 30, 90],
                    help="GPTs 倍数的时间窗，默认 7 天")
    ap.add_argument("--heat-cap", type=int, default=100, help="最多算多少个词的倍数（默认 100），$0")
    ap.add_argument("--heat-base", default="gpts", help="GPTs 倍数的基准词（默认 gpts，非 AI 赛道可换）")
    ap.add_argument("--timeline", metavar="WORD", help="单独拉一个词的 12 个月趋势曲线（验出现时间）")
    ap.add_argument("--multiramp", metavar="FILE",
                    help="批量拉多个词根的 12 月趋势（FILE=逗号分隔词根列表文件或 JSON 词文件），"
                         "出 first_nonzero/peak/recent30/baseline/signal；--out 落盘可断点续跑")
    ap.add_argument("--rate-limit", type=float, default=1.5,
                    help="multiramp 每词间隔秒数（默认 1.5s，防限流）")
    args = ap.parse_args()

    if args.multiramp:
        src_txt = args.multiramp
        from_stream = src_txt in ("/dev/stdin", "-")
        if from_stream:
            import sys as _sys
            words = [r.strip().lower() for r in _sys.stdin.read().splitlines()]
        else:
            try:
                items = json.load(open(src_txt))
                words = [str(r.get("query") or r.get("word") or r).strip().lower()
                         for r in items]
                words = [w for w in words if w and w != "query" and "{" not in w]
            except (json.JSONDecodeError, FileNotFoundError, IsADirectoryError):
                words = [r.strip().lower() for r in open(src_txt).read().splitlines()]
            except AttributeError:
                words = []
        words = [w for w in words if w]
        words = list(dict.fromkeys(words))   # 去重保持序
        rows = multiramp(words, out_file=args.out, rate_limit=args.rate_limit)
        out = json.dumps(rows, ensure_ascii=False, indent=1)
        if not args.out:
            print(f"# 请用 --out 存文件（{len(rows)} 词，stdout 也会打印）", file=sys.stderr)
        print(json.dumps(rows, ensure_ascii=False, indent=1))
        return

    if args.timeline:
        words = [args.timeline]
        if os.path.exists(args.timeline):
            rows = json.load(open(args.timeline))
            words = [r["query"] for r in rows]
        for w in words:
            tl = timeline_12m(w, "today 12-m")
            vals = [p["v"] for p in tl]
            nonzero = [i for i, v in enumerate(vals) if v > 0]
            first = tl[nonzero[0]]["t"] if nonzero else None
            print(json.dumps({"word": w, "points": len(tl),
                              "nonzero": len(nonzero),
                              "first_nonzero": first}, ensure_ascii=False))
        return

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots = [r.strip() for r in (args.roots.split(",") if args.roots else [])
             if r.strip()]
    if not roots:
        lib = [r.strip() for r in open(os.path.join(base, "assets", "词根库.txt")) if r.strip()]
        roots = lib if args.all else lib[:5]

    print(f"# 词根 {len(roots)} 个 | 窗口 {args.days} 天 | 免费（Google Trends 直连，$0）",
          file=sys.stderr)
    rows, cost = pull_free(roots, args.days)
    rows = [r for r in rows if r["pct"] >= args.min_pct]
    for r in rows:
        r["value"] = "Breakout" if r["pct"] >= BREAKOUT else r["pct"]
        del r["pct"]
    print(f"# 合并后 {len(rows)} 个飙升词 | 总花费 ${cost:.4f}", file=sys.stderr)

    out = json.dumps(rows, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
        print(f"# 已存 {args.out}", file=sys.stderr)
    print(out)


if __name__ == "__main__":
    main()
