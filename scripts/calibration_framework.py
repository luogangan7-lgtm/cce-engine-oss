import os
#!/usr/bin/env python3
"""
Viral Skill Suite — 校准测试框架
Calibration Test Framework

校准维度：
A. 跨视频对比（不同类型视频，测区分度）
B. 同类型对比（同类视频横向，测精度）
C. 同视频多次解析（同一视频跑N次，测稳定性）
D. 跨文案对比（不同类型文案/图文）
E. 同文案多次解析（文案稳定性）
F. 广告内容校准
G. 账号维度校准（同账号多内容对比）

每个校准的评估指标：
- 核心欲望识别一致性（同一内容多次跑，核心欲望是否一致）
- 跨内容区分度（不同内容是否能拆出不同的核心欲望）
- 人群画像区分度
- 放大方案差异化度（L4/L5生成是否真的不同还是模板化）
- 评分稳定性（同一内容多次评分是否稳定）
"""
import json, requests, time, os, hashlib, sys, re, ast

API_KEY = os.environ.get("MINIMAX_API_KEY", "")
BASE = "https://api.minimaxi.com/v1/text/chatcompletion_v2"
MODEL = "MiniMax-M3"
ROOT = os.environ.get("VSE_ROOT", "/Volumes/data/viral-skill-eval")
RESULTS_DIR = f"{ROOT}/results/calibration"
os.makedirs(RESULTS_DIR, exist_ok=True)


