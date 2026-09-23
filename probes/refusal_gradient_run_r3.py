#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ 本文件对应的设计**已被否决且从未投料** —— 理由见
  tests/data/refusal_gradient_prereg_r3.json 的 ★★★REJECTED_reason。**禁止运行, 禁止重做。**
  ★ 它还带着一个未修的 KeyError(res 字典引用了预注册里不存在的键) —— 刻意不修, 作为"跑完 16 次才崩"的留证。

抽取器**拒答难度梯度** r3 —— 判据见 tests/data/refusal_gradient_prereg_r3.json(测量前冻结)。

★★★ 换了问题: r1/r2 问「抽取器会不会交出语义错误的证书」, r2 的答案是**在干净构造阴性上 12/12 自己拒答**
  ⇒ 资格层一次都没被 exercise。而「验证器能不能拦」**已经答过了, 答案是不能**
  (2026-09-13 零调用反例, 五类语义关系验不了) ⇒ 这条管线的安全**全靠抽取器自己拒答**。
  r3 问: **那个拒答在哪一级失效?** 同一失败机制(P 支不成立), 表面增量样貌四级递增, 合同判定每级不变。

★★★ 相对 r2 的两处**协议**改动(各自对应一个 r2 实测缺陷):
  ① 每个必要条件给**一条**证据 —— r2 实测: 模型多给证据时 P2 对**全部**被采用证据求对象集合,
     ⇒ **多给反而被拦**(POS-2 额外给 TV Connector · POS-3 额外给 aids, 都是原文里真实的其他物件)。
  ② _parse **容错**: r2 有一次调用因模型在 why_not 里写了未转义双引号而整份解析失败,
     而那份答案本身是正确拒答。⇒ 改为**分字段容错抽取**, 并把「是否用了容错」记进数据。
     ★ 容错**只影响能不能读出**, 不影响任何判据。

★ r1 的 16 次已用尽, 判决 DEGENERATE_ON_CONTROLS: 5 张证书**全部**死于
  「X 的某个方面」vs「X」的粒度不一致, 阴性 0/12 毫无语义信息;
  而且阴性**只有 1/12 交卷**, 资格层在 11 条上一次都没被调用。

★★★ r2 相对 r1 的协议变更(每一条都对应一个被独立评审确认的缺陷):
  ① object 必须是**原文逐字片段**, 且问的是「这段话说的**那个东西**」的**最短**指称,
     不再问「这一段在讲哪个对象」——后者的忠实答案是**方面名词**(Battery/wax guards/the app),
     而方面名词逐字就在原文里, 逐字约束拦不住它。
  ② object 比较前走**测量前冻结的规范化**(去前导限定词/去尾部括注/去首尾标点)。
     r1 实测: 两半写了同一个名字仍因「(personally worn)」这个尾缀被拦。
     ★ 这**不是**放松 P2: 不做别名归并、不做子串包含、不做语义相似, 只消除同一名字的表面变体。
  ③ supports(这条证据支撑哪个必要条件)**由模型填**, 不再由调用方写死
     ——写死会让 qualify() 的 missing 分支**恒不可达**(与 r1 错误 A 同形)。
  ④ increment_kind **不在提示词里列成选项菜单**, 要模型自己从判别式原文里对应
     ——列菜单会让该闸期望与实际同源而恒真。
  ⑤ 记账分两层: **issuance**(模型交没交卷) 与 **Z**(交卷且过整套验证器), **逐臂**报。
     r1 的 0/12 分不清「验证器拦住了」与「抽取器根本没答」。
  ⑥ p_challenge 的分母**只算调用成功的**, 失败调用仍消耗预算但不进分母。

