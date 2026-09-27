# -*- coding: utf-8 -*-
"""闸: owner 的 gold 裁定只登记在 suites/gold_adjudications.json; 已运行的 suite 不改; 此后任何 suite 碰到同一 (文本 sha, 面) 必须用裁定后的接受集合。"""
import hashlib
import json
from pathlib import Path

JEV = Path(__file__).resolve().parents[1]
REG = json.loads((JEV / "suites" / "gold_adjudications.json").read_text(encoding="utf-8"))
FROZEN = {"s0-smoke-v1": "0beb544cf6b0db28e36f5f75a24c866638abba717f5dc667fe7ddbabfc33c2cd",   # 已运行: 36265705004
          "s0-compare-v1": "3718ebbe2f9e4a14aea87f8ef6d8001d8d79b3669dd23b59f3ad6a8d51545486"}  # 已运行: 36272175531


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_already_run_suites_are_untouched():
    for sid, h in FROZEN.items():
        assert hashlib.sha256((JEV / "suites" / f"{sid}.jsonl").read_bytes()).hexdigest() == h, sid


def test_adjudications_are_well_formed_and_owner_attributed():
    tax = json.loads((JEV.parents[1] / "config" / "context_taxonomy.json").read_text(encoding="utf-8"))
    vals = {f["key"]: f["values"] for f in tax["facets"]}
    for a in REG["adjudications"]:
        assert a["decided_by"].startswith("owner") and a["was"] != a["now"] and a["post_hoc_note"]
        assert all(v in vals[a["key"]["facet"]] for v in a["now"])


def test_later_suites_must_use_adjudicated_gold():
    adj = {(a["key"]["text_sha256"], a["key"]["facet"]): a["now"] for a in REG["adjudications"]}
    for p in sorted((JEV / "suites").glob("*.jsonl")):
        if p.stem in FROZEN:
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            it = json.loads(line)
            if "text" not in it:
                continue
            for facet, acc in it.get("expected", {}).items():
                want = adj.get((_sha(it["text"]), facet))
                assert want is None or sorted(acc) == sorted(want), f"{p.name}:{it['item_id']}/{facet} ignores an owner adjudication"
