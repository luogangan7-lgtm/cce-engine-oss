#!/usr/bin/env python3
"""Phase 2 base text 候选池 —— **T-盲**的机械选取规则（跑前冻结）。

为什么要单独一个脚本而不是手挑:
  「按观测 T 挑 base」= selection-on-outcome, 与当初挑「边界对」同性质。
  故选取规则只能用**测量前可观测**的特征: 来源、长度、去重、语言。
  规则写死在这里, 扩展块(+8)也**只能**用同一规则往下取, 不许看结果再选。

来源: run_items/*.json 的 `reader` 字段 —— 抓取时保存的**真人原文**(非我方生成)。
"""
import json, sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

# ── 前登记的选取规则（改这里 = 改设计, 必须重新前登记）─────────────────────
MIN_LEN, MAX_LEN = 150, 2000     # 下界: 太短撑不起 5 个扰动臂; 上界: 撰写与调用成本
SORT_KEY = "sha1"                # ★ 排序键必须与结果无关 —— 用内容哈希, 不用长度/来源
EXCLUDE_DOMAINS = ()             # 暂无


def harvest():
    seen = {}
    for f in sorted((ROOT / "run_items").glob("*.json")):
        for it in json.loads(f.read_text(encoding="utf-8")):
            t = (it.get("reader") or "").strip()
            if not t:
                continue
            seen.setdefault(t, {"url": it.get("url", ""), "first_file": f.name})
    import hashlib
    rows = []
    for t, meta in seen.items():
        dom = urlparse(meta["url"]).netloc
        if dom in EXCLUDE_DOMAINS:
            continue
        if not (MIN_LEN <= len(t) <= MAX_LEN):
            continue
        rows.append({"sha1": hashlib.sha1(t.encode()).hexdigest()[:12],
                     "len": len(t), "domain": dom, "url": meta["url"],
                     "first_file": meta["first_file"], "text": t})
    rows.sort(key=lambda r: r[SORT_KEY])
    return rows


if __name__ == "__main__":
    rows = harvest()
    print(f"候选池 n={len(rows)}  (规则: {MIN_LEN}<=len<={MAX_LEN}, 去重, 按 {SORT_KEY} 排序)")
    print("  来源:", dict(Counter(r["domain"] for r in rows)))
    b = Counter("<300" if r["len"] < 300 else "300-600" if r["len"] < 600
                else "600-1200" if r["len"] < 1200 else "1200-2000" for r in rows)
    print("  长度分箱:", dict(b))
    out = ROOT / "tests" / "data" / "phase2" / "base_pool_candidates.json"
    if "--freeze" in sys.argv:
        out.write_text(json.dumps({"rule": {"min_len": MIN_LEN, "max_len": MAX_LEN,
                                            "sort_key": SORT_KEY, "source": "run_items/*.json:reader",
                                            "t_blind": True},
                                   "n": len(rows), "rows": rows},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        print("  已冻结 →", out.relative_to(ROOT))
