#!/usr/bin/env python3
"""把多份译文的翻译器指纹排成一张表, 供与 DeepL 同源对照。

单份译文说明不了翻译器的行为 —— em dash 转换率取决于源文的逗号停顿密度,
n=1 只是那一份源文的性质。所以基线必须多样本, 且与对照组同源。
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mt_fingerprint import measure, degeneracy

rows = []
for p in sys.argv[1:]:
    t = pathlib.Path(p).read_text(encoding="utf-8").strip()
    bad, why = degeneracy(t)
    m = measure(t)
    rows.append((pathlib.Path(p).name.replace(".en.txt", ""), m, bad, why))

print(f"{'样本':<6}{'词数':>6}{'em':>5}{'em/千词':>9}{'缩写':>8}  状态")
for name, m, bad, why in rows:
    cr = f"{m['contraction_rate']:.0%}" if m["contraction_rate"] is not None else "n/a"
    print(f"{name:<6}{m['words']:>6}{m['em_dashes']:>5}{m['em_per_kw']:>9.2f}{cr:>8}  {'❌退化' if bad else 'ok'}")

ok = [m for _, m, bad, _ in rows if not bad]
if ok:
    tw = sum(m["words"] for m in ok)
    te = sum(m["em_dashes"] for m in ok)
    print(f"\n合计 {len(ok)} 份 · {tw} 词 · em dash {te} 处 = {te/tw*1000:.2f}/千词")
    print("（与 DeepL 对照需跑同一批源文，单跑一侧不构成结论）")