def call_m3(prompt, max_tokens=8000, temperature=0.7, timeout=180):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    for attempt in range(3):
        try:
            resp = requests.post(BASE, json=payload, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            return {
                "content": choice.get("message", {}).get("content", ""),
                "finish_reason": choice.get("finish_reason", ""),
                "usage": data.get("usage", {}),
            }
        except Exception as e:
            print(f"  attempt {attempt+1}: {e}")
            time.sleep(5)
    return {"content": "", "error": "all attempts failed", "finish_reason": "error"}


# ═══════════════════════════════════════════════════════════════
# ROBUST JSON EXTRACTION
# 实证根因（见 results/calibration/part6_json_fix.md）：
#   1. M3 在 JSON 字符串值内输出未转义的 ASCII 双引号（中文引用习惯）→ json.loads 失败
#   2. M3 输出被 max_tokens 截断（finish_reason=length）→ JSON 未闭合
#   3. 上游拆解内容为空时仍调提取 → M3 回复"你没给内容"的纯文本
#   4. 输出裹 ```json 代码块（单独出现时旧的 {..} 切片能救，与 1/2 叠加时救不了）
# ═══════════════════════════════════════════════════════════════

JSON_FAIL_LOG = os.path.join(RESULTS_DIR, "json_extract_failures.log")


def _strip_code_fence(text):
    """抽取 ```json ... ``` 代码块内容；允许未闭合的 fence。"""
    m = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```(?:json|JSON)?\s*(.*)$", text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return None


def _balanced_braces(text):
    """从第一个 { 开始做括号平衡扫描，抽最外层对象；不平衡则返回到文本尾（交给截断修复）。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def _fix_unescaped_inner_quotes(s):
    """修复字符串值内部未转义的 ASCII 双引号。
    启发式：处于字符串内时，一个 " 后面（跳过空白）若不是 : , } ] 或文本尾，
    则它是内容引号而非闭合引号，转义之。"""
    out = []
    in_str = False
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if in_str and ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(s[i + 1])
            i += 2
            continue
        if ch == '"':
            if not in_str:
                in_str = True
                out.append(ch)
            else:
                j = i + 1
                while j < n and s[j] in " \t\r\n":
                    j += 1
                if j >= n or s[j] in ":,}]":
                    in_str = False
                    out.append(ch)
                else:
                    out.append('\\"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_trailing_commas(s):
    return re.sub(r",\s*([}\]])", r"\1", s)


def _close_truncated(s):
    """闭合被截断的 JSON：未闭合字符串补引号，未闭合括号按栈补齐。"""
    stack = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if in_str and ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    fixed = s
    if in_str:
        fixed += '"'
    fixed = re.sub(r",\s*$", "", fixed)
    for ch in reversed(stack):
        fixed += "}" if ch == "{" else "]"
    return fixed


def _cut_to_last_complete_pair(s):
    """截断修复方案B：回退到最后一个完整键值对的结尾再闭合括号。"""
    last = None
    for m in re.finditer(r'"\s*,', s):
        last = m
    if last is None:
        return None
    return _close_truncated(s[:last.start() + 1])


def _log_extract_failure(text, note=""):
    try:
        with open(JSON_FAIL_LOG, "a") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} {note} =====\n")
            f.write((text or "<EMPTY>") + "\n")
    except Exception:
        pass


def extract_json_robust(text, log_note=""):
    """多级降级 JSON 提取：
    直接 loads → ```json 块 → 平衡括号抽最外层 {} → 畸形修复
    （未转义内部引号 / 尾逗号 / 截断闭合 / 单引号走 ast）
    全部失败 → 记录原文到 json_extract_failures.log，返回 None。"""
    if not text or not text.strip():
        _log_extract_failure(text, log_note + " [empty]")
        return None

    t = text.strip()
    candidates = [t]
    fenced = _strip_code_fence(t)
    if fenced:
        candidates.append(fenced)
    for base in list(candidates):
        b = _balanced_braces(base)
        if b:
            candidates.append(b)
        s0, e0 = base.find("{"), base.rfind("}")
        if s0 >= 0 and e0 > s0:
            candidates.append(base[s0:e0 + 1])

    tried = set()
    for cand in candidates:
        if not cand or cand in tried:
            continue
        tried.add(cand)
        q = _fix_unescaped_inner_quotes(cand)
        nc = _strip_trailing_commas(q)
        variants = [cand, q, nc, _close_truncated(nc)]
        cut = _cut_to_last_complete_pair(nc)
        if cut:
            variants.append(cut)
        for v in variants:
            try:
                obj = json.loads(v)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            try:
                obj = ast.literal_eval(v)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass

    _log_extract_failure(text, log_note)
    return None


BARE_JSON_SUFFIX = "\n\n注意：只输出裸JSON，不要markdown代码块，不要任何解释文字，字符串值内部不要使用英文双引号（需要引用时用「」）。"


def call_m3_json(prompt, max_tokens=1500, temperature=0.0, log_note=""):
    """调 M3 并健壮提取 JSON；提取失败自动带强约束 prompt 重试 1 次。
    返回 (parsed_or_None, last_result, n_calls)。"""
    result = call_m3(prompt, max_tokens=max_tokens, temperature=temperature)
    n_calls = 1
    parsed = extract_json_robust(result.get("content", ""), log_note=log_note)
    if parsed is None:
        result = call_m3(prompt + BARE_JSON_SUFFIX, max_tokens=max_tokens, temperature=temperature)
        n_calls += 1
        parsed = extract_json_robust(result.get("content", ""), log_note=log_note + " [retry]")
    return parsed, result, n_calls


def extract_core_desire(text):
    """从拆解结果中提取核心欲望（用于一致性比较）"""
    if not text or not text.strip():
        # 上游拆解内容为空，调提取必然失败（M3 会回复"你没给内容"）
        return {"raw": "", "error": "empty teardown content"}
    prompt = f"""从以下拆解报告中提取核心信息，用严格的JSON格式输出：

{text[:6000]}

请提取并输出以下JSON（不要有其他文字）：
{{
  "core_desire_1": "第一核心欲望（一个词）",
  "core_desire_2": "第二核心欲望",
  "core_desire_3": "第三核心欲望",
  "target_audience": "核心人群一句话描述",
  "engine": "发动机一句话描述",
  "key_insight": "最重要的反直觉发现一句话"
}}"""
    parsed, result, _ = call_m3_json(prompt, max_tokens=1500, temperature=0.0, log_note="extract_core_desire")
    if parsed is not None:
        return parsed
    return {"raw": result.get("content", "")[:500], "error": "parse failed"}


# ═══════════════════════════════════════════════════════════════
# TEST CASES — 校准用的内容素材
# ═══════════════════════════════════════════════════════════════

CASES = {
    # ── MC建造类（同类型对比用）──
    "mc_xiongchu": {
        "type": "mc_building",
        "platform": "抖音",
        "title": "一辈子的存档-在MC还原熊出没地图",
        "author": "creator_17",
        "stats": "180.4万赞/33.9万转发/33.8万评论",
        "duration": "34:56",
        "description": "在MC还原整个熊出没地图一口气看完版 #我的世界 #熊出没",
        "comments": ["肝：活爹", "蝗虫过境", "肝上长了个人", "光头强的一辈子", "创造都不一定做的出来呀", "流量：活爹", "李老板：效率真高", "玩mc的就是没轻没重"],
    },
    "mc_xiaozhen": {
        "type": "mc_building",
        "platform": "抖音",
        "title": "在MC还原整个小镇（虚构案例用于同类型对比）",
        "author": "creator_20",
        "stats": "45.2万赞/12.1万转发/8.3万评论",
        "duration": "28:30",
        "description": "花300小时在MC还原我的家乡小镇 每一栋房子都是回忆 #我的世界 #家乡 #建筑",
        "comments": ["这才是真正的故乡", "看哭了", "比实景还真实", "300小时太猛了", "能不能还原我的老家", "细节拉满", "肝帝", "这才是MC的意义"],
    },
    # ── 音乐类（同类型对比用）──
    "music_perfect": {
        "type": "music_mv",
        "platform": "YouTube",
        "title": "Ed Sheeran - Perfect (Official Music Video)",
        "author": "Ed Sheeran",
        "stats": "36亿播放",
        "duration": "4:42",
        "description": "Perfect official MV",
        "comments": ["singing this at our wedding", "57 years together", "single and still crying", "0% nudity 1000% talent", "July 2026 anyone?", "makes me believe in love"],
    },
    "music_wurenzhidao": {
        "type": "music_mv",
        "platform": "抖音",
        "title": "《无人之岛》8D环绕 完整版",
        "author": "creator_24",
        "stats": "15.6万赞",
        "duration": "4:37",
        "description": "回复 @冷忆冰的评论 我不会怪你的 天空一望无际 #戴上耳机 #无人之岛 #音乐分享",
        "comments": ["戴上耳机全世界都是我的", "听哭了", "8D太绝了", "单曲循环第18遍", "夜晚听太有感觉了", "这首歌救了我"],
    },
    # ── 知识/口播类（跨类型对比）──
    "knowledge_shiji": {
        "type": "knowledge",
        "platform": "抖音",
        "title": "30分钟带你听完且听懂史记",
        "author": "creator_18",
        "stats": "1.2万赞",
        "duration": "28:21",
        "description": "不要再把史记当枯燥课本了！司马迁用血泪写下的成年人生存算法 #认知觉醒 #职场智慧 #司马迁",
        "comments": ["这才是真正的知识", "听完豁然开朗", "比老师讲的好太多", "收藏了反复看", "司马迁太惨了", "职场人必看"],
    },
    "knowledge_natie": {
        "type": "knowledge",
        "platform": "抖音",
        "title": "什么是拿铁效应？",
        "author": "creator_21",
        "stats": "5.5万赞",
        "duration": "3:01",
        "description": "#经济学 #拿铁效应 #科普 #经济 #青少年创作者计划",
        "comments": ["原来我钱都花这了", "戒了咖啡能买房", "太真实了", "每天一杯奶茶的钱", "理财启蒙", "马上记账"],
    },
    # ── 广告类 ──
    "ad_volcano": {
        "type": "advertisement",
        "platform": "抖音",
        "title": "仅需9.9元就能用上国产顶流模型 Agent Plan已接入GLM-5.2",
        "author": "creator_23",
        "stats": "176赞/154转发",
        "duration": "0:53",
        "description": "火山引擎AI模型广告",
        "comments": [],
    },
    # ── 生活方式类 ──
    "lifestyle_haihai": {
        "type": "lifestyle",
        "platform": "抖音",
        "title": "在欧洲的英吉利海峡赶海 鲍鱼龙虾遍地都是",
        "author": "creator_22",
        "stats": "4.7万赞",
        "duration": "5:00",
        "description": "难道本地人不吃海鲜吗？ #赶海 #海岛小爬菜 #龙虾 #鲍鱼 #户外",
        "comments": ["欧洲的海也太富了", "满地都是鲍鱼", "本地人不懂吃", "太爽了吧", "我也想去赶海", "这比菜市场便宜"],
    },
    "lifestyle_haozhai": {
        "type": "lifestyle",
        "platform": "抖音",
        "title": "杭州800平的家 误闯天家",
        "author": "creator_19",
        "stats": "7.2万赞",
        "duration": "4:29",
        "description": "各位加油！希望也是你一年以后在杭州的家 #杭州豪宅 #顶级豪宅",
        "comments": ["这才是人生", "贫穷限制想象", "一年后我也要住这", "误入仙境", "太豪了", "打工人的梦"],
    },
}

# ── 快速拆解prompt（聚焦核心欲望+人群+发动机，用于校准）──
def quick_teardown_prompt(case_key):
    c = CASES[case_key]
    comments_str = "\n".join(f"  #{i+1}: {cm}" for i, cm in enumerate(c["comments"])) if c["comments"] else "  （无评论数据）"
    return f"""你是爆款内容心理拆解专家。请对以下内容进行核心拆解（1500字内，聚焦最核心的结论）。

平台：{c['platform']}
作者：{c['author']}
标题：{c['title']}
互动数据：{c['stats']}
时长：{c['duration']}
描述：{c['description']}

评论：
{comments_str}

请直接输出以下结构（不需要过多推理过程）：

## 核心欲望（排序前3）
列出这个内容击中的前3个核心欲望（从：归属欲/确认欲/拥有欲/成为欲/超越欲/安全感/好奇心/审美欲/怀旧欲/敬畏欲 中选），并给出一句证据。

## 人群画像
一句话描述核心人群。

## 发动机
一句话描述这个内容不可替换的命脉。

## 钩子类型
从（情感共鸣/视觉奇观/悬念/信息差/身份认同/挑战/社交货币）中选，一句话说明。

## 反直觉发现
一句话描述最重要的反直觉洞察。"""


def run_calibration(cal_name, case_keys, runs_per_case=1, label=""):
    """运行一组校准测试"""
    print(f"\n{'='*70}")
    print(f"CALIBRATION: {cal_name} {label}")
    print(f"Cases: {case_keys} | Runs per case: {runs_per_case}")
    print(f"{'='*70}")

    results = {}
    for ck in case_keys:
        results[ck] = []
        for run_idx in range(runs_per_case):
            run_label = f"{ck}_run{run_idx+1}" if runs_per_case > 1 else ck
            print(f"\n  [{run_label}] {CASES[ck]['title'][:40]}...")
            prompt = quick_teardown_prompt(ck)
            t0 = time.time()
            raw = call_m3(prompt, max_tokens=3000, temperature=0.7)
            elapsed = time.time() - t0
            content = raw.get("content", "")
            print(f"    {len(content)} chars | {elapsed:.0f}s | finish={raw.get('finish_reason')}")

            # Extract structured data
            extracted = extract_core_desire(content)
            print(f"    Desire: {extracted.get('core_desire_1','?')} > {extracted.get('core_desire_2','?')} > {extracted.get('core_desire_3','?')}")

            run_data = {
                "case": ck,
                "run": run_idx + 1,
                "raw_content": content,
                "extracted": extracted,
                "elapsed": elapsed,
                "finish_reason": raw.get("finish_reason"),
            }
            results[ck].append(run_data)

            # Save incrementally
            safe_name = cal_name.replace(" ", "_")
            outpath = os.path.join(RESULTS_DIR, f"{safe_name}_{run_label}.json")
            with open(outpath, "w") as f:
                json.dump(run_data, f, ensure_ascii=False, indent=2)

    # Save combined
    combined_path = os.path.join(RESULTS_DIR, f"{cal_name.replace(' ','_')}_combined.json")
    with open(combined_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def analyze_stability(results):
    """分析同一内容多次解析的稳定性"""
    print("\n  === STABILITY ANALYSIS ===")
    analysis = {}
    for case_key, runs in results.items():
        if len(runs) < 2:
            continue
        desires = [r["extracted"].get("core_desire_1", "") for r in runs]
        audiences = [r["extracted"].get("target_audience", "") for r in runs]
        engines = [r["extracted"].get("engine", "") for r in runs]

        # Top desire consistency
        unique_desires = set(desires)
        consistency = len(unique_desires) == 1

        analysis[case_key] = {
            "desire_runs": desires,
            "desire_consistent": consistency,
            "unique_desires": list(unique_desires),
            "audience_runs": audiences,
            "engine_runs": engines,
        }
        status = "✅ STABLE" if consistency else "⚠️ UNSTABLE"
        print(f"  {case_key}: {status}")
        print(f"    Desires: {desires}")
        print(f"    Audiences: {[a[:40] for a in audiences]}")
    return analysis


def analyze_discrimination(results):
    """分析不同内容的区分度"""
    print("\n  === DISCRIMINATION ANALYSIS ===")
    case_desires = {}
    for case_key, runs in results.items():
        if runs:
            d1 = runs[0]["extracted"].get("core_desire_1", "?")
            d2 = runs[0]["extracted"].get("core_desire_2", "?")
            case_desires[case_key] = (d1, d2)
            print(f"  {case_key}: {d1} > {d2}")

    # Check if all cases have different top desires
    all_d1 = [v[0] for v in case_desires.values()]
    unique_count = len(set(all_d1))
    print(f"\n  Unique top desires: {unique_count}/{len(all_d1)}")
    if unique_count == len(all_d1):
        print("  ✅ FULL DISCRIMINATION - all cases have distinct top desires")
    elif unique_count >= len(all_d1) * 0.7:
        print("  ✅ GOOD DISCRIMINATION - most cases distinguished")
    else:
        print("  ⚠️ POOR DISCRIMINATION - cases not well distinguished")
    return case_desires


if __name__ == "__main__":
    # Allow running specific calibrations
    run_what = sys.argv[1:] if len(sys.argv) > 1 else ["all"]

    all_results = {}

    # ═══════════════════════════════════════════════════════════
    # CALIBRATION A: 同类型视频对比（MC建造类 + 音乐类）
    # 测目标：同类视频应拆出相似但不完全相同的核心欲望
    # ═══════════════════════════════════════════════════════════
    if "A" in run_what or "all" in run_what:
        r = run_calibration("A_same_type_mc", ["mc_xiongchu", "mc_xiaozhen"], 1, "(MC建造类横向)")
        all_results["A_mc"] = r
        analyze_discrimination(r)

        r = run_calibration("A_same_type_music", ["music_perfect", "music_wurenzhidao"], 1, "(音乐类横向)")
        all_results["A_music"] = r
        analyze_discrimination(r)

    # ═══════════════════════════════════════════════════════════
    # CALIBRATION B: 跨类型对比（MC vs 音乐 vs 知识 vs 生活方式）
    # 测目标：不同类型视频应拆出明显不同的核心欲望
    # ═══════════════════════════════════════════════════════════
    if "B" in run_what or "all" in run_what:
        r = run_calibration("B_cross_type", ["mc_xiongchu", "music_perfect", "knowledge_shiji", "lifestyle_haihai"], 1, "(跨类型对比)")
        all_results["B_cross"] = r
        analyze_discrimination(r)

    # ═══════════════════════════════════════════════════════════
    # CALIBRATION C: 同视频多次解析稳定性（跑3次同一视频）
    # 测目标：核心欲望识别应高度一致
    # ═══════════════════════════════════════════════════════════
    if "C" in run_what or "all" in run_what:
        r = run_calibration("C_stability_mc", ["mc_xiongchu"], 3, "(同一MC视频跑3次)")
        all_results["C_stability"] = r
        analyze_stability(r)

        r = run_calibration("C_stability_music", ["music_wurenzhidao"], 3, "(同一音乐视频跑3次)")
        all_results["C_stability_music"] = r
        analyze_stability(r)

    # ═══════════════════════════════════════════════════════════
    # CALIBRATION D: 知识类对比 + 广告
    # ═══════════════════════════════════════════════════════════
    if "D" in run_what or "all" in run_what:
        r = run_calibration("D_knowledge_ad", ["knowledge_shiji", "knowledge_natie", "ad_volcano"], 1, "(知识类+广告)")
        all_results["D_knowledge_ad"] = r
        analyze_discrimination(r)

    # ═══════════════════════════════════════════════════════════
    # CALIBRATION E: 生活方式类对比
    # ═══════════════════════════════════════════════════════════
    if "E" in run_what or "all" in run_what:
        r = run_calibration("E_lifestyle", ["lifestyle_haihai", "lifestyle_haozhai"], 1, "(生活方式类对比)")
        all_results["E_lifestyle"] = r
        analyze_discrimination(r)

    # Save everything
    final_path = os.path.join(RESULTS_DIR, "ALL_calibration_results.json")
    with open(final_path, "w") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n\nALL CALIBRATION RESULTS SAVED: {final_path}")
    print(f"Total individual result files: {len(os.listdir(RESULTS_DIR))}")
