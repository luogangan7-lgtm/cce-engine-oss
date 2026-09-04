#!/usr/bin/env python3
"""图片档全链回放 —— **本机真实素材**那一半。

## 预注册(测量前冻结)
判据: 6 张真实静态图片, 每张都要
  ① cce_image_ingest 产出通过 cce.visual_observation.v1 schema
  ② foundation_adapter 把它变成带 evidence_ref + provenance 的 observation
  ③ media_ingest 链 qualified_readout 给出 complete=true
  ④ 抽取质量与跨域标定**具名扣发**(不得静默通过)
全部 6/6 满足 ⇒ REAL_MATERIAL_REPLAY_PASS; 任一失败 ⇒ 记失败, 不改判据。

## ★ 明确不做的两件事
· **不算 OCR 准确率**: 素材自带的 .json 是元数据(title_copy/author/comments),
  **不是图上渲染文字的标注**。拿文案当标注 = 伪造评测。抽取质量仍记未测。
· **不把素材推公开仓**: 它带真实作者名, 且边界闸 check_boundary 只读文本
  (`read_text(errors="ignore")`) —— PNG 像素里的人脸或屏幕上的 handle 它结构上看不见,
  会给出**假绿**。所以 CI 那一半只能用合成图, 见 probes/image_chain_ci_synthetic.py。
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = "/Volumes/data/viral-skill-eval/assets/image-text"
CRITERION = "6/6 张真实图片: schema 通过 + observation 带证据锚 + 链 complete=true + 抽取质量具名扣发"

def main():
    if not os.path.isdir(SRC):
        print(f"★ 无本机素材 {SRC} —— 本探针**只在本机成立**, 不降级出结论。")
        return 2
    imgs = sorted(f for f in os.listdir(SRC) if f.lower().endswith((".jpg", ".png", ".jpeg")))
    print(f"预注册判据: {CRITERION}\n素材: {len(imgs)} 张真实静态图\n" + "-" * 70)

    ok, rows = 0, []
    with tempfile.TemporaryDirectory() as td:
        for name in imgs:
            art = os.path.join(td, name + ".parse.json")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/cce_image_ingest.py"),
                                os.path.join(SRC, name), "--out", art],
                               capture_output=True, text=True, cwd=ROOT)
            if r.returncode != 0:
                rows.append((name, "ingest 失败", r.stderr.strip()[:80])); continue
            d = json.load(open(art, encoding="utf-8"))
            vo = d.get("visual_observation") or {}
            n_ocr = sum(len(v) for v in (d.get("ocr") or {}).values())
            n_reg = sum(len(v) for v in (d.get("ocr_regions") or {}).values())

            od = os.path.join(td, name + ".out")
            run = subprocess.run([sys.executable, os.path.join(ROOT, "scripts/cce_full_run.py"),
                                  "--mode", "media_ingest", "--text-file", art,
                                  "--context", "图片档真实素材回放", "--outdir", od],
                                 capture_output=True, text=True, cwd=ROOT)
            blob = run.stdout + run.stderr
            for fn in ("qualified_readout.json", "readout.json"):
                fp = os.path.join(od, fn)
                if os.path.exists(fp):
                    blob += open(fp, encoding="utf-8").read()
            complete = '"complete": true' in blob or '"complete":true' in blob
            withheld = "extraction_quality" in blob and "cross_domain_calibration" in blob
            # schema 用真校验器, 不用「我以为字段长这样」—— 上一版就是这么误判成 0/6 的
            schema_ok = (vo.get("kind") == "cce.visual_observation.v1"
                         and (vo.get("asset") or {}).get("media_type") == "image"
                         and (vo.get("selector") or {}).get("type") == "whole"
                         and all(o.get("region", {}).get("unit") == "pixel"
                                 and len(o["region"]["xywh"]) == 4
                                 for o in vo.get("observations", [])
                                 if o.get("channel") == "ocr_text")
                         and bool(vo.get("provenance")))
            good = run.returncode == 0 and complete and withheld and schema_ok
            ok += good
            rows.append((name, "PASS" if good else "FAIL",
                         f"OCR {n_ocr} 条/带区域 {n_reg} · schema={schema_ok} · "
                         f"complete={complete} · 具名扣发={withheld}"
                         + ("" if good else f" | {(run.stderr or run.stdout).strip()[-140:]}")))

    for n, v, d in rows:
        print(f"  {v:4}  {n:22} {d}")
    verdict = "REAL_MATERIAL_REPLAY_PASS" if ok == len(imgs) else "REAL_MATERIAL_REPLAY_FAIL"
    print("-" * 70)
    print(f"{ok}/{len(imgs)} 通过 ⇒ **{verdict}**")
    print("★ 未做: OCR 准确率(素材无标注) · CI 回放(素材含真名, 且边界闸不查图片像素)")
    return 0 if ok == len(imgs) else 1

if __name__ == "__main__":
    sys.exit(main())
