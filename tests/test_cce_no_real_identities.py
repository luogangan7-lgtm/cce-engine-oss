#!/usr/bin/env python3
"""仓内不得出现真实身份 —— 本地不变量, **不依赖识别层**。

## 为什么要有它, 而不是只靠 check_boundary
check_boundary 的做法是: 从识别层的结构化身份字段收全真名, 再去公开仓字面匹配。
它很有效(2026-09-03 就是它抓到的), 但它**只能抓识别层认识的人** ——
一个从未进过识别层的 handle 混进仓里, 它看不见。
而且它要扫两棵树, 跑一次约两分钟, 不适合进每次都跑的测试集。

## 这条闸问的是另一个问题
手册规定「actor_ref 里本来就只能写化名」。那是**仓库这一侧自己就能验的不变量**:
任何 actor_ref, 要么匹配化名前缀, 要么就是违规 —— 不需要知道那个人是谁。

## 它是怎么被逼出来的
2026-09-03 我取回 23 个历史 run(391 文件)提交进仓, **没有重跑边界闸**。
其中一个 run 的 actor_ref 是未化名的真实论坛 handle。本仓可 fast-forward 到公开仓,
差一步就推出去了。★ 真名不在本文件复述 —— 我第一版把它抄进反向用例里,
结果边界闸把这个文件本身也判成了泄露源。**记录泄露不等于复述泄露。**
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ID_FIELDS = {"actor_ref", "author", "username", "handle", "commenter", "op"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
CB = "/Volumes/data/cce-identified-vault/check_boundary.py"
VENDORED = os.path.join(ROOT, "config", "cce_identity_allowlists.json")

# ★ 表**落进仓当数据**, 不再运行时从保险库读。
#   2026-09-03 CI 实跑暴露: 保险库是故意只在本地的(它持有识别层), CI 上没有那个路径
#   ⇒ 原来的「运行时读」在 CI 必红。而修法**不能**是「CI 上跳过扫描」——
#   那是静默降级, 保护恰好在权威处消失。
#   ⇒ 扫描(真正的保护)到处都跑; 与保险库的**漂移检查**只在有保险库的机器上跑。
_V = json.load(open(VENDORED, encoding="utf-8"))
PSEUDONYM_PREFIXES = tuple(_V["pseudonym_prefixes"])
ALLOW = set(_V["allow"]) | set(_V["mention_allow"])
ALLOW |= {"", "None", "null"}


def is_pseudonym(v: str) -> bool:
    tail = v.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return (tail in ALLOW or v in ALLOW
            or any(tail.startswith(p) for p in PSEUDONYM_PREFIXES))


def walk(o, path, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ID_FIELDS and isinstance(v, str) and not is_pseudonym(v):
                out.append((path, k, v))
            walk(v, path, out)
    elif isinstance(o, list):
        for x in o:
            walk(x, path, out)


bad, scanned = [], 0
for dirpath, dirnames, files in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fn in files:
        if not fn.endswith(".json"):
            continue
        p = os.path.join(dirpath, fn)
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        scanned += 1
        walk(d, os.path.relpath(p, ROOT), bad)

# 本文件自己举的反例不算(它是文档, 不是数据)
bad = [b for b in bad if not b[0].startswith("tests/test_cce_no_real_identities")]
assert not bad, ("★ 仓内出现非化名的身份字段:\n" +
                 "\n".join(f"  {p}: {k}={v!r}" for p, k, v in bad[:10]))

# ── 反向: 探测器必须真的会响 ──────────────────────────────────────────
probe = []
walk({"items": [{"reader": {"actor_ref": "forum:user/SomeRealHandle+Other"}}]}, "probe", probe)
assert probe, "★ 探测器失效: 真实 handle 没被抓到"
ok = []
for good in ("reddit:u/user_47", "reddit:u/self_op", "redacted_3", "creator_1"):
    walk({"actor_ref": good}, "probe", ok)
assert not ok, f"★ 化名被误报: {ok}"

# ── 表本身要像样 ──────────────────────────────────────────────────────
assert len(PSEUDONYM_PREFIXES) >= 4 and "user_" in PSEUDONYM_PREFIXES, PSEUDONYM_PREFIXES
assert "auto-sticky" in ALLOW, \
    "★ 放行表不全 —— 我第一版手抄时就漏了它, 所以这条断言留着"

# ── ★ 漂移检查: 只在**有保险库**的机器上跑, 且必须真跑(不许因缺席而恒真) ──
if os.path.exists(CB):
    _src = open(CB, encoding="utf-8").read()
    _pre = re.search(r"PSEUDONYM_PREFIXES\s*=\s*\(([^)]*)\)", _src)
    assert _pre, "★ 边界闸里找不到化名表 —— 它的结构变了, 本闸必须同步"
    _theirs = tuple(x.strip().strip('"\'') for x in _pre.group(1).split(",") if x.strip())
    assert set(_theirs) == set(PSEUDONYM_PREFIXES), \
        f"★ 与保险库漂移了: 仓内 {PSEUDONYM_PREFIXES} vs 边界闸 {_theirs} —— 重新落表"
    _drift = "已比对(本机有保险库)"
else:
    _drift = "未比对(CI 无保险库) —— 扫描仍全量跑, 只是漂移检查在此不可执行"
assert "落进仓当数据" in _V["★why_vendored"]

print(f"test_cce_no_real_identities: OK (扫 {scanned} 个 JSON · 身份字段全为化名 | "
      "反向: 真实 handle 见红 · 四种化名不误报 | 漂移: " + _drift + ")")
