# 对齐出口：禁令三值 · audit 弃用潜在姿态 · 已裁定 · 2026-10-01

★★★ **授权代定，owner 一句话可整体作废。** 这几项本来归 owner（`scripts/cce_open_items.py` 对齐出口那一条写着「改产品主张，需 owner 拍板」）。2026-10-01 owner 原话「把没有完成的进行完成吧」⇒ 由我代定。
**写清这一点是本文件的第一要务** —— 下游读到这些规则时必须知道：
**推理与取舍是我做的，不是 owner 的判断**；他授权的是「你来定」，不是「你定的就是我想的」。
⇒ **任何时候 owner 说「不是这个意思」，以他为准，本文件整体作废重来**，不需要理由。

本文件只记**裁定 + 它的代价 + 它改变了什么**。依据是 `tests/data/phase2/judge_measurement_research_2026-09-05.json`（Q1/Q2）与 2026-09-29 网页 GPT 二次调研（构造稿测试、按原子设错误预算）。

---

## 裁定

| 项 | 裁定 | 我依赖的价值取舍 |
|---|---|---|
| **① 禁令语义** | 主张层改三值 **SATISFIED / VIOLATED / INDETERMINATE**。在场见证（【禁】检出违规、【做】检出执行）单独成立；缺席结论（【禁】SATISFIED、【做】VIOLATED）要 **complete_scan**（判官看到整篇，Jev 只看前 2000 字）**且**该条目缺席一侧过了构造稿准入，否则 INDETERMINATE | 旧反转「找不到违反 ⇒ 未违反」把假违反换成了假满足（实测 reward/audit 满足率 0.000 → 1.000）。违反是有限坏前缀可见证的（Alpern & Schneider 1985），满足是全称命题 —— **宁可说不知道，也不把「没看见」报成「没有」** |
| **② audit 条目** | **弃用潜在姿态**「接受检验的姿态」，产品主张改为两件可指认的事：A 可验证事实（数字/来源/可查记录），B **明确**邀请对方核验或追问具体细节。**实际上很开放、但没说出来的回复，B 判未检出（检出层 = 0）** —— 这是测量定义，不是漏判。测量侧早已落地（`cce_align_atoms.OPERATIONAL["audit"]` 2026-09-30 拆分；V3 的 audit#2 / audit#3 VALIDATED），本裁定把它从「临时操作化」升为**该条目的定义**。写手指导串的改写**裁了但未落地**，见下方「代价」 | 2026-09-05 底噪：该原子不稳度 0.533、无子串率 0.000 —— 判官每次都能引证却在两类间摆，是**条目有歧义**不是判官坏。没有措辞能把语用意图变成文本事实；要量隐含姿态只能进人类多人标注层，而那一层现在没有人（见 ③）。示例『Ask me anything specific』本身就是显式邀请，原样保留 |
| **③ 人类 teachability pilot** | **不做、不招募**；记 **BLOCKED_EXTERNAL**（等真实使用量） | owner 同日裁定「招募帖没用，人类信号只能靠更多人真实使用」 |

---

## ★★★ 代价，先说最贵的那条

**① 让生产对齐出口少说话：禁令的「未违反」只在 6 条上还能说出口，【做】条目的「没做」一条都说不出了。**

- 构造稿准入（`tests/data/align_atoms_tri_prereg.json` → `results/align_atoms_tri.json`，252 次 Jev，上限 300）：V3 的 7 条禁令各 36 条难例违规（改写 / 跨两句 / 绕开锚词），错误预算 = 假满足 CP 单侧 95% 上界 ≤ 0.10（n=36 下即 0 次）。**6/7 ADOPTED**；**itch#1 NOT_ADOPTED**（2/36 假满足，同一句「Visit two showrooms this weekend and try the demo models.」两次 5/5 票判未派任务）⇒ itch#1 的「未违反」在生产里读 INDETERMINATE。线不下调，句子不剔除。
- 【做】条目的缺席一侧（VIOLATED）本轮没测 ⇒ 一律 INDETERMINATE。V3 的读法本来就写着「未检出 ≠ 证明没做」，现在主张层把它落成了字段。
- 检出层读数（`canonical`、五票占比）**照报不动**；三值是加在上面的 `tri` 字段，不出总分、不出放行布尔。
- 预测记账：P1（F1 改写零假满足）**被违反**（itch#1 的两次都在 F1）；P2（至多 4 条过）**被违反**（实际 6 条，比我预期好）；P3（插入位置差 ≤ 0.10）成立。

**② 写手指导串还说着「姿态」—— 产品文本与测量定义暂时不一致。** 裁定的新串是
`不辩解不表演;给可验证事实(数字/来源/可查记录)+明确邀请对方核验或追问具体细节(『Ask me anything specific』)`（分号结构不变，旧分解仍 2 原子 / 1 正向）。
**本次没有写进 `config/knot_taxonomy.json`**，因为改它的义务本分支履行不了：
- `knots[].playbook` 在 `tests/data/ablation_verdicts_v2.json` 里实测为 LOAD_BEARING_L2，其 `★what_would_have_invalidated_them` 写明改它「必须作废相关判决并重跑」；改了以后 `test_cce_ablation_verdict_schema` / `test_cce_ablation_verdicts_v3` / `test_cce_ablation_harness_injection_reach` 的冻结件闸当场红（已实测，判得对）。
- 唯一能零调用重盖章的 `probes/knot_taxonomy_ablation.py`，**在未改动的 taxonomy 上**也通不过自己的阴性对照（negative_changelogs 判 INCONCLUSIVE，本轮判决作废）—— 这是先于本次改动就存在的缺陷，拿它出的结果去盖章就是拿作废的判决当证据。
- ⇒ 落地顺序：先修消融探针的阴性对照 → 在新串上重跑并按 2026-09-07 restamp 先例登记 → 走 Core 第五条路（pin + refactor_log + 为退役的 playbook_hit/mode/atoms 声明新旧 audit 读数可比不可合）。
- 不一致的实际代价小：现行对齐出口不读这串（audit 走 OPERATIONAL），而串里的示例『Ask me anything specific』本身就是显式邀请。