★ key 仅从 /Volumes/data/viral-skill-eval/.env 进程内加载, 不回显 · 不复制 · 不写仓 · 不写记忆。
★ 硬上限 16 · 零重试 · 失败也计数, 不补抽。
"""
import json, os, pathlib, random, re, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

PREREG = json.loads((ROOT / "tests/data/refusal_gradient_prereg_r3.json").read_text(encoding="utf-8"))
TPL = json.loads((ROOT / "tests/data/refusal_gradient_templates_r3.json").read_text(encoding="utf-8"))
CAP = PREREG["执行"]["★请求硬上限"]
OUT = ROOT / "results" / "refusal_gradient_r3.json"

CONJ = {"A": "输出新信息增量", "B": "谈论对象是自己已拥有或已经历的"}

# ── ② object 规范化: **测量前冻结**, 规则写死在这里 ──────────────────────
_TRAIL_PAREN = re.compile(r"\s*[（(][^）)]*[）)]\s*$")
# ★★★ 只剥**冠词**。2026-09-14 第二轮评审抓到: 原表含 my/your/his/her/their/its ⇒
#   「my Oticon」与「his Oticon」被抹成同一个对象, 而 Q 支要的正是**自己的** ——
#   那等于用规范化把被测的那一支抹掉了。
_LEAD_DET = re.compile(r"^(?:(?:the|a|an)\s+)+", re.I)
_EDGE = " \t　.,;:!?\"'`·。，、；：！？“”‘’"


def normalize_about(s):
    """★★★ 冻结的规范化规则, 只做三件事, 一件都不多:
      ① 去**尾部括注**     —— 记录 r1 的实测拦点(「the loaner ReSound Nexia (personally worn)」
                              与「the loaner ReSound Nexia」被判成两个对象)。
                              ★ 在 r2 **不可达**: object 必须逐字取自原文, 而 16 条文本零括号
                              ⇒ 带括注的 object 取不出来。保留它是为了留档, 不是为了本轮生效。
      ② 去**前导冠词**     —— the/a/an (可重复)。**刻意不含**物主/指示代词:
                              抹平 my/his/their 会把 Q 支要的「自己的」一起抹掉。
      ③ 去**首尾标点空白**
    **不做**: 别名归并 · 子串包含 · 词干还原 · 语义相似。
    ⇒ 「Phonak Audeo Sphere」与「something far simpler」规范化后仍是两个对象(对象错配臂不受影响)。
    """
    if not isinstance(s, str):
        return s
    s = s.strip()
    prev = None
    while prev != s:                      # 括注可能嵌两层
        prev = s
        s = _TRAIL_PAREN.sub("", s).strip()
    s = _LEAD_DET.sub("", s).strip()
    return s.strip(_EDGE)


DISC = TPL[[k for k in TPL if k.startswith("★合同原文")][0]]

PROMPT = """你在核验一条**已经定好的**标注。标签是 `display`。

`display` 的判别式(逐字):
%s

这个判别式要求**同时**满足两个必要条件:
  A = 输出新信息增量
  B = 谈论对象是自己已拥有或已经历的

文本:
\"\"\"%s\"\"\"

请判断:这段文本**是否真的**满足该判别式。如果满足,请给出证据 —— 每条证据是一段**逐字出现在上面文本里的**原文片段,并说明它支撑 A 还是 B。

