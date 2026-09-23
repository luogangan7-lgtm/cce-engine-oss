# -*- coding: utf-8 -*-
"""s0_context 的 Jev(TypeSafe System One) 读出后端 —— 逐面 Choice, 不生成文本。

★ owner 2026-09-23 点头接线。依据 results/s0_retest.json: 同批 42 条两轮, Jev 四面 κ=1.0/两面≈.88 vs MiniMax .38–.58;
  情绪余温冷读结构违反 MiniMax 42/42 vs Jev 12/42。**只比稳定性与纪律, 不比准确率(无真值)。**
★ 密钥只走环境变量 TYPESAFE_API_KEY, 缺就返回 err 让调用方走 MiniMax; 绝不读仓外文件、绝不打日志。
★ 题目集与 probes/s0_jev_shadow.py 逐字相同(闸核 sha), 否则重测证据不再适用于生产。
"""
import json, os, time, urllib.request, urllib.error

API = "https://api.typesafe.ai/v1/systemone"; MODEL = "jev-latest"; UNKNOWN = {"未知", "未提及", "", None}


def jev_questions(facets):
    qs = {}
    for f in facets:
        opts = {v: "%s: %s" % (f["desc"], v) for v in f["values"]}
        if not (set(f["values"]) & UNKNOWN):
            opts["未知"] = "the text does not show this facet; do not guess"
        qs[f["key"]] = {"type": "choice", "instructions": "Read this facet of the reader's situation from the text. Facet: %s (%s). If the text does not show it, choose 未知; never guess." % (f["key"], f["desc"]), "criteria": opts}
    return qs


def _post(body, key, retries=3):
    for att in range(retries):
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
