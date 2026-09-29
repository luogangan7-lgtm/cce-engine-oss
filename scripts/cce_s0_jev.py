# -*- coding: utf-8 -*-
"""s0_context 的 Jev(TypeSafe System One) 读出后端 —— 逐面 Choice, 不生成文本。

★ owner 2026-09-23 点头接线。依据 results/s0_retest.json: 同批 42 条两轮, Jev 四面 κ=1.0/两面≈.88 vs MiniMax .38–.58;
  情绪余温冷读结构违反 MiniMax 42/42 vs Jev 12/42。**只比稳定性与纪律, 不比准确率(无真值)。**
★ 密钥只走环境变量 TYPESAFE_API_KEY, 缺就返回 err 让调用方走 MiniMax; 绝不读仓外文件、绝不打日志。
★ 每道题与 probes/s0_jev_shadow.py 逐字相同(闸核逐题 sha); 题目**集合** = 重测集合减去 STRUCTURAL(2026-09-27 起), 可比性按题不按集合。
★ 2026-09-27 owner「做吧」: 情绪余温 是闭环接口(上一轮互动留下的感觉), 冷读时不让模型读 —— 未声明 ⇒ 首轮无余温(结构冷读)。
  依据: results/s0_retest.json 冷读结构约束 MiniMax 违反 42/42、Jev 12/42; 候选合同 experiments/jev/tasks/s0_context.v2.json 同一规则(闸钉两处相等)。
  调用方义务: 有上一轮互动时必须在 context.declaration 里声明 情绪余温, 否则按首轮处理。
  只在 COLD_READ_MODES 生效: response 模式的文本本身就是读者对我方上一轮内容的反应, 不是冷读, 保持改动前行为(模型读)。
"""
import json, os, time, urllib.request, urllib.error

API = "https://api.typesafe.ai/v1/systemone"; MODEL = "jev-latest"; UNKNOWN = {"未知", "未提及", "", None}
STRUCTURAL = {"情绪余温": "首轮无余温"}   # 结构冷读: 不出模型题; 生产唯一定义(候选合同 v2 由闸钉等)
COLD_READ_MODES = {"outbound_post", "reply"}   # 只有冷读模式才有「没有上一轮」; response(对我方内容的进站回复)有上一轮, 照旧让模型读
# ★ 2026-09-29 扣发: 情绪余温 在**任何模式**都不再让模型读(未声明、非结构冷读 ⇒ 未知, 走先验)。
#   依据 results/s0_residue_referent.json(预注册 tests/data/s0_residue_referent_prereg.json, 留出段落 + 指代最小对):
#   指向我方上一条回复的情绪召回 1.0, 但指向**别人的回复/无关事件**的情绪被读成 正/负向余温 —— 现行题面 0.79、收窄题面 0.55
#   (判据 <= 0.05)。读者分不清「对我们的感觉」与「任何感觉」, 读出值与该面定义相冲突。
#   恢复条件: 新题面在**新的留出集**上过同一判据, 且另立预注册; 调用方仍可在 context.declaration 里声明。
READ_WITHHELD = {"情绪余温"}
# ★ 2026-09-29 owner「可以加合同字段」: 情绪余温 的恢复路 = **成对读**(冷读法: 我们知道自己下了什么探针, 只看对方对它的反应)。
#   依据 results/s0_residue_profile.json(预注册 5dc6031, 全占比口径): 只读回应 泄漏比 0.47/0.49 LEAKS;
#   把我方上一条消息一起给 ⇒ 泄漏比 -0.03/-0.01、位移 0.60/0.87 DISCRIMINATES。
#   只在 response 模式、且调用方给了 prior_turn(我方上一条消息正文)时走; 没给 ⇒ 仍扣发(历史缺失 ≠ 首轮)。
#   请求与实测**逐字相同**: 同一 state 版式、同一题集(六面, 只把 情绪余温 换成 PAIRED_RESIDUE_Q), 只取 情绪余温 一面; 闸钉探针与此处相等。
PAIRED_READ = {"情绪余温"}
PAIRED_RESIDUE_Q = ("Read only the writer's reaction to OUR PREVIOUS MESSAGE shown above their reply. "
                    "Feelings about anything else (other people, other replies, devices, events) do not count. "
                    "If the reply does not react to our previous message, choose 未知; never guess.")


