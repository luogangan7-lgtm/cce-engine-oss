# -*- coding: utf-8 -*-
"""开发工具(零 API): 按 ablation_verdicts_v3.json 的 scope_rule 现算覆盖率并回写 ★coverage 段。**每次新增/删除 scope 内文件后必须跑**, 否则 test_cce_ablation_verdicts_v3 的 scope_files/scope_lines 现算闸红。"""
import json, pathlib, os
ROOT=pathlib.Path(__file__).resolve().parents[1]; P=ROOT/"tests/data/ablation_verdicts_v3.json"
doc=json.loads(P.read_text(encoding="utf-8")); rule=doc["★coverage"]["scope_rule"]; out=[]
for d in rule["dirs_recursive_py"]:
    for r,_,fs in os.walk(ROOT/d):
        for f in fs:
            if f.endswith(".py"): out.append(str(pathlib.Path(r,f).relative_to(ROOT)))
for d in rule["dirs_flat_json"]:
    for f in sorted(os.listdir(ROOT/d)):
        if f.endswith(".json"): out.append("%s/%s"%(d,f))
scope=sorted(set(out))
def nl(rel):
    with open(ROOT/rel,"rb") as fh: return sum(1 for _ in fh)
ln={p:nl(p) for p in scope}; touched={f for r in doc["verdicts"] for f in r["ablated_files"]}
ins=[f for f in touched if f in ln]; never=[p for p in scope if p not in touched]; c=doc["★coverage"]
c.update({"scope_files":len(scope),"scope_lines":sum(ln.values()),"n_touched_files":len(ins),"touched_files_union":sorted(ins),
 "lines_in_touched_files":sum(ln[f] for f in ins),"file_level_pct":round(100.0*len(ins)/len(scope),2),
 "line_level_pct_GENEROUS_UPPER_BOUND":round(100.0*sum(ln[f] for f in ins)/sum(ln.values()),2),"per_file_lines":ln})
w=doc["★what_is_still_unablated"]["③_合计"]; w["n_files_never_touched"]=len(never); w["lines_never_touched"]=sum(ln[p] for p in never)
P.write_text(json.dumps(doc,ensure_ascii=False,indent=1),encoding="utf-8")
print("覆盖率刷新: 文件级 %s%% (%d/%d) · 行级 %s%%"%(c["file_level_pct"],len(ins),len(scope),c["line_level_pct_GENEROUS_UPPER_BOUND"]))
