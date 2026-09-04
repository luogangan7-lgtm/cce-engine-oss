#!/usr/bin/env python3
"""元测试: 测试不许依赖仓外的本机素材/路径。

## 为什么加它 —— 同一类错我今天犯了三次, 全靠 CI 实跑才发现
① tests/test_cce_strategy_gate.py 断言「可发布」, 而 check_boundary 在 /Volumes/data/cce-identified-vault
② tests/test_cce_no_real_identities.py 运行时从那个保险库读化名表
③ tests/test_cce_audio_prosody.py 无 wav 时回退 __file__, CI 上把 .py 喂给 librosa
**共同点: 我假设本机素材存在。** 前两次修完还犯第三次 ⇒ 靠记性无效, 得有闸。

## 规则
测试里出现仓外绝对路径**必须**同时满足两条, 否则红:
· 有 `os.path.exists` / `os.path.isdir` 之类的**存在性判断**(即缺席时能优雅降级)
· 且**明写**缺席时的行为(打印/断言里说清「本次没跑到哪条路」)
★ 「优雅降级」不等于「静默跳过」—— 降级路径必须自己也有断言, 否则就是恒绿。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
OFFREPO = re.compile(r"[\"'](/Volumes/[^\"']+|/Users/[^\"']+|/home/[^\"']+)[\"']")
SELF = os.path.basename(__file__)

bad = []
for fn in sorted(os.listdir(TESTS)):
    if not fn.endswith(".py") or fn == SELF:
        continue
    src = open(os.path.join(TESTS, fn), encoding="utf-8").read()
    hits = OFFREPO.findall(src)
    if not hits:
        continue
    guarded = ("os.path.exists" in src or "os.path.isdir" in src
               or "glob.glob" in src or "glob(" in src)
    declares = any(w in src for w in ("CI(", "无本机素材", "不可验证", "未比对", "只跑"))
    if not (guarded and declares):
        bad.append((fn, hits[:2], f"存在性判断={guarded} 缺席行为已明写={declares}"))

assert not bad, ("★ 这些测试依赖仓外素材却没有缺席时的降级+声明:\n" +
                 "\n".join(f"  {f}: {h} — {w}" for f, h, w in bad))

# ── ★ 反向: 造一个「用了仓外路径且无任何守卫」的样子, 规则必须能判它 ────
_probe = 'x = open("/Volumes/data/whatever/file.json").read()\n'
_hits = OFFREPO.findall(_probe)
assert _hits, "★ 正则认不出仓外绝对路径 —— 本闸失效"
assert not ("os.path.exists" in _probe or "glob.glob" in _probe), "★ 反向样例不该被判为已守卫"

# ── 已知的三个「依赖仓外但守卫齐全」的文件必须真的守卫齐全 ─────────────
for fn in ("test_cce_strategy_gate.py", "test_cce_no_real_identities.py",
           "test_cce_audio_prosody.py"):
    p = os.path.join(TESTS, fn)
    if not os.path.exists(p):
        continue
    src = open(p, encoding="utf-8").read()
    assert "os.path.exists" in src or "glob" in src, f"★ {fn} 丢了存在性判断"

n_off = sum(1 for fn in os.listdir(TESTS)
            if fn.endswith(".py") and fn != SELF
            and OFFREPO.search(open(os.path.join(TESTS, fn), encoding="utf-8").read()))
print(f"test_cce_no_offrepo_dependency: OK (扫 {len(os.listdir(TESTS))} 个测试文件 · "
      f"{n_off} 个引用仓外路径且**各自带存在性判断与缺席声明** | "
      "反向: 无守卫的仓外路径会被判出 | 同类错今天犯过三次, 这条闸就是为它设的)")
