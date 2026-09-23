#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""闸: 被改判的行里, **旧结论不许以现行主张的形式出现**在 evidence 类字段里。

★★★ 为什么要这条(2026-09-13 实际发生):
判决表里被改判的行, 判决词 / status / 复核块都按复核改写了, 但 `evidence` 之类的
**被核产物字段被逐字保留** —— 于是同一行里:
  · `verdict` 写 LOAD_BEARING_L2, `evidence` 写「L2判决翻 0/21」(v3-225)
  · `verdict` 由 NO_CONSUMER 改判为 LOAD_BEARING_L2, `evidence` 仍写「**确实零消费者**」(v3-022)
  · `L4_net_new_reds` 写「被核产物记的 0 是错的」, `evidence` 仍写净新增 0(v3-262)
留原文供追溯是对的; **但只读 evidence 的人会读到旧结论**。
「过期判决表继续被引用」是本仓登记过的错误族(open_items 硬编 17.3% · v3-093「零测试覆盖」·
v3-062/071「零测试守护」), 这次它出现在**判决表自己的举证字段**上。

★ 本仓已有的处置形状(照它做, 不发明新的), 见 tests/test_cce_open_items_no_hardcoded_coverage.py:
  旧说法只能以「**被撤回的引文**」形式出现 —— 必须同时
    ① 被「」括住 / 明确标注为原文   ② 紧邻有撤回标记
  ⇒ 本闸只查这个**形状**, 不去猜哪个数字是错的。

★★★ 判据为什么零误报(两条都是**结构判据**, 不是措辞猜测):
  A. **逐字同一**: 改判块自带 `original_row_preserved_verbatim`(原行快照)。
     一个 evidence 类字段若与快照**逐字相等**, 而这一行的判决 was != now,
     那它就是「被改判前那一行的原话, 一个字都没人动过」—— 这是比对出来的, 不是猜出来的。
  B. **同行传染**: 若本行自己已经在 L1/L2/L4 字段上写了撤回标记(= 本行承认那一面被改写过),
     那么同一面的 evidence 类兄弟字段**不许还是白板**。触发条件是「本行自己的标记」, 同样不猜措辞。
  ★ 试过而**否决**的判据(会误报, 不上):
    · 「按 status ∈ {OVERTURNED_AND_REPLACED, …} 取行」—— 真正出问题的 v3-225/231/262
      status 全是 active(改判记在 ★独立复核_parser_plane 块里), 按 status 取会**整族漏掉**。
    · 「凡带 `被核产物原判` 块且与本行判决不同就要求撤回标记」—— 实测**误伤 4 行**
      (v3-283/285/287/288: 复核块自己写明「这是**措辞降级不是结论推翻**, 注入臂全部为真」,
      它们的 0/16 正是复核所依据的读数, 不是旧结论)。
    · A 判据用「快照原文是现行字段的**子串**」—— 实测**误伤 2 行**(v3-103/106 的 L2_changed
      把原话留在前面、后面补了一句「★ 但 verdict 词改判的理由不在这里, 在 M8」, 而那句 false
      根本没被撤回)。⇒ 收窄成**逐字相等**: 只有「一个字都没人动过」才算旧话占着现行位置。
    ★ 会误报的闸不上 —— 它会训练读者忽略它。
