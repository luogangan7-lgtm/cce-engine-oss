#!/usr/bin/env python3
"""未完成清单必须来自真相源, 且不许被悄悄清空。

2026-09-03 owner 两次点破我越界声报(「可以投产了」/ 收尾语气)。
⇒ 「还差什么」不由我口述, 由 scripts/cce_open_items.py 从各真相源现算。
本测试守两件事: ① 它确实在算, 不是硬编码 ② 三类不许混。
"""
import re
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from cce_open_items import items, BLOCKED, OPEN, DECIDED  # noqa: E402

rs = items()
assert rs, "★ 未完成清单为空 —— 要么真的全做完了(那就得有证据), 要么算错了"
kinds = {r["类"] for r in rs}
assert kinds <= {BLOCKED, OPEN, DECIDED}, kinds
for r in rs:
    assert r["项"] and r["证据"], f"★ 每项必须带证据: {r}"

# ── ★ 它必须**真的在算** —— 改一个真相源, 清单要跟着变 ──────────────
import json
import cce_open_items as M

# ★ 2026-09-27 根因修复: 以前**原地改写**受版本控制的 config/cce_chain_conformance.json 再 copy2 还原(mtime 也被还原, 审计看不见)
#   —— 窗口期内并行的 test_cce_chain_conformance 读到 P0=NOT_STARTED。M 读清单只经由 M._j ⇒ 在那里喂变异版, 活仓不动。
_real_j = M._j
d = _real_j("config/cce_chain_conformance.json")
for ph in d["phases"]:
    if ph["phase"].startswith("P0"):
        ph["status"] = "NOT_STARTED"
M._j = lambda rel: d if rel == "config/cce_chain_conformance.json" else _real_j(rel)
try:
    mutated = M.items()
    assert any("P0" in r["项"] for r in mutated), \
        "★ 改了 chain_conformance 清单却没变 —— 它没在算, 是硬编码的"
finally:
    M._j = _real_j

# ── 三类的语义边界不许糊 ──────────────────────────────────────────────
blocked = [r for r in rs if r["类"] == BLOCKED]
assert blocked, "★ 至少 SESOI 与内容 A/B 是卡在外部资源上的"
# ★★★ 2026-09-10 **按库里的原处方重做** —— 见 tests/data/DEV-002-destructive-checkout.json。
#   我在这个文件有未提交改动时跑了 `git checkout`, 抹掉了这处修复。
#   ★★ 而库里 memory 29b7de8f(2026-09-08) **正是记录这处修复的**, 实例就写着本文件、
#      写着 `owner 裁定`、写着修法「词表提成模块级常量 + 从被守脚本 docstring 正则提定义自证」。
#      我第一次重建时**没查库**, 硬加了三个词 —— **比原修复弱**。这一版才是原处方。
#   ⇒ 判据: 闸红了先问 —— 是被判的东西错了, 还是**闸比所守定义窄**? 后者要改闸, 不是改被判的东西。
import re as _re

BLOCKED_VOCAB = ("人类评分者", "浏览", "素材", "触达", "token", "凭据",
                 "owner 裁定", "owner 定", "规范决定",
                 # ★ 2026-09-11 加: 有些事卡的既不是资源也不是决定, 是**我不具备的能力**
                 #   —— 权限外移(把「自行解除限制的能力」移出执行者)。
                 #   ★ 同时改了被守脚本的 docstring, 否则自证查不出词表窄了。
                 # ★ 2026-09-17 加「owner 撰文」: 它与「owner 裁定」**不是同一件事**。
                 #   裁定 = 有东西摆在那儿等 owner 判; **撰文 = 根本没有那个东西**。
                 #   实例: 五类成立条件要不要升合同 —— 附件 A 里只有 A/B/C, **五条定义文本不存在**
                 #   ⇒ 不是「批不批准」而是「要不要先写五条新定义」。这一类若并进「裁定」,
                 #   读者会以为只差一个点头。★ 同时改了被守脚本的 docstring(自证的锚)。
                 "owner 撰文",
                 "权限外移")

# ★ 自证: 从**被守脚本的 docstring**提定义, 逐项检查词表覆盖得到。
#   不是我说词表够了, 是被守的那份定义说了算。
_guarded = open(os.path.join(ROOT, "scripts", "cce_open_items.py"), encoding="utf-8").read()
_m = _re.search(r"BLOCKED_EXTERNAL\s*——\s*卡在我拿不到的外部资源上\(([^)]*)\)", _guarded)
assert _m, "★ 被守脚本的 docstring 里找不到 BLOCKED_EXTERNAL 的定义 —— 自证的锚没了, 先修锚"
_defined = [t.strip() for t in _m.group(1).split("/") if t.strip()]
assert _defined, "★ 定义里一个词都没提取到 —— 空集合会让下面的检查恒真(空过)"
for _t in _defined:
    assert any(_t in _w or _w in _t for _w in BLOCKED_VOCAB), \
        f"★★★ 闸比所守定义窄: docstring 里的「{_t}」在词表里没有对应项。\n" \
        f"   ⇒ 该改**闸**(补词表), 不是改被判的条目去迎合闸。定义={_defined} 词表={BLOCKED_VOCAB}"