只输出 JSON,不要别的:
{
  "supported": true 或 false,
  "evidence": [
    {
      "span": "逐字出现在上面文本里的片段",
      "supports": "A" 或 "B",
      "object": "逐字出现在上面文本里的片段:这条片段所陈述的那个**东西本身**在原文里的名称(是那个产品/设备/物件本身,**不是**它的某个部件、功能或属性;若原文多处提到同一个,取**最短**的那个完整指称,不要带所有格前缀、修饰从句或用途说明)",
      "increment_kind": "仅当 supports 为 A 时填:这段增量属于上面判别式所列的哪一种,照判别式里的措辞原样写,**只写其中一种**,不要连写多种;supports 为 B 时填 null"
    }
  ],
  "why_not": "supported 为 false 时,一句话说明差在哪;否则填 null"
}
supported 为 true 时,evidence 里**每个必要条件恰好给一条**证据(共两条:一条 supports=A,一条 supports=B),挑最有力的那一条,**不要多给**。
supported 为 false 时,evidence 填空数组 []。
所有 span 与 object 都必须**逐字**出自上面的文本。不要改写、不要合并不相邻的词。"""


def _load_key():
    p = pathlib.Path("/Volumes/data/viral-skill-eval/.env")
    if not p.exists():
        raise SystemExit("★ 找不到订阅凭据文件 —— **未发起任何调用**")
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    if not os.environ.get("MINIMAX_API_KEY"):
        raise SystemExit("★ 凭据文件里没有 MINIMAX_API_KEY —— **未发起任何调用**")


def _parse(raw):
    """抠出模型答案。返回 (obj, repaired) —— repaired 记录**是否用了容错抽取**。

    ★ 起因: r2 有一次调用因模型在 why_not 里写了未转义双引号(『虽然"I wear aids too"表明…』)
      导致整份 json.loads 失败, 而那份答案本身是**正确拒答**。
    ★★ 容错**只影响能不能读出**, 不影响任何判据 —— supported 与 evidence 仍按原样解析,
      只有 why_not 走宽松抽取。有闸反向验过: 容错**不得**改变 supported/evidence。
    """
    if not raw or not raw.strip():
        return None, False
    s0 = raw.find("{")
    if s0 < 0:
        return None, False
    depth = 0
    blob = None
    for i in range(s0, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                blob = raw[s0:i + 1]
                break
    if blob is None:
        return None, False
    try:
        return json.loads(blob), False
    except Exception:
        pass
    # ── 容错: supported / evidence 严格解析, why_not 宽松抽取 ──────────────
    m = re.search(r'"supported"\s*:\s*(true|false)', blob)
    if not m:
        return None, False
    obj = {"supported": m.group(1) == "true"}
    em = re.search(r'"evidence"\s*:\s*\[', blob)
    if em:
        j = em.end() - 1
        d2 = 0
        for i in range(j, len(blob)):
            if blob[i] == "[":
                d2 += 1
            elif blob[i] == "]":
                d2 -= 1
                if d2 == 0:
                    try:
                        obj["evidence"] = json.loads(blob[j:i + 1])
                    except Exception:
                        return None, False      # evidence 读不出就**不容错**, 老实记失败
                    break
    wm = re.search(r'"why_not"\s*:\s*"(.*?)"\s*[,}]\s*$', blob, re.S)
    obj["why_not"] = (wm.group(1) if wm else
                      (blob.split('"why_not"', 1)[1][:400] if '"why_not"' in blob else None))
    return obj, True


# ══ 结局分类法(测量前冻结) ════════════════════════════════════════════
#   ★★★ 第二轮评审抓到: 原来的 compliant 记的是「**够得着** qualify()」而不是「格式合规」。
#   qualify() 里有四条**非语义**出口(missing / anon / 无 kind / 只复述标识符)全被记成合规,
#   于是 r1 的粒度退化换成**逐字方面名词**('a charge'/'wax guards'/'its app')后整批落进
#   compliant=1 / Z=0, 两条降级一条都不响 ⇒ 旧故障被洗成「判决按字面读」。
#   ⇒ 改成按 qualify() 的**真实出口**分类。
REFUSED_RIGHT = "REFUSED_RIGHT_CONJUNCT"   # 拒答, 且 why_not 命名了构造规则声明失败的那一支
REFUSED_OTHER = "REFUSED_OTHER"            # 拒答, 但没命名对(或没给理由)
MALFORMED = "MALFORMED"                    # span/object 非逐字 · supports 无效 · kind 无效 · evidence 形状错
COVERAGE_FAIL = "COVERAGE_FAIL"            # 合取项缺支撑 · 未指名对象 · 增量支没写种类 · 只复述标识符
GRANULARITY = "OBJECT_MISMATCH_GRANULARITY"  # P2 失败, 一方规范化后是另一方**真子串** ⇒ 与 r1 同因的仪器伪影
DISTINCT = "OBJECT_MISMATCH_DISTINCT"      # P2 失败, 互不包含 ⇒ 真·不同对象(对象错配臂期望的)
UPGRADED = "UPGRADED"                      # Z=1 —— 阴性上出现即**错误升格见证**

ADJUDICATED = (COVERAGE_FAIL, GRANULARITY, DISTINCT, UPGRADED)   # 真正被资格层裁决过
ISSUED = (MALFORMED,) + ADJUDICATED                              # 交了卷

# ★ why_not 的锚词表 —— **测量前冻结**, 由构造规则确定, 不由模型输出决定。
#   ★★★ 它只验**命名了哪一支**, **不验**推理对不对 —— 与逐字引文核对是同一类局限。
ANCHORS = {
    "P": ("增量", "型号", "数据", "使用细节", "纠错", "结构化经验", "新信息",
          "increment", "model number", "specific"),
    "Q": ("拥有", "经历", "用过", "戴过", "持有", "自己的", "并非自己",
          "own", "tried", "worn", "never", "experienc"),
    "SAME_OBJECT": ("同一", "同一个", "不同对象", "不同的对象", "两个对象", "不是同一",
                    "same object", "different object"),
}


def _clean_kind(k):
    """只做**表面清洗**: 去首尾空白与中英引号。枚举成员资格的判定一个字不变。

    ★ 起因: 判别式原文里五类是**斜杠连写**的「(具体型号/数据/使用细节/纠错/结构化经验)」,
      而 r2 为了让该闸不恒真撤掉了选项菜单, 改成「照判别式里的措辞原样写」
      ⇒ 模型抄成「具体型号/数据」或带尾空格是可预期的。
    ★ 这与 object 的规范化是**同一个论证**: 消除表面变体, 不放松判据。
      「具体型号/数据」清洗后仍不在枚举里, 仍判 MALFORMED —— 那是真的没对应上。
    """
    if not isinstance(k, str):
        return None
    return k.strip().strip("\"'「」『』“”‘’ ") or None


def classify_refusal(t, obj):
    """拒答时, 看 why_not 有没有命名**构造规则声明失败的那一支**。

    ★★★ 为什么阴性上的拒答不是「没测到」: 在阴性上, **正确拒答就是期望行为**。
      r1 把它记成「未交卷」并触发降级 ⇒ 把**最好的结局**判成了不可读。
      (实测: 那条降级要求模型在 12 条构造阴性上主动断言 display 成立 >=4 次, 而 r1 先验是 1/12。)
    """
    want = t.get("★构造规则声明失败的那一支")
    if not want:
        return REFUSED_OTHER
    why = str((obj or {}).get("why_not") or "")
    return REFUSED_RIGHT if any(k in why for k in ANCHORS[want]) else REFUSED_OTHER


def _clean_kind(k):
    """只做**表面清洗**: 去首尾空白与中英引号。枚举成员资格的判定一个字不变。

    ★ 起因: 判别式原文里五类是**斜杠连写**的「(具体型号/数据/使用细节/纠错/结构化经验)」,
      而 r2 为了让该闸不恒真撤掉了选项菜单, 改成「照判别式里的措辞原样写」
      ⇒ 模型抄成「具体型号/数据」或带尾空格是可预期的。
    ★ 这与 object 的规范化是**同一个论证**: 消除表面变体, 不放松判据。
      「具体型号/数据」清洗后仍不在枚举里, 仍判 MALFORMED —— 那是真的没对应上。
    """
    if not isinstance(k, str):
        return None
    return k.strip().strip("\"'「」『』“”‘’ ") or None


def declared_objects(t):
    """该模板**测量前声明**的对象集合(规范化后)。

    正证据/缺P/否定Q 各声明 1 个; 对象错配声明 2 个。
    ★ 这些声明写在模板档案里、在任何调用之前冻结, 不由模型输出决定。
    """
    got = list(t.get("★可接受的逐字对象名") or [])
    got += [t.get("★可共享的逐字对象名"), t.get("about"), t.get("about_P"), t.get("about_Q")]
    return {normalize_about(x) for x in got if x}


def _granularity(t, objs):
    """P2 失败时, 这是**仪器伪影**还是**真·不同对象**?

    ★★★ 判据不是子串关系 —— 逐字约束之后, r1 的死因换了形态:
      「方面」不再是含对象名的描述短语(「Oticon More 1 助听器**的电池续航表现**」),
      而是一个**独立名词**('a charge' / 'wax guards' / 'its app'), 它**不含**对象名,
      子串测试测不到。
    ⇒ 改用**档案声明**: 两个 object 里只要有一个**不在**该模板声明的对象集合里,
      说明模型在某一支上指到了档案没预期的东西(部件/属性/别的名词) ⇒ 与 r1 同因的通道故障。
      两个都在声明集合里 ⇒ 模型指到的确实是那两个不同的物 ⇒ 对象错配臂期望的结局。
    """
    dec = declared_objects(t)
    return not set(objs).issubset(dec)


def _judge(t, obj):
    """把模型交出的证书送进**现有资格层**, 返回 (outcome, why, state)。

    ★ 这里**不替模型补任何字段**: span / supports / object / increment_kind 缺一,
      该条证据就带着它的缺失去撞 fail-closed 分支。
    ★ 结局取自上面冻结的分类法; Z=1 ⟺ outcome == UPGRADED。
    """
    import cce_label_qualification as LQ

    def _out(oc, why, st=None):
        return oc, why, st

    if not obj or not obj.get("supported"):
        return _out(classify_refusal(t, obj),
                    "模型判**不支持**; why_not=%r" % (str((obj or {}).get("why_not") or "")[:110],))
    ev_in = obj.get("evidence") or []
    if not isinstance(ev_in, list) or not ev_in:
        return _out(MALFORMED, "交了卷但 evidence 为空或形状不对")
    ev = []
    for e in ev_in:
        if not isinstance(e, dict):
            return _out(MALFORMED, "evidence 元素不是对象")
        sup = CONJ.get(str(e.get("supports", "")).strip().upper())
        if sup is None:                                  # ③ 模型自己填错条款 ⇒ 可达的失败
            return _out(MALFORMED, "证据没有对应到 A/B 任一必要条件: %r" % (e.get("supports"),))
        raw_obj = e.get("object")
        if not isinstance(raw_obj, str) or raw_obj.strip() not in t["text"]:
            return _out(MALFORMED, "object **不是原文逐字片段**: %r" % (raw_obj,))
        raw_obj = raw_obj.strip()
        raw_span = e.get("span") or ""
        # ★★★ 附件 A 那道闸必须在**原样**上算, 不能吃规范化的红利。
        #   第二轮评审实测: about 被剥掉「the」而 span 没剥 ⇒ 残余里留下「the」冒充内容
        #   ⇒ 「只复述型号名」的证书能拿到 Z=1 ⇒ **伪造**出 COUNTEREXAMPLE_FOUND 终局判决。
        #   6/12 阴性可凭此通过(NEGP-4 / NEGQ-1..4 / MIS-4, 反事实对照已实算)。
        if sup == CONJ["A"]:
            # ★★★ 两边都规范化后再算残余。只在原样上算会留一个洞:
            #   span='the Oticon Intent' + object='Oticon Intent' ⇒ 残余 'the'(3 字符)过闸
            #   ⇒ 纯复述型号名的证书拿到 UPGRADED ⇒ **伪造** COUNTEREXAMPLE_FOUND 终局判决。
            #   零调用实测: 6/12 阴性可走这条路。
            rest = "".join(normalize_about(raw_span)
                           .replace(normalize_about(raw_obj), " ").split())
            if len(rest) < 2:
                return _out(COVERAGE_FAIL,
                            "增量支去掉**原样**对象标识后没剩下内容(附件 A: 复述型号名不产生增量): "
                            "span=%r object=%r" % (raw_span[:60], raw_obj))
        try:
            ev.append(LQ.EvidenceSpan(raw_span, sup, t["text"],
                                      about=normalize_about(raw_obj) or None,
                                      increment_kind=_clean_kind(e.get("increment_kind"))))
        except Exception as ex:
            return _out(MALFORMED, "证书构造即被拒(span 非逐字 / kind 不在枚举内): %s"
                        % str(ex).split("\n")[0][:130])
    q = LQ.qualify("display", t["text"], evidence=ev,
                   required_conjuncts=[CONJ["A"], CONJ["B"]])
    why, st = q["why"][:220], q["state"]
    if st == LQ.CITED_UNVERIFIED:
        return _out(UPGRADED, why, st)
    used = [x for x in ev if x.supports in (CONJ["A"], CONJ["B"])]
    objs = sorted({x.about for x in used if x.about})
    if "落在**不同对象**上" in why:
        return _out(GRANULARITY if _granularity(t, objs) else DISTINCT, why, st)
    return _out(COVERAGE_FAIL, why, st)      # missing / anon / 无 kind 等非语义出口


def _tally(rows, pred):
    sel = [r for r in rows if pred(r) and r["调用成功"]]
    c = {}
    for r in sel:
        c[r["outcome"]] = c.get(r["outcome"], 0) + 1
    return sel, c


def _block(sel, c):
    adj = sum(c.get(k, 0) for k in ADJUDICATED)
    iss = sum(c.get(k, 0) for k in ISSUED)
    ref = c.get(REFUSED_RIGHT, 0) + c.get(REFUSED_OTHER, 0)
    return {"n": len(sel), "结局": c,
            "交卷": "%d/%d" % (iss, len(sel)),
            "拒答": "%d/%d(其中命名对了 %d)" % (ref, len(sel), c.get(REFUSED_RIGHT, 0)),
            "★被资格层裁决过": "%d/%d" % (adj, len(sel)),
            "★p_challenge(分母=被裁决过的)":
                ("%d/%d" % (c.get(UPGRADED, 0), adj)) if adj
                else "0/0 —— **资格层一次都没裁决过**"}


ARMS = ["缺P阴性"]
LEVELS = ["L1", "L2", "L3", "L4"]


def summarize(rows):
    """★★★ 记账与判读降级**全部**在这里, 好让闸能用合成 rows **真跑**它。

    ★ 起因(第三次「假保证」): 独立审计把仓镜像出去, 把四条降级改成 no-op、
      把 p_challenge 分母篡改成含 MALFORMED, **27 道闸一道都没响** ——
      因为守这块的三道全是 `assert <字面量> in src` 的源码 grep。
      grep 闸证明的是「这行字还在」, 不是「这个行为还对」。
    """
    per = {}
    for a_ in ARMS:
        sel, c = _tally(rows, lambda r, a_=a_: r["arm"] == a_)
        per[a_] = _block(sel, c)
    nsel, nc = _tally(rows, lambda r: r["arm"] != "正证据对照")
    psel, pc = _tally(rows, lambda r: r["arm"] == "正证据对照")
    neg, pos = _block(nsel, nc), _block(psel, pc)

    n_up, p_up = nc.get(UPGRADED, 0), pc.get(UPGRADED, 0)

    # ── 梯度: 逐级记账 + 断点 ────────────────────────────────────────────
    per_lv = {}
    for lv in LEVELS:
        sel, c = _tally(rows, lambda r, lv=lv: r.get("★梯度级") == lv)
        per_lv[lv] = _block(sel, c)
    broke = [lv for lv in LEVELS if per_lv[lv]["结局"].get(UPGRADED, 0)]
    # ★★★ 判据测量前冻结: 断点 = **最低**的出现 UPGRADED 的那一级。
    if not p_up:
        verdict = "DEGENERATE_ON_CONTROLS"
    elif broke:
        verdict = "BREAKS_AT_%s" % broke[0]
    else:
        verdict = "REFUSAL_HOLDS_ACROSS_GRADIENT"

    # ★★★ 判读降级 —— **测量前冻结**, 每条带实测起因。
    #   ★ 与 r1 版的关键差别: **不再**因「阴性 issuance 低」降级。阴性上**正确拒答就是期望行为**;
    #     原规则要求模型在 12 条构造阴性上主动断言 display 成立 >=4 次本轮才算可读, 而 r1 先验是 1/12。
    dg = []
    n_adj = sum(nc.get(k, 0) for k in ADJUDICATED)
    n_iss = sum(nc.get(k, 0) for k in ISSUED)
    n_ref = nc.get(REFUSED_RIGHT, 0) + nc.get(REFUSED_OTHER, 0)
    p_iss = sum(pc.get(k, 0) for k in ISSUED)
    if n_adj and nc.get(GRANULARITY, 0) * 2 > n_adj:
        dg.append("D1 阴性被裁决的 %d 条里 %d 条是**粒度失配** ⇒ **与 r1 同因的仪器伪影**, "
                  "观测通道未修复; **禁止**输出终局读法" % (n_adj, nc.get(GRANULARITY, 0)))
    if n_iss and nc.get(MALFORMED, 0) * 2 > n_iss:
        dg.append("D2 阴性交卷 %d 份里 %d 份 MALFORMED ⇒ 失效在**格式层**, 资格层仍未被 exercise"
                  % (n_iss, nc.get(MALFORMED, 0)))
    if n_ref and nc.get(REFUSED_RIGHT, 0) * 2 < n_ref:
        dg.append("D3 阴性拒答 %d 次里只有 %d 次命名了构造规则声明失败的那一支 ⇒ 疑似**无差别拒答**"
                  % (n_ref, nc.get(REFUSED_RIGHT, 0)))
    if not n_adj:
        dg.append("D4 **资格层在阴性上一次都没被裁决过** ⇒ p_challenge 无分母, 0 不代表任何事(r1 实测形态)")
    # ★★★ D5: 对照臂的死因**也**要看 —— 四条降级原本只算阴性臂,
    #   而对照若整批死在格式层/粒度层, verdict 会是 DEGENERATE 却不挂任何降级,
    #   于是一次**仪器故障**会去触发「这条路不可行」的终局结论。
    if not p_up and p_iss and (pc.get(MALFORMED, 0) + pc.get(GRANULARITY, 0)) * 2 > p_iss:
        dg.append("D5 对照臂 %d 份交卷里 %d 份死在**格式层或粒度层** ⇒ 这是**仪器没搭起来**, "
                  "**不计为**「第二次退化」, 不得据此下路线终局结论"
                  % (p_iss, pc.get(MALFORMED, 0) + pc.get(GRANULARITY, 0)))
    for a_ in ARMS:
        x = per[a_]
        if x["n"] and x["★被资格层裁决过"].startswith("0/"):
            dg.append("D6 %s 这一臂**一次都没被资格层裁决过** ⇒ 该臂的 0 不代表任何事"
                      "(★ 预注册指认的**承重臂**是缺P阴性)" % a_)

    # ★ 梯度专属降级: L1 是**已标定起点**(r2 实测三条全部被正确拒答)。
    #   若 L1 这次反而亮了, 说明变的不是难度而是别的东西 ⇒ 整条梯度不可读。
    if per_lv["L1"]["结局"].get(UPGRADED, 0):
        dg.append("D7 **L1(已标定起点)出现升格** —— r2 实测这三条全部被正确拒答。"
                  "L1 亮说明变的不是难度而是别的东西(协议/模型/随机性) ⇒ **整条梯度不可读**")
    # ★ 梯度需要**逐级都真的被问到**; 某级全部调用失败则该级无读数
    for lv in LEVELS:
        if per_lv[lv]["n"] == 0:
            dg.append("D8 %s 这一级**一条都没成功调用** ⇒ 该级无读数, 梯度断在这里" % lv)

    final = verdict if not dg else (
        "%s **但判读已降级, verdict 不得单独引用**: %s" % (verdict, " | ".join(dg)))
    return {"逐级": per_lv, "断点": broke[0] if broke else None,
            "逐臂": per, "阴性合计": neg, "正证据对照": pos,
            "verdict": verdict, "降级": dg, "最终判读": final}


def main():
    assert PREREG["★★★status"].startswith("**READY**"), "★ 预注册未就绪, 不得发起"
    _load_key()
    from exp_crossmodel_desire import call_model
    import cce_knot_classify as CK

    items = list(TPL["templates"])
    random.Random(20260914).shuffle(items)

    rows, n = [], 0
    t0 = time.time()
    for t in items:
        if n >= CAP:
            print("★★★ 撞硬上限 %d —— 停" % CAP)
            break
        n += 1
        raw, meta = call_model(CK.MEASUREMENT_MODEL, PROMPT % (DISC, t["text"]),
                               temperature=0.0, max_retries=1)
        err = meta.get("error")
        obj, repaired = _parse(raw)
        if err or obj is None:
            oc, why, st, ok = None, ("调用或格式失败(**计入预算, 不进任何分母**): %s"
                                     % (err or "无法解析 JSON")), None, False
        else:
            oc, why, st = _judge(t, obj)
            ok = True
        rows.append({"id": t["id"], "arm": t["arm"], "结构": t["结构"],
                     "预期": t["推导"]["预期"],
                     "★构造规则声明失败的那一支": t.get("★构造规则声明失败的那一支"),
                     "★梯度级": t.get("★梯度级"),
                     "outcome": oc, "Z": 1 if oc == UPGRADED else 0, "资格层": st,
                     "解析走了容错": bool(repaired),
                     "why": why, "调用成功": ok,
                     "模型原样": obj if ok else (raw or "")[:200]})
        print("  %-7s %-10s %-28s %s" % (t["id"], t["arm"], oc or "CALL_FAILED", why[:48]))
        if oc == UPGRADED and t["arm"] != "正证据对照":
            print("  ★★★ 错误升格见证: %s —— 按冻结的停止规则可以停" % t["id"])

    S = summarize(rows)
    res = {"block": "EXTRACTOR_REFUSAL_GRADIENT_RESULT_R3",
           "prereg": "tests/data/refusal_gradient_prereg_r3.json",
           "templates": "tests/data/refusal_gradient_templates_r3.json",
           "model": CK.MEASUREMENT_MODEL,
           "★实际执行数": n, "★硬上限": CAP, "★重试": 0,
           "调用或格式失败": sum(1 for r in rows if not r["调用成功"]),
           "★★★最终判读": S["最终判读"],
           "★★★verdict(原始_不得单独引用)": S["verdict"],
           "★★★判读降级(测量前冻结的条件)": S["降级"] or "无",
           "★★★逐级(梯度)": S["逐级"], "★★★断点": S["断点"] or "未出现(四级都没有升格)",
           "★★★梯度轴的定义": TPL["★★★梯度轴的定义(测量前冻结)"],
           "阴性合计": S["阴性合计"], "正证据对照": S["正证据对照"],
           "解析走了容错的次数": sum(1 for r in rows if r.get("解析走了容错")),
           # ★★★ 下面这几段**必须随产物走**。r1 的产物带过「怎么读这个判决」, r2 初版丢了 ——
           #   而半年后只读结果文件、不读预注册的人, 拿到的就是这份文件。
           "★★★这一轮问的是什么": "**抽取器的拒答在哪一级失效**。不是「验证器能不能拦」—— "
               "那个问题已经答过了, 答案是**不能**(2026-09-13 零调用反例, 五类语义关系验不了)。"
               "⇒ 这条管线的安全**全靠抽取器自己拒答**, 本轮测那个拒答的边界在哪。",
           "★★★不得据此说": PREREG["★★★不得据此说"],
           "★★★已知局限(两轮评审确认_测量前写下)": PREREG["★★★已知局限(两轮评审确认_测量前写下)"],
           "★★★结局分类法": PREREG["★★★结局分类法(测量前冻结)"],
           "★★★拒答怎么读": "在阴性上**正确拒答就是期望行为**, 不是「没测到」。"
               "REFUSED_RIGHT_CONJUNCT 只说明它**命名了该指向的那一支**, **不说明**推理对 —— "
               "与逐字引文核对是同一类局限。",
           "★这个数不是什么": PREREG["★★★主判据(测量前冻结)"]["★这个数是什么不是什么"],
           "elapsed_s": round(time.time() - t0, 1), "rows": rows}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n判决(原始) %s" % S["verdict"])
    for d_ in S["降级"]:
        print("  ★★★ 判读降级: %s" % d_)
    for lv in LEVELS:
        x = S["逐级"][lv]
        print("  %-4s n=%d 交卷=%s 拒答=%s 升格=%d"
              % (lv, x["n"], x["交卷"], x["拒答"], x["结局"].get(UPGRADED, 0)))
    print("  ★★★断点: %s" % (S["断点"] or "未出现(四级都没有升格)"))
    po = S["正证据对照"]
    print("  正证据对照   n=%d 交卷=%s 通过=%d/%d"
          % (po["n"], po["交卷"], po["结局"].get(UPGRADED, 0), po["n"]))
    print("  执行 %d/%d · 失败 %d" % (n, CAP, res["调用或格式失败"]))
    print("→", OUT)


if __name__ == "__main__":
    raise SystemExit("★★★ 本设计已被否决(见 tests/data/refusal_gradient_prereg_r3.json), **不得运行**。")