"""
import copy, json, pathlib, socket, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC_PATH = ROOT / "tests/data/ablation_verdicts_v3.json"

# ── R1 绊线 ────────────────────────────────────────────────────────────────
_TRIPPED = []
socket.socket.connect = lambda s, a, *x, **k: (_TRIPPED.append(a),
                                               (_ for _ in ()).throw(AssertionError("★★★ 离线隔离被突破: %r" % (a,))))[1]

DOC = json.loads(DOC_PATH.read_text(encoding="utf-8"))

# 举证类字段 = 「只读它就会当成现行读数」的那些。deletable_reason 不在这里:
# 它由 ★deletable_ledger 的逐字 sha8 台账闸独立看守(见 test_cce_ablation_verdicts_v3.py)。
EVIDENCE_FIELDS = ("evidence", "L1_changed", "L2_changed", "L4_net_new_reds",
                   "L4_source_text_gates_invisible_to_memory_ablation", "injection_test")

RECHECK_BLOCKS = ("★overturned_by_recheck", "★downgraded_by_v3_completeness_audit",
                  "★retested_by_ce3_closure", "★replaced_by_v3_rerun",
                  # ★★★ 2026-09-13 补: 独立复核点出这三个块**原本不在名单里** ——
                  #   41 行带着它们, 而 A/B/C 三条判据结构上都看不见那 41 行。
                  #   复核找到的漏行**全部**落在这个缺口里; 缺口不是判据不够严, 是**名单漏了**。
                  "★独立复核_r2", "★独立复核_r6", "★独立复核_parser_plane")

# 撤回标记词表: 每一个都**把那段话归给别人**(被核产物 / 被改判前的原行), 不是泛泛的形容词。
# ★ "独立复核" 曾在表里, 实测**误伤 2 行**(v3-214 的 L2「gate_protocol_hash …(CE-3 闭合轮独立复核实测)」
#   与 v3-305 的 L4「未跑全量套件(独立复核只报了 L1/L2 两面)」—— 那是**测量方署名**, 不是撤回)。
#   ⇒ 收窄: 只认把话归给「被核产物 / 原判」的那些词。会误报的闸不上。
RETRACTION_MARKS = ("原判原文", "被核产物", "已撤回", "已被推翻",
                    "按本工况重判", "原写死", "先前写的", "旧判原文")
# 引文形状: 旧话必须被「」括住, 或被明确标注为「原文」。
QUOTE_SHAPE = ("「", "原文")

HEAD = 90          # 撤回标记必须在**字段开头**, 不许埋在末尾当脚注
MIN_SNAPSHOT = 12  # 太短的快照值(如 "0/22")不做包含判定, 避免偶然子串


def _txt(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _norm(v):
    """折叠全部空白 —— 让「加一个空格/换行」这种伪修复失效。"""
    return " ".join(_txt(v).split())


def is_retracted(val):
    """字段是否带**前置**撤回标记。"""
    return any(m in _txt(val)[:HEAD] for m in RETRACTION_MARKS)


def has_quote_shape(val):
    return any(q in _txt(val) for q in QUOTE_SHAPE)


def _present(row, k):
    return k in row and len(_txt(row[k]).strip()) >= MIN_SNAPSHOT


# ── 判据 A: 原行快照被原样搬进了现行举证字段 ────────────────────────────────
def check_A_verbatim_original_must_be_quoted_as_retracted(doc):
    """★★★ 改判行里, 凡**原样包含原行快照**的举证字段必须是被撤回的引文。

    为什么这不会误报: `original_row_preserved_verbatim` 是改判块自己存的原行,
    `was != now` 是改判块自己写的。两者都来自本行自述, 判定是**逐字比对**。
    判决没改(was == now)的重测行**不在范围内** —— 加宽观测面后结论不变, 原文照样是现行主张。
    """
    bad, guarded, rows_in_scope = [], 0, set()
    for r in doc["verdicts"]:
        for bk in RECHECK_BLOCKS:
            b = r.get(bk)
            if not isinstance(b, dict):
                continue
            was = b.get("was") or b.get("verdict_before") or b.get("v2_verdict")
            now = b.get("now") or b.get("verdict_now") or b.get("v3_verdict")
            snap = b.get("original_row_preserved_verbatim")
            if not isinstance(snap, dict) or was == now:
                continue
            for k in EVIDENCE_FIELDS:
                if k not in r or k not in snap:
                    continue
                rows_in_scope.add(r["id"])
                guarded += 1
                old = _txt(snap[k])
                if len(old.strip()) < MIN_SNAPSHOT:
                    continue
                # ★★★ 2026-09-13 修**伪修复通道**: 原来这里是 `old != _txt(r[k]): continue`
                #   —— 只认**逐字相同**, 于是**加一个空格就转绿**; 而且它**从头到尾没调用
                #   is_retracted()**, 失败文案却写着「却没有撤回标记」。**文案在说一件它没查的事。**
                #   (独立复核实测指出, 已复现。)
                # ⇒ 两处收紧: (a) 比对前**折叠全部空白**, 空格/换行把戏失效;
                #              (b) **真的查**撤回标记 —— 规范化后仍是原话且没标记, 才判红。
                if _norm(old) != _norm(r[k]):
                    continue
                if is_retracted(r[k]):
                    continue
                bad.append("%s.%s 与 %s 里的原判原文**(折叠空白后)相同**(改判 %s → %s), 且**无前置撤回标记**: %s…"
                           % (r["id"], k, bk, was, now, " ".join(_txt(r[k]).split())[:70]))
    assert not bad, ("★★★ 被改判行的旧举证以**现行主张**的形式留在表里(%d 条):\n  " % len(bad)
                     + "\n  ".join(bad[:10]))
    return len(rows_in_scope), guarded


# ── 判据 B: 本行自己承认某一面被改写了, 同面的兄弟字段不许还是白板 ──────────
# 触发字段 → 必须跟着带标记的字段
FACE_SIBLINGS = {
    "L1_changed": ("evidence",),
    "L2_changed": ("evidence",),
    "L4_net_new_reds": ("evidence", "L4_source_text_gates_invisible_to_memory_ablation"),
}


def check_B_retraction_must_reach_the_siblings_on_the_same_face(doc):
    """★★★ 撤回不许只改一半。

    v3-225/231/242-245/262 全是这个形状: L2_changed / L4_net_new_reds 已经按复核改写并写明
    「被核产物记的是 0/21」, 而同一行的 `evidence` 一个字没动, 仍写着 0/21。
    触发条件是**本行自己写下的撤回标记**, 所以不存在「猜哪句是旧话」这一步。
    """
    bad, guarded, rows_in_scope = [], 0, set()
    for r in doc["verdicts"]:
        for trigger, sibs in FACE_SIBLINGS.items():
            if not (_present(r, trigger) and is_retracted(r[trigger])):
                continue
            for s in sibs:
                if not _present(r, s):
                    continue
                rows_in_scope.add(r["id"])
                guarded += 1
                if not is_retracted(r[s]):
                    bad.append("%s: %s 已按复核撤回改写, 同面的 %s 却还是被核产物原文(无标记): %s…"
                               % (r["id"], trigger, s, " ".join(_txt(r[s]).split())[:70]))
                elif not has_quote_shape(r[s]):
                    bad.append("%s.%s 有撤回标记但旧话没被「」括住 / 没标为原文: %s…"
                               % (r["id"], s, " ".join(_txt(r[s]).split())[:70]))
    assert not bad, ("★★★ 撤回只改了一半, 旧读数仍以现行主张留在 evidence 里(%d 条):\n  " % len(bad)
                     + "\n  ".join(bad[:10]))
    return len(rows_in_scope), guarded


def check_the_original_text_was_not_deleted(doc):
    """★ 加标记不许顺手改原话: 被标记的字段必须仍然**逐字包含**原行快照。

    (与 A 互补: A 查「有原文却没标记」, 这条查「标了记却把原文删/改了」。)
    """
    kept = 0
    for r in doc["verdicts"]:
        for bk in RECHECK_BLOCKS:
            b = r.get(bk)
            if not isinstance(b, dict):
                continue
            snap = b.get("original_row_preserved_verbatim")
            was = b.get("was") or b.get("verdict_before") or b.get("v2_verdict")
            now = b.get("now") or b.get("verdict_now") or b.get("v3_verdict")
            if not isinstance(snap, dict) or was == now:
                continue
            for k in EVIDENCE_FIELDS:
                if k not in r or k not in snap:
                    continue
                old = _txt(snap[k]).strip()
                if len(old) < MIN_SNAPSHOT:
                    continue
                if not is_retracted(r[k]):
                    continue          # 交给判据 A 去红
                assert old in _txt(r[k]), (
                    "★★★ %s.%s 标了撤回, 但原判原文被改动/删节了 —— 撤回的代价不能是丢证据" % (r["id"], k))
                kept += 1
    return kept


# ── 反向测试 ───────────────────────────────────────────────────────────────
def _reverse():
    """每条断言都在一份**被做坏的**数据上验过会红; 另有空操作对照验不会假红。"""
    import random
    out = []

    def run(name, mutate, checker):
        d = copy.deepcopy(DOC)
        mutate(d)
        try:
            checker(d)
        except AssertionError as e:
            out.append((True, name, " ".join(str(e).split())[:95]))
            return
        out.append((False, name, "★ 没红"))

    def by_id(d, rid):
        return next(r for r in d["verdicts"] if r["id"] == rid)

    def strip_prefix(d, rid, field):
        """把撤回前缀撕掉, 只留原话 —— 这正是本轮修掉的那个形状。"""
        r = by_id(d, rid)
        t = r[field]
        r[field] = t[t.index("：「") + 2:-1] if "：「" in t else t

    run("① 改判行的 evidence 被还原成裸原判原文(v3-022)",
        lambda d: strip_prefix(d, "v3-022", "evidence"),
        check_A_verbatim_original_must_be_quoted_as_retracted)

    run("② 撤回只改了一半: L2 改了 evidence 没改(v3-225)",
        lambda d: strip_prefix(d, "v3-225", "evidence"),
        check_B_retraction_must_reach_the_siblings_on_the_same_face)

    run("③ L4 那一面只撤回一半(v3-262 的源码文本闸行)",
        lambda d: strip_prefix(d, "v3-262", "L4_source_text_gates_invisible_to_memory_ablation"),
        check_B_retraction_must_reach_the_siblings_on_the_same_face)

    def bury(d, rid, field):
        """标记被挪到末尾当脚注 —— 读者从头读仍会先读到旧结论。"""
        r = by_id(d, rid)
        t = r[field]
        body = t[t.index("：「") + 2:-1] if "：「" in t else t
        r[field] = body + "  (★被核产物原文·已撤回)"

    run("④ 撤回标记被埋到末尾当脚注(v3-231)",
        lambda d: bury(d, "v3-231", "evidence"),
        check_B_retraction_must_reach_the_siblings_on_the_same_face)

    def unquote(d, rid, field):
        """留着标记词, 但把引号与「原文」二字去掉 ⇒ 旧话又变成了本行自己的叙述。"""
        r = by_id(d, rid)
        t = r[field]
        body = t[t.index("：「") + 2:-1] if "：「" in t else t
        r[field] = ("★已撤回 —— " + body).replace("「", "").replace("」", "").replace("原文", "")

    run("⑤ 有撤回标记但旧话没被引起来(v3-262)",
        lambda d: unquote(d, "v3-262", "evidence"),
        check_B_retraction_must_reach_the_siblings_on_the_same_face)

    run("⑥ 标了撤回却把原判原文删节了(v3-093)",
        lambda d: by_id(d, "v3-093").__setitem__(
            "evidence", "★原判原文·已撤回(非现行主张)：「Poison 臂最强, 生产侧一次都没被访问」"),
        check_the_original_text_was_not_deleted)

    # ★ 空操作对照: 两条都不许假红
    for name, noop in (
        ("空操作①: 原样深拷贝", lambda d: None),
        ("空操作②: 改一个与举证无关的字段(component 后缀)",
         lambda d: by_id(d, "v3-225").__setitem__("component", by_id(d, "v3-225")["component"] + " ")),
    ):
        d = copy.deepcopy(DOC)
        noop(d)
        try:
            check_A_verbatim_original_must_be_quoted_as_retracted(d)
            check_B_retraction_must_reach_the_siblings_on_the_same_face(d)
            check_the_original_text_was_not_deleted(d)
            out.append((True, name, "未假红 ✓"))
        except AssertionError as e:
            out.append((False, name, "★★★ 空操作竟然红了: %s" % " ".join(str(e).split())[:80]))
    return out


def test_A():
    check_A_verbatim_original_must_be_quoted_as_retracted(DOC)


def test_B():
    check_B_retraction_must_reach_the_siblings_on_the_same_face(DOC)


def test_original_kept():
    check_the_original_text_was_not_deleted(DOC)


def test_reverse_all_go_red():
    res = _reverse()
    assert all(ok for ok, _, _ in res), "\n".join("%s %s: %s" % ("✓" if o else "✗", n, m) for o, n, m in res)


def test_no_network():
    assert _TRIPPED == [], "★★★ 绊线触发: %r" % _TRIPPED


# ── 判据 C: 行**自述有更正**, 举证里却看不见 ────────────────────────────────
# ★★★ 2026-09-13 补。独立复核点出 A/B 有一个**结构性盲区**:
#   B 的触发条件是「**已经有人**在兄弟字段上写了撤回标记」⇒ 一条**从没被人标过**的陈旧行,
#   A 与 B **都结构上看不见**。复核找到的漏行**全部**落在这个盲区里 —— 那不是巧合, 是设计后果。
#   而原交付把这个盲区写成了「0 误报」。
#
# ⇒ C 换一个锚: **块自己写了 was/理由须换/一句事实更正 ⇒ 这一行自述「我被更正过」**。
#   那么它的举证字段里**至少要有一处**看得见这次更正。这是**结构判据**(锚在块自带的键上),
#   不猜措辞, 因此不会误伤那些没被更正过的行。
#   ★ 它**不**定位是哪个字段错了 —— 那需要逐句读, 不是闸能做的。它只保证**更正不会在举证面上消失**。
CORRECTION_KEYS = ("理由须换", "一句事实更正")


def _row_declares_a_correction(b):
    if not isinstance(b, dict):
        return None
    for k in CORRECTION_KEYS:
        if k in b:
            return k
    w = b.get("was") or b.get("verdict_before") or b.get("v2_verdict")
    n = b.get("now") or b.get("verdict_now") or b.get("v3_verdict")
    if w is not None and n is not None and _norm(w) != _norm(n):
        return "was≠now"
    return None


def check_C_a_declared_correction_must_be_visible_in_the_evidence(doc):
    bad, scope = [], 0
    for r in doc["verdicts"]:
        for bk in RECHECK_BLOCKS:
            why = _row_declares_a_correction(r.get(bk))
            if not why:
                continue
            scope += 1
            if any(is_retracted(r[f]) for f in EVIDENCE_FIELDS if f in r):
                break
            bad.append("%s 的 %s 自述被更正(%s), 但**全部举证字段里一处撤回标记都没有** —— "
                       "只读举证的人会读到已作废的结论" % (r["id"], bk, why))
            break
    assert not bad, ("★★★ 自述有更正、举证面上却看不见(%d 条):\n  " % len(bad) + "\n  ".join(bad[:10]))
    return scope



# ── 判据 D: 名单本身必须覆盖数据里实际存在的复核块 ──────────────────────────
def check_D_the_block_list_covers_every_recheck_shaped_block(doc):
    """★★★ 2026-09-13 补。A/B/C 三条都以 RECHECK_BLOCKS 为入口 ——
    **名单漏一个块, 那一族行就集体隐身**, 而且三条判据全都不会报。

    这不是假设: ★独立复核_r2 / _r6 / _parser_plane 三个块**本来就不在名单里**,
    41 行带着它们, 独立复核找到的漏行**全部**落在这个缺口里。
    我今天把它们补进名单 —— 但**补一次不解决问题**: 下一轮又会有新块名。
    ⇒ 改成**现算**: 数据里凡长得像复核块的键(带 was/now 或明示更正键), 都必须在名单里。
      新块名出现 ⇒ 本条判红, 逼人去分类, 而不是默默少覆盖。
    """
    SHAPE = ("was", "verdict_before", "v2_verdict", "now", "verdict_now", "v3_verdict") + CORRECTION_KEYS
    seen = {}
    for r in doc["verdicts"]:
        for k, v in r.items():
            if not (isinstance(k, str) and k.startswith("★") and isinstance(v, dict)):
                continue
            if not any(x in v for x in SHAPE):
                continue
            seen.setdefault(k, 0)
            seen[k] += 1
    missing = {k: n for k, n in seen.items() if k not in RECHECK_BLOCKS}
    assert not missing, (
        "★★★ 这些块长得像复核块(自带 was/now 或明示更正键)却**不在 RECHECK_BLOCKS 名单里** —— "
        "带它们的行会对 A/B/C 三条判据**集体隐身**:\n  "
        + "\n  ".join("%s (%d 行)" % (k, n) for k, n in sorted(missing.items()))
        + "\n  ⇒ 要么补进名单, 要么在这里显式说明它为什么不算复核块。**不许默默少覆盖。**")
    return sorted(seen), sum(seen.values())

if __name__ == "__main__":
    nA, gA = check_A_verbatim_original_must_be_quoted_as_retracted(DOC)
    nB, gB = check_B_retraction_must_reach_the_siblings_on_the_same_face(DOC)
    nC = check_C_a_declared_correction_must_be_visible_in_the_evidence(DOC)
    blocks, nD = check_D_the_block_list_covers_every_recheck_shaped_block(DOC)
    kept = check_the_original_text_was_not_deleted(DOC)
    print("正向: A 守住 %d 行/%d 字段; B 守住 %d 行/%d 字段; ★C 守住 %d 行(自述有更正的全部); 原文逐字仍在 %d 处"
          % (nA, gA, nB, gB, nC, kept))
    print("★D 名单现算覆盖 %d 个复核块 / %d 行: %s" % (len(blocks), nD, blocks))
    res = _reverse()
    for ok, name, msg in res:
        print("  %s %-44s %s" % ("反向见红 ✓" if ok else "★★★ 失败", name, msg))
    bad = [n for ok, n, _ in res if not ok]
    assert not bad, "★★★ 这些反向/对照没达到预期: %r" % bad
    assert _TRIPPED == [], "★★★ 绊线触发: %r" % _TRIPPED
    print("反向: %d/%d 条按预期(含 2 条空操作对照不假红)" % (len(res), len(res)))
    print("绊线 tripped=[] (作用域: 本进程内经 socket 新建的连接; 不覆盖已建连接/子进程/C 扩展自带栈)")
    print("OK tests/test_cce_verdicts_no_stale_evidence.py")
