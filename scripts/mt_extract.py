#!/usr/bin/env python3
"""从 llama-completion 的 stdout 里剥出译文。

llama-completion 会把提示词原样回显在输出开头(-no-cnv 下尤其如此), 直接拿 stdout
当译文会把整段英文指令也算进指纹, 把 em dash 和缩写统计全带偏。
"""
import sys, pathlib

raw = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
prompt = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace").strip()

# 提示词若被回显, 从它之后切
i = raw.find(prompt)
out = raw[i + len(prompt):] if i >= 0 else raw
# 末尾的 [end of text] / EOS 标记
for marker in ("[end of text]", "<|endoftext|>", "<|eot_id|>"):
    j = out.find(marker)
    if j >= 0:
        out = out[:j]
print(out.strip())
