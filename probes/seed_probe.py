#!/usr/bin/env python3
"""P0-0 seed 探针：MiniMax 端点到底认不认 seed。

为什么在最低层打而不走 CCE 链：链上一次调用约 60-600s，且 s1/s2 混着两种噪声源。
这里只回答一个问题——**同一个 prompt，加了 seed 之后输出还变不变**。
答案决定后面三个方案还需不需要做，所以它必须先跑，而且必须便宜。

四组，每组同一 prompt：
  D  temp=0.0 无 seed   ← s2_knots 当前的调用形态。若这组已确定，则 s2 本身没问题
  A  temp=0.6 无 seed   ← s1 温度阶梯里的一档，当前形态
  B  temp=0.6 seed=42   ← 实验组
  C  temp=0.6 seed=999  ← 反向测试：必须与 B 不同，否则 seed 根本没送到
"""
import os, sys, json, re, pathlib, time, hashlib
from concurrent.futures import ThreadPoolExecutor
import requests

# 凭据只从环境变量取; 本地跑法: set -a; . <你的 .env>; set +a
KEY = os.environ.get("MINIMAX_API_KEY", "")
assert KEY, "MINIMAX_API_KEY 未设置 —— 先 set -a; . .env; set +a"
URL = "https://api.minimaxi.com/v1/text/chatcompletion_v2"

# 形状对齐真实任务：短文本 → 带权 JSON。权重是连续量，最容易看出抖动。
PROMPT = """给下面这句话按三个维度打权重，三者之和为 1，保留两位小数。

【句子】我花了两周整理这些报告，现在发现整张表可能测的根本不是我以为的东西。

只输出 JSON，不要任何解释：
{"regret":0.00,"curiosity":0.00,"resolve":0.00}"""

def call(temp, seed=None, timeout=120):
    payload = {"model": "MiniMax-M3", "messages": [{"role": "user", "content": PROMPT}],
               "max_tokens": 3000, "temperature": temp}
    if seed is not None:
        payload["seed"] = seed
    try:
        r = requests.post(URL, json=payload,
                          headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                          timeout=timeout)
        if r.status_code != 200:
            return {"err": f"HTTP {r.status_code}: {r.text[:200]}"}
        d = r.json()
        ch = (d.get("choices") or [{}])[0]
        c = (ch.get("message") or {}).get("content", "") or ""
        m = re.search(r'\{[^{}]*\}', c)
        return {"raw": c.strip()[:120], "json": json.loads(m.group()) if m else None,
                "fin": ch.get("finish_reason"),
                "base_resp": (d.get("base_resp") or {}).get("status_code")}
    except Exception as e:
        return {"err": f"{type(e).__name__}: {e}"[:200]}

GROUPS = [("D temp=0.0 无seed", 0.0, None, 6),
          ("A temp=0.6 无seed", 0.6, None, 6),
          ("B temp=0.6 seed=42", 0.6, 42, 6),
          ("C temp=0.6 seed=999", 0.6, 999, 4)]

res = {}
for name, temp, seed, n in GROUPS:
    with ThreadPoolExecutor(max_workers=3) as ex:
        outs = list(ex.map(lambda _: call(temp, seed), range(n)))
    res[name] = outs
    errs = [o for o in outs if o.get("err")]
    vals = [json.dumps(o["json"], sort_keys=True) for o in outs if o.get("json")]
    uniq = len(set(vals))
    print(f"\n═══ {name} · n={n} ═══")
    if errs:
        print(f"  ❌ {len(errs)} 次失败: {errs[0]['err']}")
    for o in outs:
        print(f"     {o.get('json') if o.get('json') else (o.get('raw') or o.get('err'))}  [fin={o.get('fin')}]")
    if vals:
        print(f"  → 不同输出 {uniq}/{len(vals)}  {'✅ 完全确定' if uniq==1 else '❌ 不确定'}")

# 反向测试：B 与 C 必须不同，否则 seed 没被端点采纳
b = {json.dumps(o["json"], sort_keys=True) for o in res["B temp=0.6 seed=42"] if o.get("json")}
c = {json.dumps(o["json"], sort_keys=True) for o in res["C temp=0.6 seed=999"] if o.get("json")}
print("\n═══ 反向测试：不同 seed 必须给出不同结果 ═══")
print(f"  B(seed=42)  取值集合 {b}")
print(f"  C(seed=999) 取值集合 {c}")
if len(b)==1 and len(c)==1:
    print(f"  → {'✅ seed 生效且可区分' if b!=c else '❌ 两个 seed 结果相同 —— seed 未被采纳，或该 prompt 本就确定'}")
else:
    print("  → ⚠️ 组内已不确定，seed 未生效，反向测试不适用")
pathlib.Path('/tmp/seed_probe.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
