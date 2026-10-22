#!/usr/bin/env python3
"""Small direct DataForSEO v3 client used by mine_round.py."""
import base64
import json
import os
import urllib.error
import urllib.request


BASE_URL = os.environ.get("DATAFORSEO_BASE_URL", "https://api.dataforseo.com/v3").rstrip("/")
LOCATION_CODE = int(os.environ.get("DATAFORSEO_LOCATION_CODE", "2840"))
LANGUAGE_CODE = os.environ.get("DATAFORSEO_LANGUAGE_CODE", "en")


class DataForSEOError(RuntimeError):
    pass


class Client:
    def __init__(self, login=None, password=None, timeout=90):
        self.login = (login or os.environ.get("DATAFORSEO_LOGIN", "")).strip()
        self.password = password or os.environ.get("DATAFORSEO_PASSWORD", "")
        self.timeout = timeout
        self.cost_usd = 0.0
        self.calls = 0
        if not self.login or not self.password:
            raise DataForSEOError("请设置 DATAFORSEO_LOGIN 和 DATAFORSEO_PASSWORD。")

    def post(self, endpoint, tasks):
        credentials = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        request = urllib.request.Request(
            f"{BASE_URL}/{endpoint.lstrip('/')}",
            data=json.dumps(tasks).encode("utf-8"),
            headers={"Authorization": f"Basic {credentials}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise DataForSEOError(f"DataForSEO HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            # Do not automatically retry paid POSTs: a timed-out request may have been billed.
            raise DataForSEOError(f"DataForSEO 网络请求结果不确定，未自动重试: {exc}") from exc

        self.calls += 1
        self.cost_usd += float(payload.get("cost") or 0)
        if payload.get("status_code", 0) >= 40000:
            raise DataForSEOError(
                f"DataForSEO {payload.get('status_code')}: {payload.get('status_message')}"
            )
        tasks = payload.get("tasks") or []
        for task in tasks:
            if task.get("status_code", 0) >= 40000:
                raise DataForSEOError(
                    f"DataForSEO task {task.get('status_code')}: {task.get('status_message')}"
                )
        return tasks

    @staticmethod
    def items(tasks):
        out = []
        for task in tasks:
            for result in task.get("result") or []:
                out.extend(result.get("items") or [])
        return out

    @staticmethod
    def task_cost(tasks):
        return sum(float(task.get("cost") or 0) for task in tasks)

    def keyword_ideas(self, seeds, limit=100):
        tasks = self.post("dataforseo_labs/google/keyword_ideas/live", [{
            "keywords": [seed], "location_code": LOCATION_CODE,
            "language_code": LANGUAGE_CODE, "limit": limit,
        } for seed in seeds])
        return tasks

    def ranked_keywords(self, domain, limit=100, min_volume=0):
        return self.post("dataforseo_labs/google/ranked_keywords/live", [{
            "target": domain, "location_code": LOCATION_CODE,
            "language_code": LANGUAGE_CODE, "limit": limit,
            "filters": ["keyword_data.keyword_info.search_volume", ">=", min_volume],
            "order_by": ["keyword_data.keyword_info.search_volume,desc"],
        }])

    def search_volume(self, keywords):
        return self.post("keywords_data/google_ads/search_volume/live", [{
            "keywords": keywords, "location_code": LOCATION_CODE,
            "language_code": LANGUAGE_CODE,
        }])

    def bulk_keyword_difficulty(self, keywords):
        return self.post("dataforseo_labs/google/bulk_keyword_difficulty/live", [{
            "keywords": keywords, "location_code": LOCATION_CODE,
            "language_code": LANGUAGE_CODE,
        }])

    def serp(self, keyword, depth=10):
        return self.post("serp/google/organic/live/advanced", [{
            "keyword": keyword, "location_code": LOCATION_CODE,
            "language_code": LANGUAGE_CODE, "depth": depth,
        }])

    def backlinks_summary(self, domain):
        return self.post("backlinks/summary/live", [{"target": domain}])