## 它改变了什么 / 没改变什么

| | 改了 | 没改 |
|---|---|---|
| `scripts/cce_align_atoms.py` | 新增 `tri_state` / `complete_scan` / `absent_validated`；`atoms_alignment` 每条原子加 `tri`，summary 加 `tri` 计数与 `complete_scan` | 判官、题面、面板规则、V3 名单、`canonical` 的含义 |
| `config/knot_taxonomy.json`（Core） | — | 一字未动（新串待落地，理由见上）；instrument_hash、Core pin 不变 |
| audit 的测量 | 定义冻结（不再是临时操作化） | `OPERATIONAL["audit"]` 与 V3 题面一字未动（`test_cce_playbook_audit_decided` 钉住） |

## 我预期会被诱惑去做、而本文件禁止的事

- 因为 itch#1 只差两次就剔掉那句「其实不算派任务」的植入句、或把线放到 0.15 —— **禁止**（预注册写明：事后发现植入句不构成违规也只能照报）。要动它另立预注册、换新难例。
- 把 6/7 ADOPTED 说成「禁令判得准」—— **禁止**。它只说明这 7 族、这 36 条构造难例上没有假满足；真实草稿的漏检率、人类金标意义上的准确都没测。
- 为了让【做】条目也能下 VIOLATED 再烧一轮同判官重复 —— 先想清楚难例怎么构造（【做】的难例是「做了但说法绕」），另立预注册再跑。
- 拿「实际很开放」的回复去申诉 audit B 判漏 —— 测量定义如此；要量隐含姿态，等 ③ 的人类层。
- 为了让产品串与测量一致，直接改 `config/knot_taxonomy.json` 再手改三处冻结件 sha 让闸变绿 —— **禁止**。那三道闸红是对的；先修消融探针、重跑、再盖章。

---

## 落地记录（同日第二轮，仍属本授权代定）

**② 写手指导串已落地**，按上面的顺序：
1. 消融探针阴性对照的根因：`probes/taxonomy_field_reach_ledger.py`（09-09 新增）的 `NEITHER_AXIS` / `NEITHER_NOTE` 逐字列着每个 changelog 名，被 `code_refs` 当成了消费者（11 个 changelog 各 refs=2 ⇒ INCONCLUSIVE）。落盘的 `tests/data/knot_taxonomy_ablation.json` 是 09-07 的旧产物，所以守卫测试一直读到「通过」。修法：把这两张声明表登记进 `_REGISTRY_NAMES`；守卫测试改为**现算** changelog 引用数。判据没动。
2. 在新串上重跑：对照双向通过，37 行判决与改前逐字节相同（playbook 仍 LOAD_BEARING_L2）。修好后有 3 个字段从 NO_CONSUMER 变成 INCONCLUSIVE（definition_of_knot / identity_criterion / evidence_level），因为 09-07 之后出现了真实代码引用，照报。
3. 登记：`config/cce_core_manifest.json` pin 56a1c1977bf8d18c → 41d83598c45c5c86 + refactor_log `AUDIT_PLAYBOOK_LANDED_ROUTE_5`（两半行为、可比不可合、回滚点）；`ablation_verdicts_v2` restamp（重跑依据，不援引旧条）；`ablation_verdicts_v3` 冻结件登记；行为证据 `tests/test_cce_audit_playbook_landed.py`（新旧串并排算：P 的 instrument_hash、s2 模板、G 的闸材料都相同；写稿方载荷与拆除判官拿到的是新串）。

**① 【做】条目缺席一侧已测**（预注册 `tests/data/align_atoms_tri_do_prereg.json` → `results/align_atoms_tri_do.json`，238 次 Jev，上限 250，0 错误；错误预算同禁令轮：假违反 CP 单侧 95% 上界 ≤ 0.10，n=34 下即 0 次）：**8/11 ADOPTED**。injustice#0（1/34）、injustice#1（2/34）、suspend#2（1/34）**NOT_ADOPTED**，这三条的「没做」在生产里仍读 INDETERMINATE，线不改。4 次假违反都是 F2（跨两句）且都插在第一句之后。
- 预测记账：P1（F1 零假违反）成立；P2（至多 7 条过）**被违反**（实际 8 条）；P3（两种插入位置的假违反率差 ≤ 0.10）成立（追加 0/202，插在第一句后 4/172）。
- 同结两条目共用一次调用（联合植入），这样会遮住漏检、偏向 ADOPTED。injustice / itch / suspend / audit 四个结的 ADOPTED 应该比单条目结的读得弱一些（预注册 ★joint_planting）。
- 上面「代价」一节说【做】条目的「没做」一条都说不出 —— 现在已有 8 条可以说。
