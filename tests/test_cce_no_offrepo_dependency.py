#!/usr/bin/env python3
"""元测试: 测试不许依赖仓外的本机素材/路径。

## ★ 第六次: 「有降级分支」不等于「降级分支是对的」
test_cce_visual_prose_gap 我加了 `if r is not None:`, 本机绿, CI 照样红 ——
因为无素材时 run() 返回的是**结构完整但 prose/constrained 为 None 的 dict**, 不是 None。
我**读代码推断**了它的缺席形态, 没去跑。
⇒ 习惯改为: 降级路径要**实际强制触发一次**(把 SRC 指到空目录跑一遍), 不许靠读代码断言。

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

# ── ★ 2026-09-04 扩一条: **间接**依赖也要管 ───────────────────────────
# 第五次同类错的形状变了: 测试文件里一个仓外路径都没有, 但它 import 了 probes/ 里的探针,
# 而探针要本机素材 ⇒ CI 上探针返回 None, 测试拿 None 下标直接 TypeError。
# 上面的正则只扫测试文件自己的字面量, 结构上看不见这条路。
# 规则: **凡从 probes/ 导入的测试, 必须自己声明缺席时跑到了哪** —— 探针按其性质就是吃素材的。
# 判据不是「提到 probes」, 而是「把 probes 加进 sys.path **并且**真的 import 了它的模块」——
# 只读探针源码做静态检查(如 module_boundary)不吃素材, 不该被判。
PROBE_MODULES = {f[:-3] for f in os.listdir(os.path.join(ROOT, "probes")) if f.endswith(".py")}
indirect = []
for fn in sorted(os.listdir(TESTS)):
    if not fn.endswith(".py") or fn == SELF:
        continue
    src = open(os.path.join(TESTS, fn), encoding="utf-8").read()
    if "probes" not in src:
        continue
    imported = set(re.findall(r"^\s*from\s+(\w+)\s+import", src, re.M))
    imported |= set(re.findall(r"^\s*import\s+(\w+)", src, re.M))
    used = imported & PROBE_MODULES
    if not used:
        continue
    # ★ 只有**被导入的探针自己引用仓外路径**才算间接依赖 ——
    #   导入一个纯函数(分词、排序判据)不吃素材, 判它就是误报, 而误报会训练人忽略这条闸。
    hungry = sorted(m for m in used if OFFREPO.search(
        open(os.path.join(ROOT, "probes", m + ".py"), encoding="utf-8").read()))
    if not hungry:
        continue
    if not any(w in src for w in ("CI(", "无本机素材", "不可验证", "未比对", "只跑", "未重测")):
        indirect.append((fn, hungry))

assert not indirect, ("★ 这些测试**通过 probes/ 间接**依赖仓外素材, 却没写缺席时跑到了哪:\n  "
                     + "\n  ".join(f"{f} → import {m}" for f, m in indirect)
                     + "\n  (探针按其性质就吃本机素材; 缺席时返回 None, 测试拿 None 下标就崩,"
                       " 或者更糟 —— 静默跳过而恒绿)")

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

# ── ★ 反向: 这条间接规则不能是空规则 ─────────────────────────────────
#   拿真实的 test_cce_visual_prose_gap 做样例: 抽掉它的缺席声明, 必须被判出。
_vp = os.path.join(TESTS, "test_cce_visual_prose_gap.py")
if os.path.exists(_vp):
    _src = open(_vp, encoding="utf-8").read()
    _stripped = _src
    for _w in ("CI(", "无本机素材", "不可验证", "未比对", "只跑", "未重测"):
        _stripped = _stripped.replace(_w, "×")
    _imp = set(re.findall(r"^\s*from\s+(\w+)\s+import", _stripped, re.M))
    _used = _imp & PROBE_MODULES
    _hungry = [m for m in _used if OFFREPO.search(
        open(os.path.join(ROOT, "probes", m + ".py"), encoding="utf-8").read())]
    assert _hungry, "★ 反向样例的探针不吃仓外素材 —— 换一个样例, 否则这条规则没被验到"
    assert not any(w in _stripped for w in ("CI(", "无本机素材", "未重测")), "★ 抽取失败"
    # 抽掉声明后, 判定三要素齐备 ⇒ 规则会判它
    _INDIRECT_REVERSE_OK = True
else:
    _INDIRECT_REVERSE_OK = False

n_off = sum(1 for fn in os.listdir(TESTS)
            if fn.endswith(".py") and fn != SELF
            and OFFREPO.search(open(os.path.join(TESTS, fn), encoding="utf-8").read()))
print(f"test_cce_no_offrepo_dependency: OK (扫 {len(os.listdir(TESTS))} 个测试文件 · "
      f"{n_off} 个引用仓外路径且**各自带存在性判断与缺席声明** | "
      "反向: 无守卫的仓外路径会被判出 | "
      f"★ 间接依赖(import 吃素材的探针)也已纳入, 反向验过={_INDIRECT_REVERSE_OK} | "
      "同类错今天犯过**五**次, 第五次就是从这条间接路进来的)")
