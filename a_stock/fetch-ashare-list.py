#!/usr/bin/env python3
"""Fetch full A-share code list from EastMoney push2.

Output: data/a_share_list.json
"""
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "a_share_list.json"
PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"
FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"  # SH+Sz A-shares
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}


def fetch_page(page: int) -> tuple[list[dict], int]:
    params = {
        "pn": page, "pz": 500, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fid": "f12", "fs": FS, "fields": "f12,f14",
    }
    url = f"{PUSH2}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    diff = data.get("data", {}).get("diff", [])
    total = data.get("data", {}).get("total", 0)
    return [{"code": d["f12"], "name": d["f14"]} for d in diff], total


def fetch_via_akshare() -> list[dict]:
    """Fallback: use akshare (wraps multiple sources, more reliable)."""
    import akshare as ak
    df = ak.stock_info_a_code_name()
    return [{"code": str(row["code"]).zfill(6), "name": row["name"]}
            for _, row in df.iterrows()]


def main():
    rows: list[dict] = []
    try:
        page = 1
        while True:
            batch, total = fetch_page(page)
            if not batch:
                break
            rows.extend(batch)
            print(f"  push2 page {page}: +{len(batch)} (total {len(rows)}/{total})")
            if len(rows) >= total:
                break
            page += 1
    except Exception as e:
        print(f"  push2 failed: {e}; falling back to akshare...")

    if len(rows) < 100:
        rows = fetch_via_akshare()
        print(f"  akshare returned {len(rows)} stocks")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"count": len(rows), "stocks": rows},
                              ensure_ascii=False, indent=2))
    print(f"\nSaved {len(rows)} stocks → {OUT}")


if __name__ == "__main__":
    main()