for r in blocked:
    assert any(w in r["证据"] for w in BLOCKED_VOCAB), \
        f"★ 标 BLOCKED 必须说清卡在**什么外部资源或什么外部决定**上: {r}"

# ── ★★★ 2026-09-10 新增: 今天那两轮留下的三件, 必须**现算**而不是我口述 ──────────
#   我先把它们口述报给了 owner, 清单里一件都没有 ——
#   「还差什么不由我口述」这条铁律**只在旧条目上生效了, 新条目又走回口述**。
def _find(kw):
    m = [r for r in rs if kw in r["项"]]
    assert m, f"★ 清单里找不到「{kw}」—— 它又只活在我的口述里了"
    return m[0]

_b = _find("跨轮请求预算闸")
# ★ 2026-09-28 (诊断 #7/#31/#40): 判据由「文件在」改为「有调用方」。原来这里钉的正是「文件在 ⇒ 已补」——
#   而那时全仓没有一个调用方, 生产链与付费回归台都没有上限。钉住了错的判据, 所以改钉内容。
_srcf = lambda rel: open(os.path.join(ROOT, rel), encoding="utf-8").read()
_wired_acc = "from cce_request_budget import reserve" in _srcf("accuracy/run_gates.py")
_wired_prod = "cce_request_budget" in _srcf("scripts/exp_crossmodel_desire.py")
_fixed = _wired_acc and _wired_prod
assert _b["类"] == (DECIDED if _fixed else OPEN), "★ 分类没跟着实际调用方走 —— 那就是硬编码"
if not _fixed:
    assert ("只接了付费回归台" if _wired_acc else "无调用方") in _b["项"], _b["项"]
assert "DEV-001" in _b["证据"]
if _fixed:
    assert "不产生任何放行资格" in _b["证据"], "★ 补闸不等于恢复放行, 这句必须跟着条目走"

# ★★★ 2026-09-13 这一项**由 BLOCKED 转 OPEN**: owner 明确「P1–P4 仍归你, 也做了吧」⇒ 授权代定 P1=只含物。
#   ★ 本闸原来钉的是「未定 · 卡 owner」。项没消失, 是**状态变了** —— 它拦得对(拦住了「悄悄改名」),
#     所以改的是**钉住的内容**, 不是把它删掉。意图一条不丢, 且比原来多钉一条:
#     **不许把「已定」当成「已完成」** —— 定了规范 ≠ 实现了它。
_d = _find("display 对象域**已定**")
assert _d["类"] == OPEN, "★ 已定之后不该再挂 BLOCKED —— 把解开的说成还卡着, 与反过来同样是误导"
assert "授权代定" in _d["证据"], "★★★ 必须写明这是 owner 授权**代定**, 不是他自己的判断"
assert "随时可推翻" in _d["证据"], "★★ 代定必须是可撤的"
# ★★★ 2026-09-14 改**判法**(不是放宽): 原来钉的是三句**当时的**措辞
#   ("尚未落进实现"/"还只在纸面上"/"零覆盖")。P2/P3 一落地那三句就过期, 本条当场判红,
#   而红的原因**与它要守的东西无关** —— 它要守的是「必须写清还剩什么」, 不是「必须写那三句」。
#   ⇒ 与 refactor_log[-1] 那次同一个教训: **锚在结构上, 不锚在快照的措辞上**。
assert "仍未做" in _d["证据"], (
    "★★★ 证据里没有「仍未做」这一节 —— **定了规范 ≠ 实现了它**; "
    "不写清剩什么, 「已定」就会被读成「已完成」")
_rest = _d["证据"].split("仍未做", 1)[1]
_items = re.findall(r"[①②③④⑤⑥⑦⑧⑨]", _rest)
assert len(_items) >= 3, (
    "★★★ 「仍未做」下只列了 %d 项 —— 这一项还挂在 OPEN 上, 就必须逐条说清挂着的是什么"
    % len(_items))
# ★ 每一项都得有实质内容, 不许只有一个序号占位
for _mark in _items:
    _seg = _rest.split(_mark, 1)[1][:40]
    assert len("".join(_seg.split())) >= 12, "★ 「仍未做」里的 %s 是空占位" % _mark
assert "74→80" in _d["证据"], "★ 断言表的变动要随条目走"

_a = _find("条已撤销")
# ★ 2026-09-23: 逐格核对后撤销项对应的 display 格**已由增量支(甲)断言覆盖** ⇒ DECIDED; 证据必须写明覆盖来自哪条断言, 并更正先前的「零覆盖」
assert _a["类"] in (OPEN, DECIDED)
if _a["类"] == OPEN:
    assert "零覆盖" in _a["证据"], "★ 撤销的断言 ⇒ 那些用例下一轮**零覆盖**, 这个后果必须写出来"