PAIRED_MAX, REPLY_MAX = 2400, 2000


def paired_state(prior, reply):
    """★ 2026-09-29 canary 36572885138 抓到: 旧写法是先拼再整体截 [:2400] —— 我方上一条一长(post6 ≈3600 字), **对方回应被整段截掉**,
    Jev 只看到我方正文, 8 条读出几乎一样。截断只能截我方上一条, 回应必须完整(回应本身按 s0 惯例取前 2000)。
    短的上一条(实测用的就是短的)与旧写法逐字相同。"""
    head, mid = "[OUR PREVIOUS MESSAGE]\n", "\n\n[THEIR REPLY]\n"
    reply = reply[:REPLY_MAX]
    room = PAIRED_MAX - len(head) - len(mid) - len(reply)
    if len(prior) > room:
        prior = prior[:max(0, room - 2)] + " …"
    return head + prior + mid + reply


def s0_residue_paired(prior, reply, facets, post=None):
    """(我方上一条消息, 对方回应) → (选中值, {值: 概率}, err)。facets = 与实测相同的六面题集来源。"""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key: return None, None, "NO_TYPESAFE_API_KEY"
    qs = jev_questions(facets); qs["情绪余温"]["instructions"] = PAIRED_RESIDUE_Q
    resp, err = (post or _post)({"model": MODEL, "state": paired_state(prior, reply), "questions": qs}, key)
    if err or not resp: return None, None, err or "EMPTY_RESPONSE"
    try:
        a = resp["answers"]["情绪余温"]; return a["choice"], a["probabilities"], None
    except (KeyError, TypeError) as e: return None, None, "BAD_SHAPE:%s" % type(e).__name__


def jev_questions(facets):
    qs = {}
    for f in facets:
        opts = {v: "%s: %s" % (f["desc"], v) for v in f["values"]}
        if not (set(f["values"]) & UNKNOWN):
            opts["未知"] = "the text does not show this facet; do not guess"
        qs[f["key"]] = {"type": "choice", "instructions": "Read this facet of the reader's situation from the text. Facet: %s (%s). If the text does not show it, choose 未知; never guess." % (f["key"], f["desc"]), "criteria": opts}
    return qs


def _post(body, key, retries=3):
    from cce_request_budget import reserve_in_scope
    for att in range(retries):
        reserve_in_scope("jev")
        req = urllib.request.Request(API, data=json.dumps(body, ensure_ascii=False).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r: return json.load(r), None
        except urllib.error.HTTPError as e:
            if e.code in (429, 529) and att < retries - 1: time.sleep(3 * (att + 1)); continue
            return None, "HTTP %d" % e.code
        except Exception as e: return None, type(e).__name__
    return None, "RETRY_EXHAUSTED"


def s0_jev_read(body, facets, post=_post):
    """body → ({面: 选中值}, {面: 概率}, err)。无 key ⇒ err='NO_TYPESAFE_API_KEY'(调用方回退 MiniMax, 且要把回退写进产物)。"""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key: return None, None, "NO_TYPESAFE_API_KEY"
    qs = jev_questions(facets)
    resp, err = post({"model": MODEL, "state": body, "questions": qs}, key)
    if err or not resp: return None, None, err or "EMPTY_RESPONSE"
    try:
        ans = resp["answers"]
        return {k: ans[k]["choice"] for k in qs}, {k: ans[k]["probabilities"] for k in qs}, None
    except (KeyError, TypeError) as e: return None, None, "BAD_SHAPE:%s" % type(e).__name__