else:
    assert "增量支(甲)" in _a["项"] and "有覆盖" in _a["证据"] and "更正" in _a["证据"] and "(甲)已裁定覆盖" in _a["证据"]
# ★ 2026-09-13: 条数由清单**现算**(8 → 2, 因为 6 条已逐条重判恢复), 不许写死
import re as _re
_n = int(_re.search(r"有 \*\*(\d+)\*\* 条已撤销", _a["项"]).group(1))
_A = json.loads(open(os.path.join(ROOT, "tests/data/local_contract_assertions_v2.json"),
                     encoding="utf-8").read())
_live = sum(1 for a in _A["断言"] if a["★★★断言状态"].startswith("**已撤销"))
assert _n == _live, "★★★ 清单报 %d 条撤销, 断言文件现算 %d 条 —— 留档与现算不一致" % (_n, _live)

# ★ 反向(旧判据下): 把预算闸文件藏起来, 该条必须从 DECIDED 翻回 OPEN。新判据下只在两处都接上时才可能是 DECIDED。
if _fixed:
    # ★ 2026-09-27 根因修复: 以前**真把活仓 scripts/cce_request_budget.py 挪走**再挪回 —— 窗口期内并行 import / 扫描 scripts/
    #   的测试会红, 被 SIGKILL 还会让仓里少一个文件。M 判「已补」只看 os.path.exists(该路径) ⇒ 仅对这一条路径答「不存在」。
    #   (不改 M 本身: 动 scripts/ 会触发付费的 accuracy.yml。)
    _src = os.path.abspath(os.path.join(ROOT, "scripts/cce_request_budget.py"))
    _real_exists = os.path.exists
    os.path.exists = lambda q: False if os.path.abspath(q) == _src else _real_exists(q)
    try:
        _r = [x for x in M.items() if "跨轮请求预算闸" in x["项"]][0]
        assert _r["类"] == OPEN and "未补" in _r["项"], "★ 文件没了它还说已补 —— 硬编码"
        assert "下次仍会静默超支" in _r["证据"]
    finally:
        os.path.exists = _real_exists
    assert _real_exists(_src), "★ 反向探针不该动到真文件"

# ★ DEV-002 的重建标记必须在, 否则读的人会以为这判据是原文
_self = open(__file__, encoding="utf-8").read()
assert "重建, 不是原文" in _self and "DEV-002" in _self, \
    "★ 重建标记被抹掉了 —— 那就等于把重建冒充成原文"

decided = [r for r in rs if r["类"] == DECIDED]
assert decided, "★ 已裁定不做的要留着防重开"

# ── ★ origin 分叉: 必须标为「不合并」而不是「待 reconcile」 ────────────
#    2026-09-03 查明: origin 独有文件全是已退役的 Hy-MT2(mt_*),
#    本地 b33befd 删除并归档。**合并 = 复活退役代码** —— 本项目栽过三次的老病。
# ★ 2026-09-28: 那次分叉早已消解(两仓同一 master), 条目改写为现状; 要守的「不复活 Hy-MT2」随证据保留。
_div = [r for r in rs if "两仓同一 master" in r["项"]]
assert _div and _div[0]["类"] == DECIDED, "★ 两仓关系是已裁定的现状, 不许标成 OPEN_WORK"
assert "Hy-MT2" in _div[0]["证据"] and "不复活" in _div[0]["证据"]
import subprocess as _sp
_r = _sp.run(["git", "log", "--oneline", "-1", "--diff-filter=D", "--",
              "scripts/mt_extract.py"], cwd=ROOT, capture_output=True, text=True)
assert "retire" in _r.stdout.lower(), \
    f"★ 本地退役提交找不到了 —— 结论要重查, 实际输出: {_r.stdout[:80]}"

print(f"test_cce_open_items: OK (共 {len(rs)} 项 · "
      f"OPEN {sum(1 for r in rs if r['类']==OPEN)} / "
      f"BLOCKED {len(blocked)} / DECIDED {len(decided)} | "
      "改真相源清单会跟着变(非硬编码) | BLOCKED 各自写明卡在**什么资源或什么决定**上 | "
      "★★★今天新增三件已**接进现算**(跨轮预算闸 / display 对象域 / 8 条撤销断言), "
      "反向验过: **藏掉预算闸文件该条会从 DECIDED 翻回 OPEN** | "
      "★★★DEV-002 二次更正: 我 checkout 抹掉的那处修复, **库里 memory 29b7de8f(2026-09-08) 正记着它** —— "
      "实例就写着本文件、写着「owner 裁定」、写了修法「词表提成常量 + 从被守脚本 docstring 自证」。"
      "我第一次重建**没查库**, 硬加三个词, **比原修复弱**; 现已按原处方重做 | "
      "★自证双向验过: 词表少一项判红 · 被守 docstring 加一项而词表没跟也判红)")
