# CCE 全链路架构、工作流编排与基础参数规范（重构草案 v1.0）

> 文档定位：CCE 平台传播主系统的架构基线与重构规范  
> 重点方向：**Population-first / Population Field / Evidence-first / Measurement-first**  
> 当前日期：2026-08  
> 适用范围：社媒、公开内容、信息传播、广告、网站内容、平台分发与后续行为回测  
> 非默认范围：一对一私信、CRM、个人助手、长期个人画像（这些属于 Individual/Direct 可选模式）

---

## 0. 状态标记

本文所有模块必须标记为以下四种状态之一：

- **[CURRENT]**：当前生产链已经存在并可通过 GitHub 生产工作流验证。
- **[PROPOSED]**：建议重构后进入主链，但当前尚未完整生产化。
- **[RESEARCH]**：测量结构、算法或理论仍需实验验证，禁止当成事实。
- **[LEGACY]**：历史兼容或已退役结构，不应作为新生产设计依据。

---

## 0.1 [MEASURED] 2026-08-18 实测批注（本轮新增，非原草案内容）

本轮对草案的 [CURRENT] 声明与 §21 的风险判断做了实测核对。**三处需要改动**，
逐条列在下面，正文对应小节已就地标注 `[MEASURED 2026-08-18]`。

新增第五种状态标记：

- **[MEASURED]**：有本轮实测数据支撑的结论，附取数动作与 n。**与 [RESEARCH] 的区别是它已经有数，
  与 [CURRENT] 的区别是它描述的可能是缺陷而不是能力。**

### 核对结论速览

| 草案原判 | 实测 | 处置 |
|---|---|---|
| §2.1 生产入口与 3 个 profile | **属实**，与仓库逐字一致 | 保留 |
| §2.2 subject_chain 五段结构 | **属实**，阶段名完全一致 | 保留 |
| §44 Phase 0「不改 current contract gates」 | **不能照做**：其中两个 gate 已证不执行 | 见 §44 Phase 0 改写 |
| §21「9-simplex 是风险」 | **是现状但不恒定**，21 次观测 20 次总和为 1.0，1 次为 0.5 | 升级为 [MEASURED] |
| §23 K1 首次测量 | **作废重做**：首版断言只覆盖 draft 未覆盖 context | 过程与更正保留在 §23 |
| 数据进入链路的节点 | 原草案未写 | **新增 §2.4 节点图**，逐段读码追出 |
| 不确定性来源 | 原草案未涉及 | s1 是**温度阶梯**非单次 t=0，s2 继承其抖动（§2.4.2） |
| 噪声底 | 原草案未涉及 | **`within_js` 一直在算但从未当判据**，阈值 0.25 在 29 次里只响 1 次（§2.4.4） |
| post vs reply 可比性 | 原草案未涉及 | **K=5 vs K=3，不是同一台仪器**（§2.4.5） |
| §23 K1 Reliability | 槽位现成但无数 | **已填入首个基线，见 §23 K1** |

**⚠️ 本节写于本轮最早期，其后的实测远多于此，且第一次测量已作废。**
完整取数记录见 §44.11 ~ §44.16。关键几次：

| run / 探针 | 干什么 | 结果 |
|---|---|---|
| `32095782756` | 同项重跑首测 | ❌ **作废**：断言只覆盖 `draft` 未覆盖 `context` |
| `32096357295` | 同项重跑重做（整项指纹断言，断言经反向测试） | 完全相同读数对 0/6，单结极差 0.65 |
| `probes/seed_probe.py` | P0-0：seed / temperature / 换端点 | 三条路排除两条，见 §44.11 |
| `probes/ladder_probe.py` | 温度阶梯 R=20 受控对照 | 四层 p 全 >> 0.05，无可测增量（§44.14） |
| `32114744002` | 重构后 K1 正式判定 | ❌ 三项不达标（§44.16 修正了其中两项判据的可比性问题） |
| `probes/frozen_s1.py` | 冻结 s1 的 2×2 因子实验，78 个原始 draw | ★ **提高 n 单调改善**，推翻前一组 A/B（§44.16） |

**本轮共有三处结论被后续实测推翻或更正，且全部原样保留在案**：
「temperature 已试过所以不可修」（§2.4.2）、
「阶梯是最大的未拆噪声源」（§44.14）、
「n=5 比 n=1 差」（§44.16）。

---

# 1. CCE 的核心定义

## 1.1 CCE 不是“用户画像系统”

CCE 不应围绕：

- 一个具体的人是谁；
- 某个 Persona 长什么样；
- 某个人会不会喜欢某条内容；
- 某个人应该收到什么个性化刺激；

来建立平台传播主链。

对于公开平台传播，CCE 的第一等对象应为：

> **Population Field（人群主体场）**

个人只保留为：

> **Evidence Unit（证据单元）**

用于：

- 去重；
- 证据归属；
- 时间连续性；
- 防止一人多条内容污染总体；
- 必要时进行纵向研究；
- 一对一个性化模式的可选扩展。

---

## 1.2 CCE 的核心工作

CCE Core 的职责应收缩为：

```text
Stimulus / Observed Response / Transition Evidence
                    ↓
              CCE Measurement
                    ↓
       Dynamic Composition / State Readout
                    ↓
           Confidence / Evidence
```

CCE Core 不负责：

- 定义平台受众；
- 生成 Persona；
- 决定平台分发；
- 模拟用户；
- 预测真实购买为“事实”；
- 自动修改长期主体；
- 自动生成营销内容；
- 把相关性直接称为因果机制。

---

# 2. 当前生产基线

## 2.1 [CURRENT] 生产入口

当前生产提交入口应保持唯一：

```text
.github/workflows/cce-submit.yml
```

提交协议：

```text
cce.submission.v1
```

当前生产 profiles：

```text
outbound_post
outbound_reply
subject_chain
```

新生产集成必须走统一提交入口。

兼容工作流或历史工作流不应继续承担新生产功能。

---

## 2.2 [CURRENT] subject_chain 当前含义

当前 subject_chain 已经不是旧 s0-s8 主链。

其核心结构可概括为：

```text
source_validation
        ↓
parallel measurement
        ↓
exact fingerprint join
        ↓
population aggregation
        ↓
end-to-end audit
```

这里的重要设计应保留：

- 真实响应主体与实际证据绑定；
- reached member 不能由目标受众语料伪造；
- population 不能只用均值替代；
- member distributions 需要无损保留；
- heterogeneity、mixture、coverage、uncertainty 需要独立表达。

---

## 2.4 [MEASURED 2026-08-18] 数据进入链路的节点图

**这一节回答一个此前没写、且已经造成过一次测量作废的问题：envelope 里哪些字段真的进入测量。**

追法：`scripts/cce_submission.py`（envelope → normalized item）
→ `.github/prepare.py`（item → `run/` 文件）
→ `.github/workflows/cce-submit.yml`（`run/` 文件 → CLI 参数）
→ `scripts/cce_full_run.py`（参数 → stage）
→ `scripts/cce_knot_classify.py`（stage → prompt）。逐段读码，非推断。

### 2.4.1 三类字段：进测量 / 只校验记录 / 不进链路

```text
envelope.items[i]
│
├─ draft.text ──────────► items.text ─────────► run/input.txt
│     ├─► s0  取前 2000 字，读出未声明的情境面
│     ├─► s1  stage1 prompt 正文（全文）
│     └─► s4  guard / 文风闸
│                                                          【进测量】
├─ context.summary ─────► items.context ──────► run/context
│     └─► s1  拼进 stage1 prompt **头部**：`平台/形态: {context}`
│              ★ 最易被忽略的一条。它不是元数据，它是 prompt 的一部分。
│              ★ 2026-08-18 一次稳定性测量因在此写入序号而作废（见 §23 K1）。
│                                                          【进测量】
├─ context.declaration ─► items.context_decl ─► run/context_decl.json
│     └─► s0  已声明的面直接采用，不再让模型读出（声明 > 读出 > 未知）
│                                                          【进测量】
├─ guard_profile ───────► run/guard_profile ──► s4  合规闸档位
│                                                          【进测量】
│
├─ context.dimensions ──┐
├─ context.provenance ──┼─► _meta.context_snapshot ─► run/submission_meta.json
├─ surface / platform ──┘     └─► cce_full_run.py 只做两件事：
│                                 ① 核 `text_sha256` 与 run/input.txt 实测是否一致
│                                 ② 原样写进 manifest.meta.submission
│                             **不进入任何 stage 的 prompt 或计算。**
│                                                     【只校验+记录，不进测量】
│
├─ reader.text ─────────► items.reader_text ──► run/reader.txt
│     └─► 主链**不读**。仅 `scripts/reply_loop.py` 使用，
│         而该步在 workflow 里挂 `if: ... && inputs.with_alignment`，**默认关**。
│         ★ 这解释了契约里 `reader_baseline` 为什么从不执行 —— workflow 里根本没有这一步。
│                                                          【不进链路】
│
└─ job_id ──────────────► items.ref_tag ──────► run/ref_tag
      └─► prepare.py 原注释即写明「仅元数据, 不进链路」   【不进链路】
```

### 2.4.2 ★ 不确定性的真实来源：s1 是温度阶梯，不是单次 temperature=0

`scripts/cce_knot_classify.py`：

```python
_base = [0.0, 0.3, 0.6, 0.9, 0.15, 0.45, 0.75]
temps = _base[:k]                 # k=3 → [0.0, 0.3, 0.6]；k=5 → 再加 0.9, 0.15
with ThreadPoolExecutor(...) as ex:
    pvs = [p for p in ex.map(one, temps) if p]
avg = {L: [mean over pvs] for L in LAYERS}
```

- **stage1 按设计就是多温度采样**，K 次并行，四层向量取**平均**。
  这是设计意图，不是缺陷 —— 它要的就是温度展开带来的分布。
- **stage2（九结）确实是 `temperature=0.0`**，但它的输入是 stage1 的产物。
  → **s2 的不可复现有一部分是从 s1 继承的。**

**⚠️ 2026-08-18 二次更正（对抗评审指出，已实查确认）：**

本节初稿写的是「temperature 已经是 0，所以这个方向做过了、无效」。**这句跳步了。**
实查 `scripts/exp_crossmodel_desire.py:71-76`，发往模型的 payload 只有四个字段：

```python
payload = {"model": ..., "messages": [...], "max_tokens": ..., "temperature": ...}
```

**`seed` 从未发送过，`top_p` 也没有。** 即：

- 「把 temperature 设成 0」做过了 ✅
- 「让调用可复现」**从来没有真正尝试过** —— 缺的是 `seed`
- MiniMax 的 OpenAI 兼容端点是否支持 `seed`，**本文档尚未核实，不得假设**

**正确的分解应当是三层，逐层可判：**

| 层 | 是不是缺陷 | 现状 |
|---|---|---|
| s1 多温度展开本身 | **不是**，是设计意图 | 保留 |
| **单个温度点内部的不可复现** | **是**，且可能可修 | **未验证：从未发过 seed** |
| s2 继承 s1 的抖动 | 是 | 若上一行可修，此行随之缩小 |

> **⚠️ 上表在 P0-0 探针跑完后已过期，保留原文只为留下推理链。实测结论见 §44.11：**
>
> | 上表原判 | P0-0 实测 |
> |---|---|
> | 「单个温度点内部的不可复现…可能可修，未验证」 | **端点接受 `seed` 但不实现它**（HTTP 200 而行为不变，n=6 仍 6 个不同输出） |
> | 「MiniMax 是否支持 seed 尚未核实」 | **已核实：不支持**（阿里云端点同样不实现） |
> | 「s1 多温度展开是设计意图，保留」 | **R=20 受控对照：阶梯相对同温重复采样没有可测增量**（四层 p 全 >> 0.05，见 §44.14） |
>
> **正确的最终分解（三条路已走完两条）：**
>
> ```text
> ✅ 已排除  加 seed         —— 两个端点都不实现
> ✅ 已排除  调 temperature  —— temperature=0.0 本身就不确定（同 prompt n=6 得 6 个不同输出）
> ⚠️ 测不出  温度阶梯         —— R=20 下与同温重复采样无可测差异
> ★ 有效     n 次抽样聚合     —— §44.16 实测: 提高 n 单调改善众数占比与极差, 两个 prompt 皆然
> ```

### 2.4.3 同一份 stage1 输出里混着两种统计口径

```text
layers        = K 次采样的平均      ← 聚合
within_js     = K 次采样两两 JS 散度 ← 离散度
appraisal     = pvs[0]              ← **单次抽样**（T=0.0 那一次）
chain_trace   = pvs[0]              ← **单次抽样**
```

**`appraisal` 与 `chain_trace` 是单抽，`layers` 是聚合，二者在同一个 JSON 里没有任何标注区分。**
下游若把它们等同看待即为口径混用。

### 2.4.4 ★★ 噪声底一直在被测量，但从未被当作判据

`within_js` 就是这台仪器的**自测噪声底**。它每次都算、每次都写进 manifest，
但**没有任何 gate 使用它** —— 现有的唯一动作是 `high_divergence_flag`（阈值 0.25），
且该阈值在实测中几乎不触发。

**[MEASURED] n=29 个真实 item（2026-08-17/18 全部生产与测试 run）**

| 层 | 中位 | 范围 | 超现行阈值 0.25 |
|---|---|---|---|
| `desire_vec` | 0.076 | 0.035 – 0.191 | 0 / 29 |
| `need_vec` | **0.106** | 0.011 – **0.267** | 1 / 29 |
| `emotion_vec` | 0.108 | 0.027 – 0.209 | 0 / 29 |
| `action_vec` | 0.083 | 0.009 – 0.138 | 0 / 29 |

**阈值 0.25 设得远高于实际分布，29 次里只响 1 次 —— 接近永久绿。**
按本文铁律，永久绿与永久红是同一种失效：读数与被测对象无关，于是没人再看它。

→ **这是重构里成本最低、收益最高的一处**：噪声底已经在算，只需把它接成判据。
→ 且它天然满足 §23 K1「distribution stability」的要求，不需要新增任何 LLM 调用。

### 2.4.5 post 与 reply 用的不是同一台仪器

```text
outbound_post / post   →  K=5  →  temps = [0.0, 0.3, 0.6, 0.9, 0.15]
outbound_reply / reply →  K=3  →  temps = [0.0, 0.3, 0.6]
```

（`scripts/cce_full_run.py`：`"k": 5 if a.mode in {"post","outbound_post"} else 3`）

**采样次数与温度分布都不同 ⇒ 两者的 `layers` 平均与 `within_js` 离散度不可直接比较。**
本文档此前未记录这一点，而既往台账中存在 post 与 reply 读数并列呈现的情况。

→ **建议列为 K5 Cross-context Validity 的一个具体待查项**：
   同一份文本分别以 K=3 与 K=5 跑，量出仅由 K 造成的读数差，作为「跨模式比较」的下限门槛。

---

## 2.3 [LEGACY] 旧 s0-s8

仓库中仍可能存在：

```text
s0
s1
s2
s3
s4
s5
s6
s7
s8
```

以及旧 full-run 代码。

重构原则：

1. 不立即删除；
2. 迁入 legacy / compatibility 语义；
3. 禁止新模块依赖已退役阶段；
4. 测试应明确阻止“历史组件重新成为生产标准”。

---

# 3. CCE 平台传播主系统的新本体

## 3.1 主体本体只有一个

对于 Broadcast / Platform 场景：

> **Subject = Population Field**

不再把以下对象视为独立主体本体：

- Individual Subject
- Segment Subject
- Target Subject
- Reached Subject
- Activated Subject
- Action Subject
- Conversion Subject
- TikTok Subject
- Facebook Subject
- Hearing Aid Subject

它们应分别归入：

- 证据粒度；
- 模式；
- 窗口；
- Context；
- Partition；
- Domain Projection。

---

# 4. Population Field 模型

## 4.1 基本定义

```text
Population Field
=
Population Definition
× Time Window
× Context
× Structural Variables
× Dynamic Measurement Space
× Domain Projection
× Evidence
× Uncertainty
```

---

## 4.2 Field 的核心组成

```text
POPULATION FIELD
│
├── Definition
├── Boundary
├── Window
├── Structural Slow Variables
├── Universal Dynamic Space
├── Context
├── Domain Projection
├── Density
├── Modes
├── Long Tail
├── Heterogeneity
├── Coverage
├── Uncertainty
├── Evidence
└── Provenance
```

---

# 5. Population Field 中的“Mode / Segment”

## 5.1 Segment 不再视为一种固定人群

应定义为：

> Population Field 中当前时间窗口内出现的高密度结构区域。

例如：

```text
Population Field
│
├── Mode A
├── Mode B
├── Mode C
├── Secondary Modes
└── Long Tail / Unassigned
```

Mode 可：

- create
- continue
- grow
- shrink
- split
- merge
- disappear
- migrate

这些变化首先是：

> **descriptive_not_causal**

禁止直接说某个内容“导致 Segment 分裂”，除非存在实验或其他足够强的因果证据。

---

# 6. Individual 的重新定位

## 6.1 Broadcast 主链

Broadcast 场景不要求永久 Individual Subject ID。

建议使用：

```text
evidence_actor_ref
```

而非：

```text
subject_id
```

其用途仅限：

```text
deduplication
provenance
response ownership
longitudinal evidence linking
sampling control
```

---

## 6.2 Direct / Individual 可选模式

只有以下场景才启动真正 Individual Subject：

- 私信；
- CRM；
- 销售对话；
- 一对一邮件；
- 个人助手；
- 长期用户研究；
- 个人推荐。

Individual 模式不得反向污染 Broadcast 内容策略。

---

# 7. Population 的参数体系

参数不分“几十种主体各自一套”。

应统一为四层。

---

## 7.1 Universal Dynamic Space

所有行业共享的动态主体坐标。

示例：

```text
desire
need
emotion
action
attention
understanding
belief
uncertainty
trust
interest
intent
readiness
```

这些属于通用测量空间。

---

## 7.2 Structural Slow Variables

不是绝对固定，而是慢变量。

```text
language
age_band
life_stage
role_structure
capability
resource_constraint
economic_constraint
accessibility
knowledge_level
category_experience
```

建议增加：

```text
timescale
last_updated
confidence
evidence_refs
```

---

## 7.3 Context Conditions

Context 不属于主体本体。

```text
platform
surface
time
location
device
session
social_context
relationship_context
task
current_goal
recent_events
exposure_context
```

---

## 7.4 Domain Projection

行业特有变量作为挂载层。

例如助听器：

```text
hearing_difficulty
device_experience
stigma
caregiver_involvement
audiologist_trust
insurance_context
price_reference
```

例如香氛：

```text
scent_family_preference
occasion
projection_preference
longevity_preference
brand_signal
```

Domain Projection 不应进入 CCE Universal Core。

---

# 8. Geography / Region 的正确定位

地域不是独立主体。

建议：

> **Geography = Population Partition + Context**

例如：

```text
Global Population Field
│
├── US Partition
├── UK Partition
├── Germany Partition
└── Nigeria Partition
```

地域必须记录，但不默认认为不同地域一定是不同主体结构。

真正的差异变量可能来自：

- 语言；
- 文化；
- 法规；
- 收入结构；
- 医疗系统；
- 平台生态；
- 社会规范；
- 产品可得性；
- 价格参照。

---

# 9. Platform / Surface 的定位

不要建立：

```text
TikTok Subject
Facebook Subject
Reddit Subject
```

而是：

```text
Population Field
× Platform Context
× Surface Context
× Time Window
```

例如：

```text
platform = Reddit
surface = subreddit/community
```

平台是较稳定 Context，具体 community / feed / discovery surface 是更动态的 Context。

---

# 10. Stage / Window 模型

Target、Reached、Responded、Acted、Converted 不应建成不同主体。

它们是同一个 Population Field 的条件窗口。

---

## 10.1 建议窗口类型

```text
candidate
target
delivered
reached
responded
activated
acted
converted
```

是否保留 responded 与 activated 两者，应由证据定义决定。

若无法区分：

```text
responded == activated
```

则不要人为造两个窗口。

---

## 10.2 Evidence Gate

### Target

要求：

```text
target_definition
target_frame
planned_distribution
pre_exposure_freeze
```

### Delivered

要求平台分发记录。

### Reached

要求真实曝光 / 入站成员证据。

### Responded / Activated

要求真实响应或可验证 CCE observed_response。

### Acted

要求行为数据：

```text
click
search
save
share
dm
lead
...
```

### Converted

要求商业结果 join。

---

# 11. Population Stage Delta

比较的是条件分布变化。

```text
Target vs Delivered
Target vs Reached
Reached vs Responded
Responded vs Acted
Acted vs Converted
```

若相邻窗口证据不可比：

```text
delta = NOT_TESTABLE
```

禁止强算。

---

# 12. 多模态输入总体架构

## 12.1 原始链路

```text
Raw Media
   ↓
Signal Decomposition
   ↓
Multimodal Perception
   ↓
Observation
   ↓
Atomic Event
   ↓
Composite / Cross-modal Event
   ↓
CCE Measurement
```

---

# 13. Signal Decomposition

## 13.1 Video

```text
frames
shots
scenes
camera
person
object
action
gaze
lighting
composition
motion
ocr
temporal change
```

---

## 13.2 Audio

必须保留两条并行路径：

```text
Original Mix
+
Source Separation
```

Source Separation：

```text
speech
BGM
SFX
ambient
noise
other
```

---

# 14. Audio 参数

## 14.1 Original Mix

```text
total_loudness
dynamic_range
clarity
masking
overall_energy
speech_to_music_ratio
speech_to_ambient_ratio
ducking
overlap
crossfade
```

---

## 14.2 Speech

```text
ASR
speaker
speaker_diarization
pitch
loudness
energy
speech_rate
rhythm
pause
stress
timbre
prosody
intonation
```

---

## 14.3 BGM

```text
BPM
rhythm
key
mode
harmony
instrument
timbre
energy
dynamic_range
structure
build_up
drop
chorus
transition
peak
entry
exit
ducking
```

---

## 14.4 SFX / Ambient

```text
type
intensity
direction
distance
duration
repetition
sync_with_visual
```

---

# 15. Visual 参数

```text
scene
environment
person_count
person_position
face
expression
gaze
body_pose
gesture
action
object
product
brand
camera_angle
shot_size
camera_motion
focus
depth
lighting
color
composition
visual_salience
transition
```

---

# 16. Observation Schema

Observation 必须只描述：

> 机器实际观测到什么。

不能直接写心理结论。

建议：

```json
{
  "observation_id": "obs_001",
  "source_ref": "media_001",
  "modality": "audio",
  "time": {
    "start": 5.2,
    "end": 6.1
  },
  "feature": "bgm_loudness",
  "value": -8.2,
  "unit": "db",
  "confidence": 0.94,
  "parser": {
    "name": "parser_name",
    "version": "x.y.z"
  },
  "evidence_ref": "raw_segment_001"
}
```

---

# 17. Event Schema

Event 负责回答：

```text
谁
什么时候
在哪里
对什么
做了什么
如何做
和其他事件有什么关系
```

建议：

```json
{
  "event_id": "evt_001",
  "event_type": "emphasis_event",
  "time": {
    "start": 5.2,
    "end": 6.3
  },
  "actors": ["person_01"],
  "targets": ["viewer"],
  "objects": [],
  "actions": ["emphasize_claim"],
  "modalities": [
    "speech",
    "music",
    "camera",
    "subtitle"
  ],
  "observation_refs": [
    "obs_001",
    "obs_002",
    "obs_003"
  ],
  "relations": [
    "synchronized",
    "reinforcing"
  ],
  "confidence": 0.86
}
```

---

# 18. Cross-modal Event

允许多个原子事件组合。

关系建议第一版只保留有限枚举：

```text
supports
reinforces
conflicts
contrasts
synchronizes
precedes
follows
overlaps
masks
substitutes
amplifies
attenuates
```

---

# 19. CCE Measurement Modes

当前建议冻结三种：

```text
stimulus
observed_response
transition
```

---

## 19.1 stimulus

测：

> 内容 / 刺激本身呈现什么动态结构。

不代表真实用户一定发生该状态。

---

## 19.2 observed_response

测：

> 真实响应证据中呈现什么动态结构。

属于对真实 evidence 的测量。

---

## 19.3 transition

要求：

```text
evidence-bound pre_state
```

输出：

```text
pre_state
post_state
exact_delta
```

在真实 post-state estimator 尚未充分校准前：

```text
transition_prediction != observed fact
```

---

# 19.5 [MEASURED 2026-08-18] Measurement System —— 本文档原缺的一整层

**来源**：外部架构评审指出 `CCE Measurement` 仍是一个黑盒名字，应正式展开。
**已实现并上生产**（公开仓 HEAD `b0df9728756e`，验证 run `32126692815`）。

## 19.5.1 为什么必须有这一层

它防的是一句话：**原始 LLM draw 被当成「人的心理状态」。**

本轮实测已证这不是假想：单次 stage2 调用给出的是一次抽样而非测量
（同项重跑完全相同读数对 0/6），而这些读数曾被直接写进台账当读数用。

## 19.5.2 结构

```text
CCE MEASUREMENT SYSTEM
│
├── Instrument Definition      ← 已实现
│   ├── ontology_version
│   ├── prompt_sha256          ★ 由模板文本导出，改一个字哈希就变
│   ├── model / endpoint
│   ├── sampling_policy        s1_k · s1_temps · s2_n
│   └── aggregation_policy     support_rule · intensity_stat · composition
│
├── Repeated Measurements      ← 已实现（s2 n=5，逐 draw 保留 occur）
├── Reliability                ← 部分实现（within_js 已接闸；见下方修正 b）
├── Calibration                ← 部分实现（within_js 逐层阈值 n=31）
├── Aggregation                ← 已实现（intensity × support 两维）
├── Uncertainty                ← 已实现（per_knot range / mode_share）
└── Qualified Readout          ← 已实现，为链路最后一段
        ↓
   只有 Qualified Readout 允许进入下游 / Population Field
```

## 19.5.3 `instrument_hash`：那次 A/B 作废的可执行解药

**2026-08-18 的一组 A/B 作废，根因是 prompt 与采样数一起变了而无人察觉** ——
当时没有「仪器」这个一等概念，两臂看起来只差一个环境变量。

仪器版本化之后，**那种混淆在构造上不可能发生**：

```python
assert_same_instrument(readouts)   # 跨读数比较前强制拦截
```

两条拒绝规则，均有反向测试：
- **不同 `instrument_hash` → 拒绝比较**（换了仪器就是换了尺子）
- **缺 `instrument_hash` → 拒绝比较**（无从判断是否同一把尺子）

★ 关键设计：`prompt_sha256` 由**模板文本本身**导出（变量位用哨兵占位）——
**改一个字哈希就变，忘不掉**；而被测内容变化**不**改变哈希，
否则每条内容都会成为不同仪器。两个方向都有断言。

## 19.5.4 Qualified Readout：把零散的扣发收敛成一个具名出口

此前每处扣发都是零散加的（s1 超噪声底扣发该层 `top`、s2 首结不稳扣发 `playbook`），
**没有一个地方回答「这次运行到底哪些读数可用」**——
于是不确定性只在一条路上生效（`reply_loop.py` 曾照旧发 PASS/FAIL）。

生产实跑（run `32126692815`）：

```text
instrument_hash  3170a226dec8726b
usable  (5)  s1.tops.desire / need / emotion / action · s2.distribution
withheld(1)  s2.playbook_primary ← top1 不稳: [display, reward, audit, display, display]
```

**纪律：不在 `usable` 里的不是「弱证据」，是没有读数。**

## 19.5.5 三处对外部评审建议的修正（实测依据）

**(a) 评审引用的数据落后一版。** 它引「同稿 n=8、0 个相同读数对、极差 0.65」
作为「重构无效」的证据。**§44.16 的冻结 s1 实验之后该结论已被推翻** ——
n 扫描单调改善（众数占比 0.615 → 0.906 → 0.962）。
评审的**结论**（measurement 优先）不受影响，但那组数字不应再作此用。

**(b) 评审的 `Reliability` 层列了 `top_stability` —— 该量已证为坏判据。**
`len(set(tops)) == 1` 在 **n=1 时恒真**，且 `P ≈ p^n` 随 n 单调下降是构造性的
（提高 n 就会让它变差，是算术不是现象）。
→ 该层必须用**众数占比 `mode_share`**（跨 n 可比），不能用一致性。已按此实现。

**(c) 评审未涉及本轮发现的天花板：`s1` 的单抽 `appraisal` 被注入 `s2` 的 prompt。**
**【2026-08-18 已修并上生产，见 §19.5.7】**
（`cce_knot_classify.py` 的 stage2 prompt 里嵌 `s1['tops']` 与 `s1['appraisal']`，
而后者取自 `pvs[0]`，是单次抽样。）
一个 rep 内 n 次 s2 抽样**共享同一份抖动过的 prompt**，
⇒ **s2 的任何聚合器都碰不到 rep 间方差。**
→ **Measurement System 的仪器边界必须包含 s1**，否则这一层建在天花板底下。
   §44.16 实测佐证：两个冻结 s1 区组的四层 tops 有两层完全不同，
   且 prompt 效应在两区组间相差 3.6×（两因子不可加）。

## 19.5.6 由此重排的优先级（采纳评审建议）

```text
P0  Production Truth        contract / manifest / gate 真执行      ← §44.12 已完成
P1  Measurement System      仪器 / 重复测量 / 噪声底 / 出口闸       ← 本节，已完成主体
P2  Observation / Event     多模态、跨模态事件
P3  Population Field        坐标 / 密度 / Mode / 窗口 / 分区 / 时间演化
P4  Knot Latent Structure   K0–K8
P5  Distribution + Behavior + Outcome
P6  Mechanism Learning
```

**与原 §44 最大的区别：Measurement System 提到了 Population Field 前面。**

评审的一句话值得原样保留：

> 先修 Measurement → 确认 Reliability → 收集大量真实 Observation → 再研究 Knot latent structure → **最后**决定九结到底是什么；
> 而不是「觉得 9-simplex 不合理 → 直接设计一个新的 6+3 → 上线」，
> **否则只是用一个未经验证的结构替换另一个未经验证的结构。**

⚠️ **这条批评对本轮成立**：§22 的四层结构已上生产，而 **K0–K8 一条都没跑**。
本文档不为此辩解，登记在案：四层结构目前的地位是
**「比单层 simplex 更能表达同时高企的驱动与阻挡」的结构性改进，
不是「被验证过更接近真实潜结构」的结论。**

---

# 20. 九结：当前地位

## 20.1 [RESEARCH] 九结不能继续被视为已经验证的心理地基

当前九结：

```text
Drive:
pain_seek
injustice
belong
reward
display
itch

Brake:
suspend
inertia
audit
```

建议定位：

> **candidate measurement ontology**

而不是：

> 人类主体性的已证明九个真实潜变量。

---

# 21. 九结当前最大风险：统一 9-simplex

## [MEASURED 2026-08-18] 这不是风险，已经是现状

实测 8 次同稿重跑，**权重总和 8/8 恰为 1.0**。九结当前**就是** compositional data，
本节以下推论全部已经生效，不是假设。

附带两条实测修正：

- **0.05 网格不是硬约束**。本轮出现 `0.33` 与 `0.12`。
  （此前 13 条读数全部落在 0.05 网格上，属小样本巧合，不构成结构性证据。）
- **九结中同时激活的从未超过 4 个**（本轮 2–4 个，此前 13 条为 1–3 个）。
  九个结里长期有五个以上恒为零。**这本身是 K0 Coverage 的负面证据，
  应在 §23 K0 中作为待查项登记。**

---

如果计算结构是：

```text
K1 + K2 + ... + K9 = 1
```

则九结成为 compositional data。

固定总和会导致：

> 一个分量增加时，其他分量必须相对下降。

因此必须明确：

```text
relative composition
≠
absolute intensity
```

---

# 22. 九结建议的新候选模型

## 22.1 第一层：Evidence

每结先输出：

```text
evidence_strength
evidence_refs
confidence
```

---

## 22.2 第二层：Independent Intensity

允许：

```text
reward = 0.88
audit = 0.81
```

同时成立。

不强制总和为 1。

---

## 22.3 第三层：Within-family Composition

推动族内部：

```text
sum(drive_composition) = 1
```

阻挡族内部：

```text
sum(brake_composition) = 1
```

同时保存：

```text
drive_mass
brake_mass
```

示例：

```yaml
drive_mass: 0.78
brake_mass: 0.71

drive_composition:
  reward: 0.35
  belong: 0.22
  pain_seek: 0.18
  display: 0.10
  injustice: 0.08
  itch: 0.07

brake_composition:
  audit: 0.59
  inertia: 0.27
  suspend: 0.14
```

---

## 22.4 第四层：Drive × Brake Interaction

允许识别：

```text
high drive / low brake
high drive / high brake
low drive / high brake
low drive / low brake
```

不能把“想要很强 + 审核很强”压扁成一个单一占比。

---

# 23. 九结研究 Gate

在修改生产算法前，建立 research branch 比较不同模型。

---

## K0 Coverage

九结能否覆盖真实材料？

```text
unknown_rate
unmapped_evidence_rate
```

---

## K1 Reliability  ← **★ 本次重构选定的验收 gate**

同一材料不同模型 / 标注者是否稳定？

```text
agreement
distribution stability
confidence calibration
```

### [MEASURED 2026-08-18] 首个基线：同项重跑 n=8

> **⚠️ 第一次测量作废并已重做，过程保留在案。**
> 首次实验（run `32095782756`）只断言了 `draft.text_sha256` 相同，
> 却在 `context.summary` 里写了「第 1/4 份」这样的序号——而 `context` 正是喂给结分类器的 `--context`。
> **四份的输入并不相同，测到的是上下文敏感度，不是重跑稳定性。**
> 这是一个典型的假检查：**断言只覆盖了输入的一部分**。
> 重做时改为断言「整项去掉 `job_id`/`content_id` 后逐字相同」，并对该断言做了反向测试
> （改一个字的 context 必须被抓到）。**以下数据来自重做的 run `32096357295`。**

**取数动作**：两份已过闸稿件各复制 4 份，同组各项**除 `job_id`/`content_id` 外全部字段逐字相同**
（含 `context`、`declaration`、`dimensions`、`reader`），提交前以整项指纹断言，断言本身经反向测试。

| 指标 | A = post8 正文 (n=4) | B = 一条回复稿 (n=4) |
|---|---|---|
| **完全相同的读数对** | **0 / 6** | **0 / 6** |
| 不同读数种类 | 4 | 4 |
| `s1_readout` 不同种类 | 2 | 4 |
| **单结权重最大极差** | **0.65**（`pain_seek`, 0.00–0.65） | 0.35（`audit`, 0.00–0.35） |
| 激活结个数 | 3, 1, 3, 2 | 4, 3, 2, 3 |

**8 次同项重跑产生 8 个互不相同的分布。零重复。**

### ★★ 根因：`temperature=0.0` 已经设了，但没有带来确定性

`scripts/cce_knot_classify.py:126` 是 `call_model("M3", prompt, temperature=0.0)`。
**采样温度不是原因。** 因此重构的第一件事不是给九结分层，而是**让这台仪器先能复现**。

同批还发现 simplex 不是恒定约束：`stab2_A_2` 的权重总和只有 **0.5**
（此前 21 次观测中 20 次为 1.0）。**「总和恒为 1」这条本身也不稳定。**

### ★ 由此得出的第一条硬约束：跨稿比较当前不可做

同稿噪声底（单结极差 **0.37**）已经吃掉大部分跨稿差异
——同期 13 条不同稿件的 `display` 取值范围只有 0.30–1.00。

这与本项目既有铁律同源：**报排名之前必须先算内部离散作噪声底，
差距落在噪声内的层禁止排名。**（原用于 JS 散度层，现证同样适用于 `s2_knots`。）

→ **在 K1 达标之前，任何「A 稿 display 高于 B 稿」的说法都不成立。**
→ 已产出的所有单次 `s2_knots` 读数应标注为**单次抽样，不是测量**。

### ★ K1 有一个现成且零成本的分子：`within_js`

见 §2.4.4：仪器每次运行都已经在算 K 次采样之间的 JS 散度并写进 manifest，
**只是从未被任何 gate 使用**。把它接成判据不需要新增任何 LLM 调用。

实测噪声底（n=29）：`desire` 中位 0.076 · `need` 0.106 · `emotion` 0.108 · `action` 0.083。
现行阈值 0.25 在 29 次里只触发 1 次，**接近永久绿**。

**建议 K1 拆成两个可独立判定的子项：**

- **K1-a 层内离散（零成本，立即可上）**：`within_js` 各层中位数 ≤ 现基线，
  且单次超过 `中位 + 2×MAD` 时判红。阈值必须从实测分布定，不能沿用 0.25。
- **K1-b 同项重跑（需 n 次重跑，成本 ×n）**：见下表。

### K1 的可判形式（本次重构的验收 gate，含 n 与量纲）

| 项 | 阈值 | 当前基线 |
|---|---|---|
| 同稿重跑次数 | n ≥ 8 | 8 ✅ |
| 完全相同的读数对占比 | **≥ 6/8** | **0/6** ❌ |
| 单结权重极差 | **≤ 0.10** | **0.37** ❌ |
| top-1 结一致率 | ≥ 7/8 | 7/8 ✅（A 4/4 + B 3/4） |

**两项达标、两项不达标。重构后必须四项全过才算 K1 通过。**

**反向测试（这道闸必须能观察到失败）**：把两份**内容不同**的稿子按同组提交，
若闸判「稳定」则闸本身失效 —— 它必须对真实差异报红。
不做这一步的 K1 等同于没有 K1。

---

## K2 Separability

九个结是否真正可区分？

---

## K3 Co-occurrence

哪些结天然共现？

---

## K4 Latent Structure

比较：

```text
Model A: 9-class simplex
Model B: 9 independent intensities
Model C: 6-drive simplex + 3-brake simplex + masses
Model D: data-driven latent structure
```

---

## K5 Cross-context / Cross-region Validity

跨：

```text
language
region
platform
surface
time
```

是否仍测量相同或可比结构。

---

## K6 External Validity

与真实：

```text
watch
search
click
share
lead
purchase
```

的关系是否稳定。

---

## K7 Incremental Validity

九结相对于：

```text
raw text baseline
simple semantic baseline
basic CCE layers
```

到底增加多少有效信息。

---

## K8 Intervention

真正改变相关刺激后：

```text
outcome_delta
```

是否按假设变化。

---

# 24. Population Field 的九结表达

禁止只保存总体均值。

必须保存：

```text
knot_intensity_distribution
drive_brake_joint_distribution
co_occurrence
modes
heterogeneity
quantiles
unassigned_mass
uncertainty
```

---

# 25. Distribution Plane

分发必须独立。

```text
Content
   ↓
Platform Distribution
   ↓
Delivered
   ↓
Reached
```

核心原则：

```text
Activation != Distribution
```

内容能否激活谁，不等于平台会把内容送给谁。

---

# 26. Behavior Plane

真实行为独立记账：

```text
impression
view
watch_time
completion
rewatch
like
comment
save
share
search
click
follow
dm
lead
purchase
repeat_purchase
```

这些是 Observed Outcome。

---

# 27. Evidence / Provenance Plane

所有高层结论必须能够回溯：

```text
CCE Result
   ↓
Measurement
   ↓
Event
   ↓
Observation
   ↓
Raw Evidence
```

建议 provenance 结构借鉴：

```text
Entity
Activity
Agent
```

核心字段：

```text
source_ref
generated_by
parser_version
schema_version
cce_version
timestamp
confidence
evidence_refs
```

---

# 28. Archive Plane

GitHub Actions artifact 不应作为长期学习唯一存储。

应增加持久化归档：

```text
GitHub Artifact
      ↓
Archive Worker
      ↓
PostgreSQL / Supabase
```

第一阶段不需要向量数据库。

---

## 28.1 建议结构化表

```text
runs
artifacts
raw_sources
observations
events
cross_modal_events
measurements

population_definitions
population_windows
population_modes
population_membership_evidence
population_snapshots

distribution_events
behavior_events
outcomes

mechanism_candidates
mechanisms
experiments

schema_versions
model_versions
```

---

# 29. Mechanism Learning

Mechanism 不能一发现相关性就进入“手法库真理”。

状态建议：

```text
observed
candidate
preregistered
tested
replicated
rejected
```

---

## 29.1 Mechanism Schema

```json
{
  "mechanism_id": "mech_001",
  "status": "candidate",

  "population_condition": {},
  "context_condition": {},

  "event_pattern": [],

  "activation": {},
  "inhibition": {},

  "state_transition": {},

  "behavior_effect": {},
  "outcome_effect": {},

  "evidence": {
    "sample_size": 0,
    "replications": 0,
    "confidence": 0
  },

  "provenance": {}
}
```

---

# 30. Strategy Plane

Mechanism Intelligence 之后才进入内容策略。

```text
Mechanism Intelligence
        ↓
Persuasion Strategy
        ↓
Narrative Strategy
        ↓
Multimodal Creative Strategy
        ↓
Content Generation
```

---

# 31. Persuasion Strategy

建议九个策略功能：

```text
Subject / Population Condition
Need Activation
Consequence
Cognitive Reframing
Target Belief
Solution / Persuasion Mechanism
Evidence
Inhibition Resolution
Action Transition
```

这些不是固定九段式脚本。

---

# 32. Population-aware Content Strategy

平台内容不再消费 Persona。

输入：

```text
dominant_modes
secondary_modes
shared_needs
shared_inhibitions
high_density_intersections
under_covered_regions
desired_state_transition
coverage_objective
activation_objective
inhibition_constraints
platform_context
domain_context
```

输出目标：

> 设计 Population Field 中的“覆盖形状”。

---

# 33. 群体传播的优化目标

Individual 模式更强调：

```text
Depth of Activation
```

Broadcast 模式更应关注：

```text
Population Coverage
× Activation Strength
× Robustness
− Inhibition
```

注意：

群体不是“不需要深度”。

群体需要的是：

> **共享结构上的深度**

而不是：

> **单一个体特异信息上的深度**

---

# 34. 多入口内容

群体内容允许不同 Mode 从不同入口进入，最后汇合到共同目标状态。

```text
                Content

         ┌────────┼────────┐
         ↓        ↓        ↓
      Mode A    Mode B    Mode C
         │        │        │
         └────────┼────────┘
                  ↓
            Shared State
                  ↓
             Next Action
```

---

# 35. GitHub 工作流建议

## 35.1 保持当前生产控制面

```text
cce-submit.yml
```

继续作为统一入口。

---

## 35.2 新增 Media Ingest Workflow

建议：

```text
cce-media-ingest.yml
```

职责：

```text
source validation
media extraction
signal decomposition
multimodal parser
observation generation
event assembly
artifact manifest
```

不得直接做：

```text
subject inference
behavior prediction
mechanism claim
```

---

## 35.3 Production / Research / Compatibility 分层

```text
.github/workflows/

production/
    cce-submit.yml
    cce-media-ingest.yml

research/
    knot-structure-eval.yml
    mechanism-experiment.yml
    parser-benchmark.yml

compatibility/
    legacy workflows
```

若目录结构不便改，可至少通过 registry 显式标记 class。

---

# 36. Capability Registry

每项能力至少包含：

```yaml
capability_id:
status:
  - production_github
  - component_only
  - research_only
  - missing
  - legacy

input_contract:
output_contract:
workflow:
version:
evidence_required:
fallback_policy:
```

---

# 37. Workflow Registry

```yaml
workflow_id:
class:
profile:
accepted_schema:
capabilities:
stages:
artifact_contract:
completion_gate:
production_complete_allowed:
```

---

# 38. Manifest

任何生产 run 都必须输出 Manifest。

核心字段：

```text
submission_id
workflow_id
profile
started_at
completed_at

requested_items
completed_items
failed_items

artifact_hashes
contract_versions
model_versions

complete
failed_at
production_verified
```

原则：

```text
complete != true
→ 禁止声称“完整跑了 CCE”
```

---

# 39. 基础 Contract 列表

> ★ **就地更正（2026-09-04）**：下面这份 `/contracts/` 布局**是当年的建议，不是现状**。
> 仓库走了另一种布局，本节保留原文只为可追溯。**读这一节不要据它去找文件。**
> 现行真相源：`config/cce_*_contract_v*.json`（5 个契约）+ 4 个注册表，
> 权威顺序见 [`docs/README.md`](README.md)，完整更正见 §19.5.52。
> 更正写在这里而不是只写在 §19.5.52 —— 更正放在远处，读这一节的人仍然会被误导。

建议仓库最终统一：

```text
/contracts/

submission.schema.json
context.schema.json

raw_source.schema.json
observation.schema.json
event.schema.json
cross_modal_event.schema.json

measurement_request.schema.json
measurement_result.schema.json

population_definition.schema.json
population_window.schema.json
population_mode.schema.json

distribution_event.schema.json
behavior_event.schema.json
outcome.schema.json

mechanism.schema.json
experiment.schema.json

manifest.schema.json
```

---

# 40. 推荐仓库结构

```text
cce-engine/

├── .github/
│   └── workflows/
│       ├── cce-submit.yml
│       ├── cce-media-ingest.yml
│       └── research/
│
├── config/
│   ├── capability_registry.json
│   ├── workflow_registry.json
│   ├── taxonomies/
│   └── research/
│
├── contracts/
│   ├── submission/
│   ├── context/
│   ├── observation/
│   ├── event/
│   ├── measurement/
│   ├── population/
│   ├── behavior/
│   ├── mechanism/
│   └── manifest/
│
├── cce/
│   ├── foundation/
│   ├── measurement/
│   ├── population/
│   ├── evidence/
│   ├── archive/
│   ├── mechanism/
│   └── strategy/
│
├── adapters/
│   ├── text/
│   ├── video/
│   ├── audio/
│   ├── image/
│   └── platform/
│
├── legacy/
│
├── tests/
│
└── docs/
```

---

# 41. 完整工作流编排

```text
                         REAL WORLD
                              ↓
                         RAW SOURCE
                              ↓
                  SIGNAL DECOMPOSITION
                              ↓
                  MULTIMODAL PERCEPTION
                              ↓
                         OBSERVATION
                              ↓
                       ATOMIC EVENTS
                              ↓
                   CROSS-MODAL EVENTS
                              ↓
                    CCE MEASUREMENT
                              ↓
                    MEASUREMENT ARTIFACT
                              ↓
                     POPULATION FIELD
                              ↓
               MODES / HETEROGENEITY
                              ↓
                    TARGET POPULATION
                              ↓
                       STRATEGY
                              ↓
                         CONTENT
                              ↓
                      DISTRIBUTION
                              ↓
                  DELIVERED / REACHED
                              ↓
                 RESPONDED / ACTIVATED
                              ↓
                           ACTED
                              ↓
                         CONVERTED
                              ↓
                       EVIDENCE GRAPH
                              ↓
                  POPULATION FIELD UPDATE
                              ↓
                   MECHANISM DISCOVERY
                              ↓
                    EXPERIMENT / TEST
                              ↓
                  REPLICATED MECHANISM
                              ↓
                       NEW STRATEGY
                              ↺
```

---

# 42. 四条独立 Ledger

必须分开：

## Content Ledger

```text
内容里发生了什么
```

## Population Ledger

```text
当前 Population Field 是什么结构
```

## Distribution Ledger

```text
平台实际送给了谁
```

## Outcome Ledger

```text
实际发生了什么行为与商业结果
```

Attribution 层再连接。

---

# 43. 核心铁律

1. Raw ≠ Observation  
2. Observation ≠ Event  
3. Event ≠ State  
4. State ≠ Behavior  
5. Behavior ≠ Outcome  
6. Population Field ≠ Persona  
7. Mode ≠ 固定人群  
8. Individual ≠ Broadcast Target  
9. Activation ≠ Distribution  
10. Target ≠ Reached  
11. Responded ≠ Acted  
12. Prediction ≠ Fact  
13. Correlation ≠ Mechanism  
14. Mechanism 必须有 Evidence  
15. Inference 必须有 Confidence  
16. 所有结果必须有 Version  
17. 所有高层结论必须可追溯到 Evidence  
18. Population 不能用均值虚构“平均人”  
19. 不可比窗口的 Delta = NOT_TESTABLE  
20. 新模态增加 Parser，不应修改 CCE Core  
21. 研究工作流不得产出 production complete=true  
22. Legacy 组件不得成为新生产依赖  
23. 九结当前是 candidate ontology，不是已验证真理  
24. 九结 absolute intensity 与 relative composition 必须分离  
25. 群体内容优化以 Population Coverage / Structure 为中心，不以 Persona 为中心  

---

# 44. 重构实施阶段

## Phase 0：冻结当前生产基线

### [MEASURED 2026-08-18] ⚠️ 原文「不改 current contract gates」不能照做

实测发现当前契约里有两个 gate **声明了但不执行**，而 `complete=true` 检测不到：

| 缺陷 | 实测 |
|---|---|
| `outbound_reply` 声明 6 段，`manifest.chain` 只有 5 段 | `reader_baseline` 在 5 个真实 run 里 **0 次**出现 |
| `outbound_post` 的链上文风闸 | `if` 条件只匹配 `outbound_reply`，帖子**从不过该闸** |

后果：`outbound_reply` 与 `outbound_post` 在**实际执行上无差别**，
所谓「回复过了 CCE」的历史含义仅等于「过了 outbound_post 那五段」，不含任何读者基线或对齐。

**照原文冻结 = 把整份重构建在一个报绿的坏基线上**，
且直接违反本文自己的铁律 21「研究工作流不得产出 production complete=true」——
同一根因的另一面：**绿灯不验证声明过的东西是否真的发生。**

### Phase 0 改为：先修地基，再冻结

**P0-a（必须先做，一行断言）**

```text
聚合闸断言 manifest.chain == 契约中该 profile 的 stages 列表，缺一即红
```

这一条同时拦住上述两个缺陷，以及「静默放行」类的第三个（本地先验对非法类型 return None 不记 error）。

**P0-b 反向测试**：故意从链里摘掉一段，断言必须让整个 job 红。不做反向测试的断言等同于没有断言。

**P0-c 然后才冻结**：

```text
cce-submit.yml
3 production profiles
current contract gates   ← 仅在 P0-a/P0-b 通过后
current population aggregation
current manifest discipline
```

### Phase 0 验收 gate

```text
① manifest.chain 断言已上线，且反向测试见红
② 重跑一个历史 run，reader_baseline 缺失被判红（当前会误判为绿）
③ outbound_post 的链上文风闸条件已修，且有一条故意违规的稿子被拦下
```

---

## Phase 1：本体重命名与 Contract 清理

完成：

```text
Population Field
Mode
Evidence Unit
Window
Partition
Context
Domain Projection
```

把概念从：

```text
Individual → Segment → Population
```

切换成：

```text
Population Field
├── Modes
└── Evidence Units
```

---

## Phase 2：Subject/Population 模块重构

保留：

```text
member distributions
weighted mixture
quantiles
JS heterogeneity
coverage
unassigned mass
uncertainty
```

新增：

```text
field structure
mode coverage
mode activation
field drift
window transition
partition projection
```

---

## Phase 3：Foundation / Multimodal

生产化：

```text
video ingest
audio ingest
image ingest
source separation
speaker diarization
prosody
mix metrics
observation
event
cross-modal event
```

---

## Phase 4：九结 Research Branch

生产算法保持冻结。

并行测试：

```text
A: 9-simplex
B: 9 independent intensity
C: drive/brake dual-family model
D: data-driven latent model
```

通过 K0-K8 后再决定是否迁移生产。

---

## Phase 5：Archive Plane

建立长期结构化归档。

禁止依赖短期 GitHub artifact 承担长期 Population / Mechanism 学习。

---

## Phase 6：Mechanism / Experiment

实现：

```text
candidate
preregister
test
replicate
reject
```

---

## Phase 7：Strategy / Generation

最后接：

```text
Population-aware strategy
Persuasion
Narrative
Multimodal Creative
Content Generation
```

---

## [MEASURED 2026-08-18] 44.9 每个 Phase 的验收 gate（原草案缺失，本轮补）

原草案有 8 个 Phase 与一张能力矩阵，但**没有任何一条写明「怎么算这个 Phase 做完了」**。
按本项目规矩，新方案必须回答验收 gate 是什么，否则 Phase 会以「感觉差不多了」结束。

**每条 gate 都必须能观察到失败**：写完立刻问「什么输入会让它红」，答不出来就是假 gate。

| Phase | 验收 gate（可自动跑） | 反向测试 |
|---|---|---|
| **0 地基** | `manifest.chain == 契约 stages` 断言上线；历史 run 重跑时 `reader_baseline` 缺失被判红 | 手动摘掉一段，job 必须红 |
| **1 本体重命名** | 旧名在生产路径上 grep 命中 = 0；契约 schema 版本号已升；旧 envelope 提交被明确拒绝而非静默接受 | 提交一份旧 schema envelope，必须报错而不是通过 |
| **2 Subject/Population** | 保留字段（member distributions / mixture / quantiles / JS / coverage / unassigned / uncertainty）逐个存在性断言；新增字段有非空样本 | 删掉 member distributions，聚合必须红而不是退化成均值 |
| **3 Multimodal** | 新增 Parser 后 **CCE Core 文件 diff = 0**（铁律 20 的可执行形式） | 故意在 Core 里改一行，CI 必须拦 |
| **4 九结 Research** | **★ K1 四项全过**（见 §23）：n≥8 · 相同读数对 ≥6/8 · 单结极差 ≤0.10 · top-1 ≥7/8 | 两份不同内容按同组提交，闸必须报「不稳定」为假、报差异为真 |
| **5 Archive** | 任一历史 run 可按 run_id 完整重建其 manifest 与 artifacts | 删一个 artifact，重建必须失败而不是静默补空 |
| **6 Mechanism** | 每条 mechanism 记录都能追到 evidence_refs，且至少一次 replication | 造一条无 evidence 的 mechanism，注册必须被拒 |
| **7 Strategy** | 生成物必须过现有三闸（outbound_guard / style_check / check_boundary），且不得引用未达标层的读数 | 喂一条引用了 K1 未达标读数的生成物，必须被拦 |

---

## [MEASURED 2026-08-18] 44.10 关于 A/B 测试的设计约束

**内容 A/B（两版内容上平台比效果）当前不可判**，这是已经算过的：
分辨 R=0.34 与 R=0.75 需约 **24,500 浏览/帖**，本序列历史最高单帖仅 16,102。
再发两版只会得到一个宽到包住一切的区间。**该路径在触达量级提升之前不应开启。**

**引擎 A/B（新旧链在同一批输入上的读数对照）是当前唯一可判的形式**，
且它的被测对象已经由 §23 K1 定死：**同稿重跑稳定性**。

设计要点：

1. **被测对象是稳定性，不是读数本身。** 不比「新链读数是否更合理」——那没有判据；
   比「新链能否在零输入变化下给出可复现的读数」——那有判据。
2. **旧链基线已冻结**（§23 K1 表格，n=8）。新链跑同一批 8 项，逐项对照。
3. **必须同时跑反向测试**：两份不同内容按同组提交，若新链判「稳定」则新链失效。
4. **不得用同一批输入既调参又验收。** 若重构中用这 8 项调过任何阈值，
   验收必须换一批新的 8 项，否则是拿自己的产物验自己。

---

## [MEASURED 2026-08-18] 44.11 三方案对抗评审结论：**全部未通过**

对 §44.10 提出的三条实现路径各做了 4 个镜头的独立对抗评审（12 条判决，评审默认立场为怀疑）。

**结果：12/12 判 `gate_is_real = false`。8 条 reject，4 条 adopt_with_changes。没有一个验收 gate 活下来。**

| 方案 | 判决 | 致命处 |
|---|---|---|
| **A** n 次采样聚合报分布 | 3 reject / 1 改后可用 | 立论跳步（见下 ①）+ gate 永不执行（②） |
| **B** 按输入指纹缓存 | 4 reject | 命中率结构性为 0（③）+ 把 K1 变成构造性必过（④） |
| **C** 跨模型共识 | 3 reject / 1 改后可用 | 先筛后测（⑤）+ n=4 时噪声大于阈值本身（⑥） |

### ① 方案 A 的立论被推翻（已实查确认，本文 §2.4.2 已据此二次更正）

A 的整个立论是「`:126` 已经是 `temperature=0.0`，所以根因不是温度，所以只能测不能修」。
实查发现 payload 里**从未发送过 `seed`**。**根因未查清就宣布不可修。**

### ② ★ 结构性陷阱：新增测试文件在 CI 里永不执行

`.github/workflows/cce-submit.yml` 的 contract 作业是**硬编码的 8 行测试命令清单**；
`tests/test_cce_*` 只是 **PR 触发路径过滤**，不是执行清单。

**三个方案都新增了测试文件，都没改那 8 行 ⇒ 三个 gate 全是永久绿。**

（实查：当前 `tests/` 下 8 个文件 8 个都在清单里，暂无孤儿测试。但这是潜伏陷阱 ——
**任何新增测试文件若不同时改那 8 行，就是一个从不运行的闸。**）

→ **凡新增 gate，必须同时在该清单里增行，并给出「删掉这一行则 CI 变绿」的反向证明。**

### ③ 方案 B 的命中率结构性为 0

缓存目录落在 runner workspace，而 outbound 作业是 `max-parallel: 8` 的矩阵，
每个 job 是独立 ephemeral VM + 全新 checkout。**跨 job、跨 run 都不共享，命中率恒为 0。**

### ④ 方案 B 会把可靠性 gate 变成构造性必过

K1 判据是「同项重跑 n≥8，完全相同读数对 ≥6/8」。缓存默认读写时，同项重跑**必然 8/8 相同、极差 0.00**，
K1 显示满分通过，而仪器一点没修。唯一防线是文档里一句「复测须关缓存」，**代码零强制**。

本项目已证明散文 caveat 挡不住引用：13 条 s2_knots 读数每条都标了「不可单独使用」，
仍被当读数写进了台账。

### ⑤ 方案 C 的「先筛后测」

C 先把不一致的结剔进 `unresolved`，验收闸再去量 `agreed` 的权重极差
—— **被验收的集合是被验对象自己筛出来的**。

而触发本次重构的那个失败形态（`pain_seek` 四次里 0.65 / 0.50 / 0.40 / 完全缺席）
在「两侧多数出现」这一条上本身就是抛硬币，**会被自动移出被测集合**。
**这个 gate 结构上看不见它要测的那个缺陷。**

另有恒绿极端态：两模型持续分歧时每次 `agreed=[]`，跨 run 极差恒 0，稳定性判据全绿
—— **「稳定地拒答」通过了一个稳定性闸。**

### ⑥ 方案 C 在 n=4 时数学上不成立

用 C 自己引的数：`pain_seek` 0.65 / 0.50 / 0.40 / 缺席(0) → SD = 0.278。
n=4 时均值 SE = 0.139，跨模型 gap 的 SE = √2 × 0.139 = **0.197 > δ = 0.15**。

**被卡阈的那个量，其自身抽样噪声大于阈值本身 —— 边界结上的判定不如抛硬币。**
要把 SE(gap) 压到 δ/2 需 **n ≈ 28 / 模型**。

> 评审同时给出的「私有仓 Actions 只剩约 199 分钟」这条**不适用** ——
> 当前生产入口在**公开仓** `luogangan7-lgtm/cce-engine-oss`，Actions 分钟不计费。
> 该条属评审引用了过期记忆，本文不采纳。但 ⑥ 的数学论据与配额无关，仍然成立。

### 由此得出的下一步（本文对 §44 Phase 0 的补充）

**P0-0（先于 P0-a）：seed 探针。** 成本近乎为零，且它的结果决定后面三个方案还需不需要做。

```text
动作：给 call_model 的 payload 加 seed，同项跑 n=8
判据：抖动是否消失
  · 消失      → 三个方案全部不需要，问题是「没设 seed」
  · 部分消失  → 量出残余，再谈用哪个方案覆盖残余
  · 不消失    → 说明端点忽略 seed，此时方案 A 才是正确路径
反向测试：故意传两个不同 seed，读数必须不同（否则说明 seed 根本没被发送）
```

### [MEASURED 2026-08-18] P0-0 探针已执行，结论如下

**取数动作**：`probes/seed_probe.py`，直接打模型端点（不走 CCE 链），同一 prompt，
形状对齐真实任务（短文本 → 三维带权 JSON）。

#### 结果一：端点**接受** `seed`，但**不实现**它

| 组 | 配置 | 不同输出 |
|---|---|---|
| D | MiniMax `temperature=0.0`，无 seed | **6 / 6** |
| A | MiniMax `temperature=0.6`，无 seed | 5 / 6 |
| B | MiniMax `temperature=0.6`，**`seed=42`** | **6 / 6** |
| C | MiniMax `temperature=0.6`，`seed=999` | 4 / 4 |

请求返回 HTTP 200、`base_resp.status_code=0` —— 参数被接受，**行为无变化**。

→ **「加 seed 让调用可复现」这条路走不通。不是没试，是试了不行。**
→ §44.11 ① 对方案 A 立论的质疑（「根因未查就宣布不可修」）**已查，结论是确实不可修**。

#### 结果二：★ `temperature=0.0` 本身就不产生确定性

D 组 6/6 全不同，逐维极差 0.20 / 0.20 / 0.15。

**这修正了本文 §2.4.2 的一处措辞**：此前写「s2 的不可复现有一部分是从 s1 继承的」。
实测表明 **s2 自己那次 `temperature=0.0` 的调用就在抖**，不需要从 s1 继承任何东西。
s1 的温度阶梯是**叠加**在这之上的第二个噪声源，不是唯一来源。

#### 结果三：换仪器能降约一半抖动，但不能消除

同温 0.0、同 prompt、无 seed、n=6 的干净对照：

| 端点 | 不同输出 | regret 极差 | curiosity 极差 | resolve 极差 |
|---|---|---|---|---|
| MiniMax-M3 | **6 / 6** | 0.20 | 0.20 | 0.15 |
| Qwen3.8-max（阿里云） | **3 / 6** | 0.15 | 0.15 | **0.00** |

Qwen 有两对重复、且 `resolve` 维完全稳定。**但两者都不是确定性的。**

> 附注：所有取值 100% 落在 0.05 网格上（两个端点、四组、共 66 个数）。
> 这与 §21 观察一致，且现在有了跨端点证据 —— **0.05 网格是模型输出习惯，不是本仓代码造成的量化**。

#### 由此确定的下一步

```text
✅ 已排除：加 seed          —— 端点不实现
✅ 已排除：调 temperature   —— 0.0 本身就不确定
⚠️ 部分可用：换端点          —— 抖动减半，不归零，且换仪器需重标定全部基线
★ 剩下唯一诚实的方向：承认不确定性，n 次采样，报分布而不是报点值
```

**即 §44.10 的方案 A 方向成立**，但它的验收 gate 必须重做 ——
§44.11 ② 指出的「新增测试文件在 CI 里永不执行」是致命的，
**任何新 gate 必须同时在 `cce-submit.yml` 的 8 行硬编码测试清单里增行，
并给出「删掉这一行 CI 就变绿」的反向证明。**

---

## [MEASURED 2026-08-18] 44.12 重构已上生产：Phase 0 + n 次抽样聚合

公开仓（生产入口）HEAD `5a20d29eb23d`。改前 6 个文件备份于 `archive/cce-oss-pre-refactor-20260818/`。
用户决策为直接改生产而非开分支，原话：**「本来就是错的，继续用生产跑还是错的」**。

### 已上线（每一项都附实测，不是声称）

| 改动 | 验证 |
|---|---|
| `reader_baseline` 补上实现 | 生产 run `32099546100`：chain 6 段、该段 OK、产出 `reader_baseline.json` |
| `manifest.chain == 契约 stages` 断言 | 反向测试：契约链绿／摘一段红／乱序红。**并拿今天早些时候的真实历史 artifact 重判 → 由绿转红** |
| outbound_post 接上链上文风闸 | 核过 post8 正文 rc=0，不拦既有稿件 |
| 补 outbound_reply 孪生静态断言 | 此前只钉 outbound_post，缺口持续数周 |
| **s2_knots 单次抽样 → n=5 抽样聚合** | 生产 run `32100394222`，见下 |

### ★ n 次抽样聚合的设计要点

- 逐结报 `occur/n` · 中位数 · `min/max/range`
- **缺席记 0，分母恒为成功抽样数而非出现次数** ——
  取 `occur` 作分母会让只出现 1 次的噪声结显示成满分稳定
- `knots` 保持既有形状（weight 改为中位数），实测下游 5 个消费者无需改动
- ~~**刻意不设权重阈值**~~ ⚠️ **这句是假的，见下**
- `top1_stable=false` 时 **`playbook_primary` 置 None** ——
  它是整条链里唯一直接指挥「怎么写」的字段，不确定性必须在这里生效。

> ### ⚠️⚠️ [MEASURED 2026-08-18 二次更正] 本小节原文有两处硬错误
>
> **错误一：「刻意不设权重阈值」是假的。**
> 聚合里 `median(缺席记 0) > 0` 等价于一个**没有写下来的硬阈值 `occur > n/2`**，
> 它藏在中位数算术里，因而无法被质疑或校准。
> 顺带造成两个数值缺陷：`occur=3/5` 系统性低估约 25%（蒙特卡洛 20 万次：真 0.500 → 报 0.374）；
> **偶数 n 上 `occur=n/2` 报真值的一半**（n=4/6/8 实测 0.40 → 0.20）。
> → 已改为显式常量 `SUPPORT_RULE = "occur * 2 > n"`，并把强度与出现率拆成
>   `intensity`（出现时的中位数）× `support`（出现率）两维。
> → **教训：声称「没有阈值」之前，先找一遍藏在算术里的那个。**
>
> **错误二：`top1_stable` 这个判据本身是 n 依赖的，不能跨 n 比较。**
> `len(set(tops)) == 1` 在 **n=1 时恒为真** ⇒ 扣发闸在单抽下**永不触发**；
> 且 `P(全体一致) ≈ p^n` 随 n 单调下降是**构造性**的
> （p=0.8 时：n=1 → 1.00 · n=2 → 0.64 · n=5 → 0.33 · n=8 → 0.17）。
>
> **所以「把 n 从 1 提到 5 之后 top-1 一致率变差」在数学上是必然的，不是发现。**
> 闸的严格度成了旋钮，不是测量。而 “stable” 这个词还把**样本的性质**说成了**世界的性质**。
> → 主量已改为**众数占比** `top1_mode_share`（跨 n 可比），
>   二元字段改名 `top1_unanimous`，并在 `sampling` 里带上「不可跨 n 比较」的告诫。
>
> 两处都由对抗评审（workflow `wgd3n1wrv`，9 agent）指出后实测确认。

### 生产首跑即触发（比任何测试都有说服力）

```text
top1_draws  = ['audit', 'audit', 'display', 'display', 'audit']
top1_stable = False   →  playbook 扣发
knots(中位) = audit 0.42 / display 0.40 / reward 0.20
逐结极差    = audit 0.30 · display 0.35 · reward 0.15
噪声结      = belong 1/5 · pain_seek 1/5   ← 此前会被当成真实的结记下来
```

**首结之差 0.02，而各自极差 0.30–0.35。** 旧系统会挑一个当首结、把它的 playbook 当指导发出去。

### ⚠️ 必须同时记下的观察：稳定性判断本身也不稳

同一份稿子，**本地跑得 `top1_stable=True`（display 5/5），生产跑得 `False`（3:2 翻转）**。
即 n=5 时 `top1_stable` 自身带抽样噪声。

→ 它是**「判 false 时确实不稳」**的信号，**不是「判 true 就稳」的证明**。
→ **不得据一次 `top1_stable=true` 声称该稿读数可靠。** 那个结论需要更大的 n，n 待定，不拍。

### 闸的可信度：变异测试 4/4 全红

`tests/test_cce_knot_stability.py` 离线跑、不需 API key、含 4 项反向测试。
故意改坏聚合逻辑的四种方式全部被抓到：分母改 `occur` ／ `top1_stable` 恒真 ／
全失败静默返回空 ／ 中位数换最大值。

### ★ 并且它被加进了 `cce-submit.yml` 的**硬编码**测试命令清单

这是 §44.11 ② 那条致命处的处置。该测试第 5 节**自己断言自己在清单里** ——
它自己防它自己变成一个从不运行的永久绿闸。

---

## [MEASURED 2026-08-18] 44.13 第二批：噪声底接闸 + 口径分离

公开仓 HEAD `6c650ea54194`。验证 run `32111177990`。

这两件是 §2.4.3 与 §2.4.4 里**本文档自己点过名、第一批却没做**的。
遗漏根因值得记：它们是写 §2.4 节点图时新发现的，不属于 §44 任何一个 Phase 编号，
于是**掉在两个结构之间** —— 写进文档就当处理过了。与本项目既有教训同形：
**结论写进记录 ≠ 结论进了执行队列。**

### ① `within_js` 接上闸（零新增 LLM 调用）

它是仪器的自测噪声底（K 次采样两两 JS 散度），一直在算、一直写进 manifest，
**此前没有任何 gate 使用它**；唯一动作是阈值 0.25 的 flag，实测 31 条只触发 2 次。

阈值改为**逐层从实测标定**（中位数 + 2×MAD，n=31）：

| 层 | 实测中位 | 新阈值 | 标定集内触发 |
|---|---|---|---|
| `desire_vec` | 0.076 | **0.120** | 6/31 |
| `need_vec` | 0.108 | **0.161** | 7/31 |
| `emotion_vec` | 0.108 | **0.157** | 2/31 |
| `action_vec` | 0.088 | **0.125** | 2/31 |

> ⚠️ **这组阈值在这 31 条上标定，首次样本外检验就是它上线后的每一次生产运行。**
> 不得用同一批数据既标定又验收。若样本外触发率与 6/7/2/2 显著不同，以样本外为准重标。

**动作不是让 build 红，是扣发该层的 `top` 标签** —— 与 s2 扣发 playbook 同一逻辑：
内部离散超过自身噪声底的层，它的 top 是在读噪声。
与既有纪律同源（差距落在噪声内的层禁止排名 / 情绪层禁单 top / 禁 argmax）。

并且 `within_js` 缺失（`k_ok < 2`）从「静默缺省」改为**抛错** ——
没有噪声读数就没有可信度判断，此时放行等于回到改前状态。

### ② stage1 返回体的口径分离（§2.4.3 的处置）

新增 `single_draw{}` 与 `_provenance{}`，把 `appraisal` / `chain_trace`（单抽，温度阶梯第一档）
与 `layers` / `tops`（K 次聚合）显式分组，单抽项带 caveat「不得与聚合项并列引用」。
顶层同名键保留，下游不需改。

### 生产首跑两个闸同时触发

```text
s1  desire_vec = 0.1788 > 0.120   →  tops.desire 扣发
    need / emotion / action 未超  →  top 保留
s2  top1_draws = [reward, display, display, display, display]  →  playbook 扣发
```

**一次运行里两个不可靠读数各自被扣住，其余照常发。** 这是「不确定性在做决策的地方生效」的形态，
而不是把它写在 manifest 里没人看。

### 闸的可信度

`tests/test_cce_within_js_gate.py`：离线跑、不需 API key，含逐层阈值判定、扣发 top、
边界（`>` 而非 `>=`）、缺失即红、CI 自防断言。
**变异测试 4 个全红**：阈值调 1.0 ／ 不扣发 ／ 缺失静默放行 ／ 退化成通用 0.25。
已加进 `cce-submit.yml` 的硬编码测试清单。**10/10 测试通过。**

---

## [MEASURED 2026-08-18] 44.14 温度阶梯的受控对照：R=3 下不可判，且我此前的定性说错了

`probes/ladder_probe.py`。问题：s1 的温度阶梯 `[0.0, 0.3, 0.6, 0.9, 0.15]`
相对「同温重复采样」，多给了什么？

- 臂 A：当前阶梯，K=5
- 臂 B：全部 `temperature=0.0`，K=5
- 各重复 R=3，同一份文本、同一 context

### 结果：四层全部落在噪声内，不可判

| 层 | A 阶梯均值 | B 同温均值 | 差 (A−B) | 合并 SD | **差/SD** |
|---|---|---|---|---|---|
| `desire_vec` | 0.1155 | 0.0881 | +0.0274 | 0.0292 | **0.94** |
| `need_vec` | 0.0997 | 0.0762 | +0.0234 | 0.0432 | **0.54** |
| `emotion_vec` | 0.0797 | 0.0933 | **−0.0135** | 0.0313 | **0.43** |
| `action_vec` | 0.0656 | 0.0729 | **−0.0074** | 0.0083 | **0.89** |

**差/SD 全部小于 1**，即 A−B 的差比同臂重复之间的波动还小。
**且两层显示阶梯更大、两层显示阶梯更小 —— 方向不一致本身就是噪声的特征。**

这正是本项目自己那条纪律的又一次应用：**差距落在噪声内的层禁止排名。**
（这次被禁止排名的是我自己的实验。）

要在 80% 功效下分辨这个量级的差，每臂需要 **R ≈ 19（desire）到 86（emotion）**。

### [MEASURED] R=20 复测：阶梯没有可测的增量

| 层 | A 阶梯 | B 同温 | 差 | Welch p | R=20 可分辨的最小差 | 观测差/可分辨 |
|---|---|---|---|---|---|---|
| `desire_vec` | 0.0916 | 0.0952 | **−0.0037** | 0.592 | 0.0136 | 0.27 |
| `need_vec` | 0.0982 | 0.0981 | **+0.0001** | **0.992** | 0.0198 | 0.00 |
| `emotion_vec` | 0.1021 | 0.0935 | +0.0086 | 0.217 | 0.0138 | 0.62 |
| `action_vec` | 0.0711 | 0.0651 | +0.0060 | 0.424 | 0.0149 | 0.40 |

**R=3 时 desire 的差是 +0.0274、need 是 +0.0234；R=20 时塌成 −0.0037 和 +0.0001。**
这正是「那些差本来就是噪声」的特征 —— 加大 n 时真实效应会收敛到某个非零值，噪声会收敛到 0。

`desire` 层在 R=3 时算出需要 R≈19，实跑 R=20，**功效达标而 p=0.592**。
四层的观测差全部小于本 R 能分辨的最小差。

> **结论：温度阶梯相对同温重复采样，没有可测的增量。**
> 它是一个买不到东西的不受控变量。拿掉它可简化仪器且不损失可测信息 ——
> 但**这不是「消除噪声」**，端点固有的不可复现仍在（P0-0 已证 `temperature=0.0` 本身就不确定）。
>
> ⚠️ 本结论限于**一份文本、一个端点、within_js 这一个指标**。
> 阶梯若在别的用途上（如故意制造语义多样性以覆盖歧义）有价值，本实验测不到那一面。

### ★ 顺带更正一处我此前的定性说法

我在 §44.13 收尾时说「s1 的温度阶梯是现在最大的未拆噪声源」。**这句不准。**

P0-0 已证 `temperature=0.0` 本身就不产生确定性；本对照又显示阶梯相对同温多出的量
在 R=3 下测不出来。所以更准确的分解是：

```text
端点固有的不可复现   ← 主噪声源, 已证存在, 且加 seed 无效
    ↑ 叠加
温度阶梯带来的展开   ← 量级未知, R=3 下与 0 不可区分
```

**即使把阶梯拿掉，s1 也不会变确定。** 拿掉它的收益是「少一个不受控变量」，
不是「消除噪声」。这个区别足以改变它的优先级 —— 它不是最大的那块。

---

## [MEASURED 2026-08-18] 44.15 §22 四层结构已上生产

公开仓 HEAD `7a3e9464cfbf` · 验证 run `32113950638`。

### 生产实跑给出的正是 §22.2 预言的形态

```text
第 2 层 intensity   display 0.88 · audit 0.80 · reward 0.55    总和 2.23  ← 不再是 1
第 3 层 推动族 mass 0.88  组成 {display .615, reward .385}     (和 = 1.0)
        阻挡族 mass 0.80  组成 {audit 1.0}                      (和 = 1.0)
第 4 层 high_drive / high_brake
兼容层  weight  display .395 · audit .359 · reward .247        (和 = 1.0)
```

§22.2 原文举例「允许 `reward = 0.88` 与 `audit = 0.81` 同时成立」。
实测给的是 `display 0.88` 与 `audit 0.80` —— **「想要很强」与「审查也很强」现在能同时表达。**

**同一份稿子在旧单层 simplex 下是** `audit 0.42 / display 0.40 / reward 0.20` ——
三者被迫分一个固定预算，两个都很强的结只能互相压低。这就是 §21 说的 compositional data 的后果。

### mass 的定义（§22 未钉死，本实现的选择与理由）

取**族内最大强度**：
- §22.2 举例的个体强度接近 1，若 mass 取和会 >1 而失去「强度」量纲
- 取最大值使 mass 与 intensity 同量纲，可直接用于 §22.4 的四象限
- composition 与 mass 正交：前者是**形状**，后者是**水平**

四象限切点 0.5 在代码里明确标注为「量纲中点，不是校准阈值，仅作分类标签，不得作判据」。

### 兼容

`knots` 每项仍带 `weight`（= 全局组成，和为 1），下游 5 个消费者的 `{key: weight}` 读法不破；
同时新增 `intensity`。抽样层兼容模型偶尔仍吐 `weight` 的情况。

### ★★ 两个方法学修正，都由验证过程自身暴露

**① 变异测试找出了测试用例的覆盖盲区。**
「mass 改成族内求和」最初**没被抓到** —— 原用例每族只有 1 个活跃结，`max` 与 `sum` 相等。
补同族多结用例（推动 3 结 / 阻挡 2 结）后才分得开。
→ 变异测试的价值不只在验证被测代码，**也在暴露测试自身的盲区**。

**② ★ 变异测试 harness 自身一度不可信。**
循环在同一秒内反复重写源文件，而 **Python 的 `.pyc` 失效判据是 (mtime, size)，不是内容哈希**。
恢复后的干净文件与某个变异版本同秒同尺寸 → 解释器**继续执行变异版字节码**。

表现为「恢复后测试仍红」，且红的症状正是**上一个变异**的症状（`mass` 取最小），
而源码里明明写着 `max`。

→ **那一批变异结果全部作废。** 某些「✅ 变红」可能是上一个变异的字节码在红。
   这本身就是一种假检查：读数与被测对象无关。
→ **写死的纪律**：任何反复改写源文件的验证脚本必须设 `PYTHONDONTWRITEBYTECODE=1`
   并每次清 `__pycache__`；且**必须先验基线为绿**，基线不绿则全部结果作废。
→ 在该条件下重跑：**14 个变异（10 knot_stability + 4 within_js）14/14 全部被抓到**，基线绿。

---

## [MEASURED 2026-08-18] 44.16 冻结 s1 因子实验：n 扫描单调改善，推翻 §44.15 之后那组 A/B

`probes/frozen_s1.py` · 2 prompt × 2 冻结 s1 区组 × 20 draw = **78 个可用原始 draw**。
只调 `_stage2_draw`，**绝不调 `_stage2_aggregate`** —— 原始 draw 未聚合未归一落盘。
三条判决线**在跑之前写死在脚本里**。

### ★ 核心结果：提高 n 单调改善两个指标，两个 prompt 都是

| prompt | n=1 | n=2 | n=4 | n=5 | n=10 |
|---|---|---|---|---|---|
| NEW 众数占比 ↑ | 0.615 | 0.735 | 0.843 | 0.906 | **0.962** |
| OLD 众数占比 ↑ | 0.513 | 0.701 | 0.702 | 0.679 | 0.805 |
| NEW 首结极差 ↓ | 0.160 | 0.192 | 0.125 | 0.100 | **0.052** |
| OLD 首结极差 ↓ | 0.500 | 0.327 | 0.214 | 0.195 | 0.100 |

**这直接推翻此前那组 A/B 得出的「n=5 比 n=1 差」。** 那组用了两个坏判据：

1. `top1_unanimous` 在 **n=1 时恒真**（`P ≈ p^n`，提 n 必然变差 —— 是算术不是现象）
2. 单结极差的**归一分母跨臂不同**（OLD 每 rep 4–6 结 vs NEW 恒 3 结）

换成**跨 n 可比的众数占比**、且**在同一 prompt 内切分**之后，结论反过来：**重构是有效的。**

### 三条预注册判决线**全部没有干净触发** —— 原样报告，不事后改线

| 线 | 判据 | 实测 | 结果 |
|---|---|---|---|
| 1 | 新 prompt 均差 < 旧的一半（比值 < 0.5） | **0.563** | ❌ 差一点 |
| 2 | 两者相当 | Welch **p = 0.0006** | ❌ 高度显著 |
| 3 | 区组效应 > prompt 效应 | 0.0786 vs 0.0944 | ❌ |

> **我的判决线是为一个比现实更干净的世界写的。**
> 这本身是教训：预注册判据必须覆盖「落在两条线之间」的情形，
> 否则真值出来时唯一的选择就是事后改线 —— 而那正是预注册要防的。

### 我那句「NEW 更诚实」：一半对一半错

- **对的一半**：OLD 单抽 top1 众数占比只有 **0.513**（三选一的随机基线 0.333）——
  **OLD 本身就离稳定很远**，「三结近平局」不是 NEW 造出来的。
- **错的一半**：NEW 把 draw 内 top1−top2 均差从 0.2205 压到 **0.1241（−44%，p=0.0006）**。
  **这部分压缩确实是 prompt 造的，我原来没承认。**
  新 prompt 里那个 `reward=0.85 且 audit=0.80` 的例子，在暗示模型「多个结都可以很高」。

### 交互很强，两因子不可加

prompt 效应在 B0 只有 0.0406，在 B1 有 0.1482（**3.6×**）——
**prompt 的影响本身取决于 s1 抽到哪一份。**

两个冻结 s1 区组的四层 tops 有**两层完全不同**
（`curiosity好奇`/`attend关注` vs `pride自豪`/`dominate支配`），
且 B1 的 `desire`/`need` 的 `within_js`（0.2145 / 0.2475）**双双超过已标定的噪声底阈值**。

### 净结论

1. **n=5 聚合有效，保留。** n=10 更好（众数占比 0.962、极差 0.052），成本翻倍，待定。
2. **NEW prompt 在稳定性上也更好**（每个 n 上众数占比更高、极差更小），**同时**压缩了结间差距。
   两件事不矛盾：**独立打分比分配固定预算更受约束**，故每结更可复现、而结间更接近。
3. **s1 仍是大头**且与 prompt 强交互 —— 下一步该动的是它，不是继续调 stage2。

---

# 45. 当前“已具备 / 缺失”矩阵

## 已具备或接近具备

```text
GitHub production control plane
submission contract
workflow registry / capability registry
stimulus / response measurement
population aggregation
member distributions
JS heterogeneity
coverage
evidence-bound response chain
window audit
manifest / artifact verification
```

---

## 部分具备

```text
video parse
OCR
raw mix audio extraction
speech recognition
foundation adapter
atomic/composite event assemble
```

---

## 当前缺失或未生产化

```text
production media ingest
standalone image ingest
standalone audio ingest
audio source separation
speaker diarization
prosody
mix metrics
full cross-modal event semantics
population repeated-window learning
persistent archive pipeline
mechanism registry
experiment workflow
strategy generation loop
```

---

## 研究未定

```text
九结真实潜在结构
9-simplex 是否合理
drive/brake 分组是否成立
transition post-state estimator
cross-region measurement validity
cross-platform mechanism transfer
causal attribution
```

---

# 46. 外部研究与标准依据

本文不照搬外部标准，但借鉴以下思想：

1. **W3C Web Annotation Data Model**  
   支持把标注绑定到具体资源及 timed multimedia 的片段，适合 Observation / Evidence Target 设计。

2. **W3C PROV-O**  
   提供 Entity / Activity / Agent 等 provenance 思想，适合 CCE Evidence Graph。

3. **Aitchison, 1982, The Statistical Analysis of Compositional Data**  
   说明固定总和的 compositional data 位于 simplex 中，必须谨慎解释分量与相关结构。九结若强制总和为 1，就必须承认其是相对构成而非绝对强度。

4. **Categories and Dimensions: Advancing Psychological Science Through the Study of Latent Structure**  
   强调潜在结构到底是类别还是连续维度应由数据检验，而不是预先假定。适用于九结 K4 审计。

5. **Construct Validity: Advances in Theory and Methodology**  
   强调心理构念验证需要把理论、测量与外部可观察关系一起验证，且应避免用一个单分数压缩多维构念。

6. **Measurement Invariance literature**  
   对跨语言、跨地域、跨平台比较有启发：同一个量表/构念在不同群体与时间下是否具有可比意义，需要单独验证，不能默认。

7. **GitHub Actions artifact retention**  
   GitHub 官方文档说明 artifact/log 默认保留期通常为 90 天；因此不能把 GitHub Artifact 当长期 Population / Mechanism 学习的唯一数据库。

---

# 47. 最终冻结建议

当前阶段建议冻结以下结论：

```text
1. Broadcast CCE = Population-first
2. Population Field 是平台传播的一等主体对象
3. Individual 是 Evidence Unit，不是默认 Target Unit
4. Mode 是 Field 的结构，不是固定 Persona
5. Window 表示 Target/Reached/Action/Conversion 等条件阶段
6. Geography 是 Partition + Context，不是主体类型
7. Platform / Surface 属于 Context
8. Domain 通过 Projection 挂载，不污染 Universal Core
9. CCE Core 只做 Measurement
10. Distribution / Behavior / Outcome 独立记账
11. Mechanism 必须经过 Evidence → Hypothesis → Test → Replication
12. 九结保留为 candidate ontology，但计算结构进入 research audit
13. 生产链暂不直接切换九结算法
14. 第一阶段不需要向量数据库
15. 长期学习必须补 Archive Plane
```

---

# 48. 最简总图

```text
              POPULATION FIELD
                     ↓
                  CONTEXT
                     ↓
                  STIMULUS
                     ↓
            MULTIMODAL PARSING
                     ↓
                OBSERVATION
                     ↓
                   EVENT
                     ↓
               CCE MEASURE
                     ↓
          POPULATION RESPONSE FIELD
                     ↓
               DISTRIBUTION
                     ↓
              REAL BEHAVIOR
                     ↓
                 OUTCOME
                     ↓
                EVIDENCE
                     ↓
          POPULATION FIELD UPDATE
                     ↓
             MECHANISM LEARNING
                     ↓
                STRATEGY
                     ↓
               NEW CONTENT
                     ↺
```

---

# 49. 一句话定义

> **CCE 是一个以 Population Field 为平台传播主对象、以 Evidence 为事实基础、以多模态 Event 为输入结构、以动态测量为核心、以真实 Distribution / Behavior / Outcome 为验证源，并通过重复证据形成可检验机制与新内容策略的人群主体性测量—传播—学习系统。**

## 19.5.7 [MEASURED 2026-08-18] 仪器边界扩到 s1（★ 标题原为「天花板已打掉」，当晚校准对照后撤回，见本节末）

验证 run `32127691127`。

### 改了什么

此前 s2 的 prompt 由「s1 聚合 `tops` + `pvs[0]` 的 `appraisal`」拼成**一份固定 prompt**，
一个 rep 内 n 次 s2 抽样**共享同一份抖过的 prompt**
⇒ **s2 的聚合器在数学上碰不到 rep 间方差，无论 n 多大。**

改为：`stage1` 逐 draw 暴露 `{from_temperature, tops, appraisal}`（各 draw 用自己的向量算 top），
`stage2` 为每份 s1 draw 生成一份 prompt，n 次 s2 抽样 **round-robin 取用**。
**成本不变，不新增任何模型调用。**

### ★ 结果：测得的不确定性**变大了** —— 这正是修对了的样子

```text
instrument_hash  3170a226dec8726b  →  57ec6cf478d3875e
s1_pairing       round_robin_over_3_s1_draws
s2               n=5 · mode_share 0.6 · max_range 0.48
qualified        usable 3 / withheld 3
                 s1.tops.desire  within_js 0.164 > 0.12
                 s1.tops.need    within_js 0.166 > 0.161
                 s2.playbook_primary  top1 不稳
```

**改动前的低极差是「把 s1 噪声冻住」换来的假象**，不是仪器更稳。
现在 s1 的方差真正进入 s2 的聚合，仪器开始报出它**本来就有**的那部分不确定性。

> **⚠️ 且本文档不给出「0.48 vs 改前 0.1–0.35」这种对比** ——
> 那些 run 的 `instrument_hash` 是 `3170a226…`，与本次不是同一把尺子，
> **本文档自己刚立的 `assert_same_instrument` 会拒绝这个比较。**
> 要量出改动前后的差，必须在同一实验里把 `s1_pairing` 当因子跑，尚未做。
>
> 这条限制值得单独记：**instrument_hash 上线的第一个效果，
> 就是拦住了作者自己想做的一次不当比较。**

### ⚠️⚠️ [MEASURED 2026-08-18 当晚] 校准对照：**本次改动没有改善任何可测的东西**

`probes/pairing_calibration.py` · 同一份文本 · `s1_pairing` 作为因子 · 每臂 R=6 · 96 次调用。
判决线**跑前写死**。判据刻意不用「谁的极差小」（那会直接奖励低报），用**校准比**：

```text
校准比 = 仪器在单个 rep 内报出的不确定性 ÷ rep 之间实际的变动
≈1 校准好 · ≪1 低报 · ≫1 过报
```

| 臂 | 报告不确定性 | 实际 rep 间变动 | 校准比 |
|---|---|---|---|
| NEW round-robin | 0.5317 | **0.33** | **1.61** |
| OLD single-prompt | 0.4383 | **0.33**（核心结口径） | **1.33** |

> OLD 未 restrict 时头条是 0.40，来自 `suspend` —— **稀有结的「极差」是它偶尔出现时的值，
> 不是稳定性**。这与本文档此前记过的同一个坑同形，本次自查发现并已 restrict 到两臂共有的核心结。

### 三条判决线逐条读

| 线 | 判据 | 实测 | 结果 |
|---|---|---|---|
| 1 | OLD ≪ 1（低报）→ 改动是对的 | OLD **1.33**，不低报 | ❌ **我预测的方向错了** |
| 2 | 两臂相当 → 改动只把数字变大了 | 1.33 vs 1.61 | 接近但不等 |
| 3 | NEW ≫ 1（过报） | NEW **1.61**，两臂皆过报 | 最接近成立 |

### ★ 最要命的一条不在判决线里

round-robin 的**全部理由**是「s1 的方差被冻死在 prompt 里，s2 聚合碰不到 rep 间方差」。

**而实测 rep 间变动 0.33 → 0.33，一点没动。**

要么 s1 的贡献本来就小，要么 round-robin 并没真的把它传播进去。
**两种情况下，§19.5.7 开头那句「天花板已打掉」都不成立，现予撤回。**

这同时是对 §44.16 「s1 仍是大头」那条推论的**反证**，一并登记。

### 处置

- **代码保留**：成本不变（零新增调用），且「不冻结一个已知噪声源」在原则上更干净。
- **但撤回一切「它改善了稳定性 / 打掉了天花板」的说法** —— 没有数支撑。
  当前 `s1_pairing=round_robin` 的地位是**结构性选择，不是经过验证的改进**。
- **R=6 很薄**，`max` 又是噪声大的统计量。若要判定，需要更大的 R 与逐结（而非 max）的判据。

### ★ 第三次同一个自伤：探针丢掉了回答自己问题所需的字段

`reported` 端同样需要按「两臂共有的核心结」重算（OLD 每 rep 4–5 结、NEW 恒 3 结，
不 restrict 就是拿不同分母比），**而本探针初版只落了聚合值、没落逐 rep 逐结明细**。

前两次：`probes/ab_knot_n.py` 丢 `sampling`（由对抗评审指出）；本次自查发现。
**已修：`per_knot` 落盘 + 判据自动 restrict 到共有核心结。**

> **通则（第三次了，写进纪律）：探针必须落下它自己判据所需的全部原始字段 ——
> 聚合值不够。写探针时先问「如果结论被质疑，我要拿什么重算」。**

---

### 配对策略进哈希

`sampling_policy.s1_pairing` 参与 `instrument_hash`。改了配对就是换了仪器，
新旧读数不会被静默当成同一把尺子。legacy 路径如实标注 `single_s1_aggregate(legacy)`，
**不伪装成已修**（有反向测试钉死）。

### 变异测试又找出一处测试自身的盲区

「`stage1` 不再暴露逐 draw」最初跑不红 —— 因为测试是**手工构造** `draws` 喂给 `stage2` 的，
**从没断言 `stage1` 会产出它**。已补。本轮变异 8 个全中。

---

## 19.5.8 [PREREG 2026-08-18 · 结果待填] ★ P1 的 Reliability 项**没有做完**，所以 P2 不能开始

评审给的次序原话是：先修 Measurement → **确认 Reliability** → 收集大量真实 Observation → 再研究 Knot latent structure。

§19.5 做完了 Measurement 的四件：仪器身份（`instrument_hash`）· 重复测量（`KNOT_N`）·
噪声底（`within_js` 闸）· 出口闸（`qualified_readout`）。
**但「确认 Reliability」一项没做**，而且此前没意识到它没做。

### 缺口：现有的闸全是「单次运行内部」的散布

| 闸 | 量的是什么之间的散布 | 层级 |
|---|---|---|
| `within_js` | s1 各温度 draw 之间 | **单次运行内** |
| `top1_mode_share` / `max_range` | n 次 s2 抽样之间 | **单次运行内** |
| **（不存在）** | **同一份文本两次独立跑之间** | **跨运行 — 从未被测，也没有闸** |

而用户真正关心的是跨运行那一格：**同一份文本明天再跑一次，还是不是这个答案。**

§19.5.7 的校准对照第一次量到了这个数：**核心结 rep 间变动 0.33**。
0.33 大不大，取决于**两份不同文本之间的差**有多大 —— 而那个数从来没人算过。

### 判据：可分辨性 D

```text
D = 文本间变动 (信号) ÷ 重跑间变动 (噪声)
```

**如果仪器区分不了真实语料里不同的文本、差距还没它自己重跑的抖动大，
那么 §22 的四层结构、九结分布、下游一切分析全部是噪声。**

`probes/discriminability.py` · 3 份真实语料 × R=4 × 8 调用 = 96 次。

**选文本的规则也写死**（防我自己挑对结论有利的样本）：
`run_items/reddit_20260810.json` 的唯一 `reader` 文本按**长度升序**取 index 0 / 中位 / 末，
**不按内容挑，不预读结点**。挑「明显不同」的极端对是另一个实验（见分支）。

**核心结口径**：只用在**每一个（文本, rep）格子**里都出现的结。
不用并集补零 —— 那正是 §19.5 记过的隐藏阈值坑（缺席记 0 会把极差灌成假信号）。
结集本身因文本而异也是分辨力，但没算进 D，**所以 D 是下界**。

### ★ 判决线（跑之前写死，不许事后挑）

| # | 判据 | 处置 |
|---|---|---|
| 1 | **D ≤ 1** | 仪器分辨不出真实语料。**下游全是噪声，P2 之前必须停**，并跑极端对照区分「仪器盲」与「语料同质」 |
| 2 | **1 < D < 2** | 能分辨但信噪比薄。**单条读数不可单独使用**，必须配 n 次重复才能出结论 |
| 3 | **D ≥ 2** | 分辨力可用，P1 的 Reliability 项通过，可进 P2 |
| ★ | **长度混杂** | 选样规则自制造了 293/1581/4058 字的长度差。**逐结均值若随长度单调 → D 主要由长度驱动，属弱分辨，上面三条降一档读** |

> 本节在结果产出**之前**写入。结果只填进下一小节，判决线不动。

---

## 19.5.9 [MEASURED 2026-08-18] 结果：**判决线一条都没触发，D 未定义**

`gh run 32130867661`（公开仓 Actions，96 次真实调用，仪器全程同一把 `57ec6cf478d3875e`）。

### 原始读数

| 文本 | 字数 | 4 次重跑的 top1 | 结集 |
|---|---|---|---|
| **T0** 车祸致聋，问耳挂式 | 293 | `pain_seek` ×4 | `{pain_seek, suspend}` |
| **T1** 问能否屏蔽特定声音 | 1581 | `pain_seek` ×4 | `{pain_seek, suspend}` |
| **T2** OTC 与处方到底差在哪 | 4058 | `reward` ×4 | `{audit, belong, display, injustice, pain_seek, reward}` |

主导结的逐 rep 取值：
`T0 pain_seek` 0.92 / 0.92 / 0.90 / 0.92（极差 **0.02**）·
`T1 pain_seek` 0.88 / 0.80 / 0.85 / 0.82（极差 0.08）·
`T2 reward` 0.85 / 0.88 / 0.88 / 0.88（极差 **0.03**）。

### ★★ 统计量退化了，而且是往「通过」的方向退化

核心结（每个格子都出现的结）= **空集**（T0/T1 只有 2 个结，T2 有 6 个，三者交集为空）。
→ 分子分母都是 0 → `0/0` 报成 **`inf`** → **判决线 3「D≥2 通过」照字面读会触发。**

**这是同一类失效的第四次**，共同结构是：
**边界条件下统计量返回了对作者有利的值，且不报错。**
前三次：`top1_stable` 在 n=1 恒 True · `median(ws)>0` 隐藏阈值 · 稀有结极差冒充稳定性。

**处置：`D` 未定义，四条判决线一条都不触发，本轮不判 P1 Reliability 通过或不通过。**
探针已改为退化时抛错并明说「判决线一条都不触发」，并在
`tests/test_cce_measurement_system.py` 立闸钉住（反向测试确认会红）。

> 讽刺的地方值得记下：**结集互不相交本身可能是最强的分辨力**，
> 而我的统计量把它映射成了「没有数据」。这是设计缺陷，不是数据不好。

### 这批数据**已经**能下的结论

| 结论 | 证据 | 反驳 |
|---|---|---|
| **重测极稳** | 三份文本 top1 各 4/4 一致；主导结极差 0.02–0.08 | R=4 偏薄 |
| **T2 与 T0/T1 可分辨** | top1 不同、结集不同、无一重叠 | 见下方长度混杂 |
| **T0 与 T1 不可分辨** | 同 top1、同结集、`pain_seek` 均值仅差 ~0.07 | 也可能**就是对的**（两者都是听力受损者求助）——无真值，分不出 |

### ★ 顺带推翻我自己上一节的一个数

§19.5.7 报的「rep 间变动 **0.33**」用的是**对结取 max 的极差**。
本节数据显示主导结极差只有 **0.02–0.03** —— **`max` 永远被刚够 support 门槛的边缘结主导。**
所以 0.33 量的是**最吵的那个结**，不是仪器的噪声水平。**该数予以降级**。
（§19.5.7 的两臂**对照**结论不受影响：两臂用的是同一个 max 口径，0.33 vs 0.33 仍成立。）

### 严重的未解混杂：长度与结数几乎完全共变

293 字→2 结 · 1581 字→2 结 · 4058 字→6 结。
`support` 规则 `occur*2 > n` 是否在长文本上系统性地让更多结过门槛？未查。
**在这一条解决之前，任何跨不同长度文本的比较都被污染。**

### 已预登记的分支（写在 length 臂出数之前，git 历史为证）

`DISC_SELECT=jaccard` —— 取词集 Jaccard 相似度**最低**的一对（纯机械，实测 sim=0.0408）。
用于区分：**仪器盲**（九结读数与被测文本无关 → 四层结构与下游全部作废重来）
vs **语料同质**（仪器有能力 → 结论降为「本语料上不可用」）。

---

## 19.5.10 [MEASURED 2026-08-18] ★ P1 Reliability 判 **FAIL** —— 而且这批数据完全够判

§19.5.9 说「本轮不判 P1 通过或不通过」。**那句话是错的**，现予更正。

错在**把两件事绑在一个 gate 里**：
**可复现性是单文本内部性质 —— 不需要真值、不需要对照、不受长度混杂影响，已经测到底了。**
不够的是另一件事（可分辨性 / 仪器读不读内容），它缺一个等长阳性对照，
96 次调用怎么重排都合成不出来。

### 判决（`scripts/cce_ksep.py`，数据 `tests/data/discriminability_20260818.json`）

| 项 | 判决 | 依据 |
|---|---|---|
| **P1a 读数（结集）可复现** | **FAIL** | 3/3 文本各有一个结在闸上翻转；rep 对结集一致率 **0.50 / 0.50 / 0.33** |
| **P1b 已过闸结 intensity** | **FAIL** | T1 `pain_seek` 0.08、T2 `audit` **0.20**（占其均值 0.4375 的 46%）超 tol 0.05；T0 0.02 过 |
| **P1 = P1a ∧ P1b** | **★ FAIL** | 不需要再花一次 API |
| **P2 可分辨性** | **不可判** | 全部 `UNCALIBRATED` |

**翻转结逐条**：T0 `suspend` 1/4 · T1 `suspend` 3/4 · T2 `pain_seek` 2/4。
这是逐 rep 枚举，不是估计量，不含任何自由度。

### ★★ 根因是 `support` 闸的二值化，不是 n 太小

`support` 闸 = 对 Binom(n=5) 计数在 `occur > n/2` 处切一刀。
让输出布尔「不稳」（P(过闸)∈[0.1, 0.9]）的 p 区间宽度：

| n | 5 | 10 | 20 | 40 | 80 | 160 |
|---|---|---|---|---|---|---|
| 不稳定带宽 | **0.507** | 0.378 | **0.277** | 0.199 | 0.142 | 0.101 |

**n 从 5 提到 20 —— 4 倍 API 成本 —— 只把不稳定带从 0.51 压到 0.28。**
带宽 ~ O(1/√n)。**「加大 n」是错的处方。**

**正确的修法：停止发布布尔结集，改发 `occur/n`。**
诚实代价必须一起写进 gate：**n=5 时 `occur/n` 的分辨率是 ±0.2（一个计数）。**
50% 的类别翻转变成 ±0.2 的连续不确定度。**下游如果仍然需要一个布尔，问题原样返回。**

> 自我警惕：这个修法会让 P1a **按构造通过**（没有可翻转的东西了）。
> 那不是仪器变好了，是停止丢信息。

### `itch` 与 `inertia` 全程一次都没点火

→ 它们的信度**未被测量**。**禁止说「九结体系整体通过」。**

### 采纳 KSEP，否决 PSI 与 D_var

| 提案 | 处置 | 理由 |
|---|---|---|
| **KSEP** | **采纳** | 闸后读数上的位置检验（均值向量 L1/9 + 精确置换）。`min_effect=None` 时 verdict 恒为 `UNCALIBRATED` —— **PASS 分支结构上不可达** |
| PSI `(B̄−W̄)/(B̄+W̄)` | **否决** | 测的是**组内离散度不对称度**不是分离度。两文本期望读数逐结相同、仅一侧抖动大时恒 >0，解析上限 **1/3**（0.15 判决线的 2.2 倍，加大阈值也堵不住） |
| D_var | **否决** | 闸前算、闸后判 —— 闸后逐字节相同的两份文本它给 0.9988 PASS |

### ★ 元教训（第五次，形状和前四次不同）

前四次是「统计量在**退化**输入上返回有利数」。这一轮四个提案**一个都没退化** ——
它们是**欠定或错位**：PSI 测离散度却叫分离度；D_var 闸前算闸后判。

**新规则：写完任何守卫/闸门，必须构造一个它应该抓住的输入，确认它真的触发。**
本次就靠它抓到 KSEP 自己有一条**不可达分支**（「无恒定出现的结」）——
可达性已证明并标注，且明说**它不算已验证的守卫**。

### ★ 连带降级：「round-robin 不改善稳定性」那次撤回**本身也没有依据**

§19.5.7 的 0.33 是 **max-over-knots**，被骑闸的边缘结垄断。同口径复算：

| 文本 | max 口径极差 | 9 槽平均 rep 间距离 |
|---|---|---|
| T0 | 0.180 | **0.0111** |
| T1 | 0.300 | **0.0219** |
| T2 | 0.335 | **0.0491** |

**差一个数量级。**「两臂都是 0.33」只说明两臂的**最吵那个边缘结**一样吵，对主导结什么都没说。

三层分开记：
1. 「打掉了天花板」→ **仍然撤回**（从来没有正面证据）
2. 「实测反证了 s1 是大头」→ **降级为「未测」，不是「已证伪」**
3. `s1_pairing=round_robin` 地位不变：结构性选择，非经验证的改进

> **通则：用坏统计量得出的否定结论，不比用坏统计量得出的肯定结论更可信。**
> 我此前只防「退化会吐出对我有利的答案」，漏了对称的一半 ——
> 它同样会吐出对我不利、而我因为「显得诚实」就照单全收的答案。**自我批评不是证据。**

---

## 19.5.11 [MEASURED 2026-08-18] ★★ 根因更正：仪器没有漂移，是布尔闸把 ±0.22 的测量洗成了干净类别

§19.5.10 的处方（停止发布布尔结集，改发 `occur/n`）**方向对，理由说错了一半**，现更正。

### 更正一：`occur/n` 本身也不"稳"，而这**恰恰证明仪器是好的**

从同一批数据（0 次新调用，`per_knot` 早就记了每个被观测结的 `occur/n`）算 rep 间极差：

| 文本 | 最不稳的结 | 四次 rep 的 `occur/n` | 极差 |
|---|---|---|---|
| T0 | `suspend` | 0.2 / 0.6 / 0.0 / 0.2 | **0.60** |
| T2 | `pain_seek` | 0.8 / 0.6 / 0.4 / 0.2 | **0.60** |
| T1 | `suspend` | 0.4 / 0.8 / 0.8 / 0.6 | 0.40 |

**极差最大 0.60 = 3 个计数**，不是我在 §19.5.10 里写的 ±0.2。
**「量化步长 ±0.2（一个计数）」是分辨率，「rep 间极差 0.60」是可复现性 —— 我把两者混为一谈了。**

但关键在下一步：这抖动是不是**纯抽样**？

### ★ 过散检验：X² = 44.37，df = 36，X²/df = **1.23**，p = **0.159**

12 个非退化的「文本 × 结」格，逐格比较 rep 间观测方差与二项预期 `p(1−p)/5`：

| 合并过散参数 Σ观测/Σ预期 | 比值中位数 | 范围 |
|---|---|---|
| **1.20** | 1.19 | 0.39 – 2.22 |

**p = 0.159，不显著 ⇒ 无法拒绝「抖动全部来自 n=5 抽样」。**

> **仪器没有额外漂移。** 所谓「读数不可复现」不是仪器缺陷 ——
> 是 n=5 的抽样不确定度**本来就有这么大**，而布尔闸把它藏起来了。
> 问题从来不是仪器不稳，是**把一个 ±0.22 的测量洗成了一个干净的布尔**。

### 更正二：Wilson 区间证明闸切在了数据区分不开的地方

不用 `sqrt(p(1−p)/n)`（它在 `occur=0` 或 `occur=n` 时给 se=0，等于宣称"5 次全中 ⇒ 完全确定"）：

| occur/n | 点估计 | Wilson 95% 区间 |
|---|---|---|
| 5/5 | 1.00 | **[0.566, 1.000]** |
| 4/5 | 0.80 | [0.376, 0.964] |
| **3/5（刚过闸）** | 0.60 | **[0.231, 0.882]** |
| **2/5（刚没过）** | 0.40 | **[0.118, 0.769]** |
| 1/5 | 0.20 | [0.036, 0.625] |

**3/5 与 2/5 的区间大幅重叠** —— 闸切在了数据根本区分不开的位置。
**5/5 的下界只有 0.566**：全票通过的结，真值也可能低到 0.57。

### 落地（`scripts/cce_knot_classify.py`）

- `knots` **不再 `continue` 掉少数派**，全量发布，每条带 `occur` / `n` / `support_ci95` / `support_majority`
- `weight` 仍**只在过闸结上**归一，未过闸恒 `0.0`
- `intensity` / `families` / `drive_brake` **本次刻意不动** —— 动它们是另一个变更

**「下游逐值不变」是被测的，不是被声称的**（`tests/test_cce_support_publication.py`）：
`cce_align_v2.score` 的 `alignment_score`/`resonance`/`dissolution` 在 post 与 reply 两模式下逐值相同；
`reply_batch.hooks_for` 选择相同。`detail` 会多出零贡献行 —— 已核无消费者。

### ★ 两条旧契约断言被 CI 抓到

`test_cce_knot_stability.py` 里「少数派不进 knots」「2/4 不进输出」编码的是**已废止的契约**。
**没有删掉它们，换成了新契约下必须成立的断言**：少数派必须**在** `knots` 里、`weight=0`、
`occur=n/2` 的区间必须横跨 0.5。CI 测试数量下限 11 → 13。

> 这一条本身就是 §19.5.10 元教训的正面案例：**闸真的抓住了我改动的东西。**
> 一个改了生产行为却全绿的测试套件，才是该担心的。

### 对「加大 n」的判决要说得更准

§19.5.10 说「加大 n 是错的处方」——**对布尔成立，但要补一句**：
布尔的不稳定带宽与 `occur/n` 的标准差**都是 O(1/√n)**，同一个速率。
差别不在收敛快慢，而在**布尔把信息丢了**：任何 n 下都分不清 0.49 与 0.51。
所以发布 `occur/n` 不是为了让读数变稳，是为了**不把 ±0.22 的测量洗成一个干净的布尔**。

---

## 19.5.12 [MEASURED 2026-08-18] ★ Stage1 等长阳性对照 **通过** —— 仪器读的是内容，不是长度

oss run **32141330271**，64 次调用，仪器 `57ec6cf478d3875e` 全程一致（与 run 32130867661 同一台）。

### 前登记设计（跑前写死，未事后调整）

- `T_a` = 语料**天然**最短的一份，293 字
- `T_b` = 其余 11 份各截到 ≤293 字的最大词边界前缀，取与 `T_a` **Jaccard 最低**者
  → 实选 index 10，**289 字**，Jaccard **0.075**（其余对 0.088–0.156）
  → 选「最不像」是**故意给仪器最好的机会**：这里都分不开，别处更分不开
- `R = 4`（不是 3）：KSEP 要求 R≥4，否则 p 下限 1/10 = 0.1 > α，设计上永不可拒绝零假设
- 两份**同一 run 内**跑：混用历史 rep 会引入批次效应，而批次效应**抬高**分离度（假阳性方向）

### 结果

| | 值 |
|---|---|
| 观测 `T` | **0.07389** |
| 在置换零分布中的排名 | **35 / 35（最大）** |
| `p` | **1/35 = 0.0286**（= 下限，R=4 能给出的最强结果） |
| 判决 | **SEPARATED** |

> **等长条件下仪器分得开两份不同内容 ⇒ 它读的是内容，不是长度。**
> §19.5.9 悬着的「仪器盲 vs 语料同质」这一支，可以排除「仪器盲」。

### `min_effect` = **0.06278**（前登记规则：零分布 95 分位）

KSEP 的 PASS 分支**从此存在**。常量连同三条限度一起写进代码（不许只写在文档里）：

1. **一对文本 / R=4 / 35 构型** —— 这是**一个**经验锚，不是估计良好的常数
2. 来自**最有利**的一对，即「最好情况下的可分离量级」，不代表典型文本对
3. ★ **等长内容效应 0.07389 只有长度驱动效应（T0-vs-T2 = 0.40611）的 18.2%**

### ★★ 由此回判：此前 T0-vs-T2 的"分离"约 **82% 是长度**

| 对照 | T | p | 标定后判决 |
|---|---|---|---|
| **A vs B（等长 293/289）** | **0.07389** | **0.0286** | **SEPARATED** |
| T0 vs T1（293 / 1581） | 0.02208 | 0.0571 | **NOT_SEPARATED**（且 T < min_effect） |
| T0 vs T2（293 / 4058） | 0.40611 | 0.0286 | SEPARATED，**但 82% 由长度驱动，不可作内容分辨力证据** |

**T0 与 T1 这两份真实文本，本仪器确实分不开。** 这不再是「不可判」，是一个有标定的否定结论。

### 可复现性再次 UNSTABLE_MEMBERSHIP（A 0.500 / B 0.333）

与 run 32130867661 完全一致 —— 且现在知道来源是 n=5 抽样（过散 1.20，p=0.159），
**不是仪器漂移**。两次独立实验给出同一个数量级，这本身是仪器行为稳定的旁证。

### 诚实边界

前登记的判决线写了「失败无法区分仪器盲与文本真像」。**成功有镜像的边界**：
在**最不像的一对**上成功，不能推出典型文本对可分。第二对独立文本跑出来之前，
`min_effect` 只是一个锚，不是阈值。

---

## 19.5.13 [MEASURED 2026-08-18] 第二对（典型）分得开；长度臂的负对照**前提不成立**

两个前登记探针同批跑完，仪器全程 `57ec6cf478d3875e`。**两条结论都推翻了我自己先前的话。**

### A. 第二对等长文本（oss run **32143785964**，64 调用）—— 典型对也分得开

规则取 Jaccard **中位数**（典型），排除 Stage1 用过的 index 0/10 → index 1×8，Jaccard **0.1013**，长度 288/286。

**T = 0.22389，排名 35/35，p = 1/35 = 0.0286 ⇒ SEPARATED。**
两对独立等长文本都在 p 下限分开 ⇒ **「仪器读的是内容」显著加强。**

#### ★ 证伪一：「Jaccard 最低 = 给仪器最好的机会」—— 撤回

| 对 | Jaccard | T |
|---|---|---|
| Stage1「最不像」 | 0.0750 | 0.07389 |
| 第二对「典型」 | 0.1013 | **0.22389（大 3.0 倍）** |

**词面相似度不预测可分离性。** §19.5.12 里「故意给仪器最好的机会」那句没有依据，已在代码注释里划掉。

#### ★ 证伪二：不存在全局 `min_effect`

两对的零分布 95 分位 **0.06278 vs 0.14944，差 2.4 倍** —— 水位由**文本自身的组内变异**决定。
且 **R=4 时 `p≤0.05` 需要观测严格大于其余 34 个构型 ⇒ 已蕴含 `T > null_max`**，
`min_effect` 只在「整个零分布被压在它之下」时做功。
**`min_effect` 不动**（前登记写的是「取两次较小者」=0.06278）—— **不事后挪门柱。**

### B. 长度零假设臂（oss run **32143780680**，96 调用）—— ★ 三臂救了这一臂

| 臂 | 长度 | 观测到的结 | 结集一致率 |
|---|---|---|---|
| BASE | 293 | inertia, injustice, pain_seek, suspend | 0.167 |
| PAD | 1564 | audit, **display**, injustice, pain_seek, **reward**, suspend | **0.000** |
| FILL | 1270 | **display, reward** | **1.000** |

**垫料不是无结的。** `FILL` 单独跑就稳定点火 `display` + `reward`，而 `PAD` 比 `BASE` 多出的
`[audit, display, reward]` 里，`display`/`reward` **正是垫料自己的结**。

> **⇒「无结垫料」前提不成立，本臂无法回答长度问题。长度仍是开放问题。**
> 两臂设计会在这里给出一个**自信的错误答案**（任一方向都能自圆其说）。
> 这正是把两臂改三臂、把「假设」换成「实测」的全部理由。

#### 主判是 UNDERPOWERED，不是阴性

`BASE vs PAD`：`T = 0.10792`，`p = 0.0857`，等价上界 `0.16153` > `min_effect 0.06278`
⇒ **NOT_SEPARATED 且 NOT_EQUIVALENT ⇒ 既不能说不同，也不能说相同。**
**且 T 高于 `min_effect`** —— 「低于当前分辨率」的说法在此为假。

### ★ 我自己写的判决逻辑报了有利结论

探针里原本是 `if p > 0.05 or T < min_effect: 判定「没有推动读数」`。
那一行**把 `p>0.05` 当成了「无效应」的证据**（经典谬误），并在 `T` 高于 `min_effect` 时仍打印「低于分辨率」。

**根因修法：三分判决收进 `KSEP.verdict3()`，探针不自己判。**
每个探针各判一次 = 每个探针各错一次。出口只有三个：

| 出口 | 含义 |
|---|---|
| `SEPARATED` | 有证据说**不同** |
| `EQUIVALENT` | 有证据说**差异小于当前分辨率** |
| `UNDERPOWERED` | **既不能说不同，也不能说相同。不是「没有差异」。** |

### ★ 附带发现：可复现性是**文本的**性质，不是仪器的常数

`FILL`（中性技术文本）结集一致率 **1.000**；`BASE`（真人个人叙述）**0.167**；`PAD` **0.000**。

> 同一台仪器，在中性技术文本上完美可复现，在真实的人类个人叙述上崩掉。
> **不稳定不是仪器的固定属性 —— 丰富、含糊、多义的人类文本才是它崩的地方。**
> 这对 P2（收集真实读者响应）是直接的坏消息：真实语料正是最不稳的那一类。

### 九结现已全部被观测到

`itch` / `inertia` 在第二对里点火（run 32130867661 中 itch 从未出现、inertia 只在闸下 2/5）。
⚠️ 但**稀有结的逐结信度仍未测量**，「九结整体通过」照旧禁止。

---

## 19.5.14 [MEASURED 2026-08-18] ★ 长度问题已答；但仪器没有「空读数」这一档

oss run **32147076464**，仪器 `57ec6cf478d3875e`。两条腿，一条治本一条意外更重要。

### 腿 B（不含任何假设）：`BASE` vs `BASE×5` → **EQUIVALENT**

内容**逐字相同**，长度 293 → 1473（对照 T1 = 1581）。

| T | p | 等价上界 | min_effect |
|---|---|---|---|
| 0.02056 | 0.4857 | **0.04514** | 0.06278 |

**结集完全相同**（`inertia` / `injustice` / `pain_seek` / `suspend`）—— 长度 5 倍，**没多点火任何结**。

> **⇒ 长度本身不驱动读数。T0-vs-T2 的差异应归因于内容。**

⚠️ 限度：重复是最弱的一种「变长」，模型可能把重复段落当一段处理。
它排除的是**「纯 token 数」**这一机制，不排除「更长的真实文本含更多样内容」——
但后者是**内容**，正是仪器该响应的东西。

### ★★ 腿 A：三个不同文体的候选垫料**全部**点火

| 垫料 | 点火的结 |
|---|---|
| `filler_numeric`（**纯数字表**） | audit, **belong**, display, **pain_seek**, reward, suspend（6 个） |
| `filler_legal`（法律样板） | audit, inertia, injustice, pain_seek, reward, suspend（6 个） |
| `filler_procedural`（操作步骤） | display, reward |
| `filler_neutral`（说明文，§19.5.13） | display, reward |

**一张纯数字表读出 `pain_seek` 与 `belong`。**

> **⇒ 九结对任意文本都响应，缺少「空读数」这一档。**

#### 这条改变九结该怎么用

- 「某结出现」携带的信息**比此前假设的少得多** —— **没有可对照的零点**。
- 但「文本 A ≠ 文本 B」仍是强证据（两对等长文本均 p = 1/35）。
- **⇒ 支持比较性 / 差分使用；不支持对单一文本的绝对断言。**
  「这条评论有 `pain_seek`」几乎不携带信息；「这条比那条更 `pain_seek`」才有。

这与 §19.5.11 的结论同向：仪器本身是好的**比较器**，坏的**绝对计**。

### 撤回：§19.5.12 的「T0-vs-T2 的分离约 82% 是长度」

| 反证 | 内容 |
|---|---|
| (a) | 第二对等长 T = 0.22389 = T0-T2（0.40611）的 **55%** ⇒ 18.2% 是拿**最小**的等长效应当上限，而等长效应本身在 0.074–0.224 间变动 |
| (b) | 腿 B 直接证明长度 per se 无效应 |

已在 `scripts/cce_ksep.py` 常量注释里划掉并写明两条反证。

### 本轮四个探针的总账

| run | 问题 | 结论 |
|---|---|---|
| 32130867661 | 读数可复现吗 | **P1 FAIL**；根因是布尔闸洗掉不确定度，非仪器漂移（过散 1.20, p=0.159） |
| 32141330271 | 等长下分得开吗 | **SEPARATED** T=0.0739, p=1/35；min_effect 标定 0.06278 |
| 32143785964 | 典型对也分得开吗 | **SEPARATED** T=0.2239；证伪 Jaccard 代理与全局 min_effect |
| 32143780680 | 垫料能做负对照吗 | **不能** —— 垫料自带结；主判 UNDERPOWERED |
| 32147076464 | 长度驱动读数吗 | **不驱动**（内容同、长度×5 → EQUIVALENT）；且**无空读数** |
| 32150369795 | stage1 也没空读数吗 | **也没有**（无人称/真人 JS 比 0.99）；`confidence 高估`假设被推翻 |

---

## 19.5.15 [MEASURED 2026-08-18] P2 前置基线：stage1 **也**没有空读数；而「confidence 高估」被我自己的实测推翻

oss run **32150369795**，60 次调用（**只跑 stage1**），5 文本 × R=4 × k=3。
数据固化 `tests/data/p2_stage1_baseline_20260818.json`。

**为什么必须单独测**：Observation 层（`cce_response_chain.py`）喂的是 **stage1 四层**
（desire / need / emotion / action），九结（stage2）按 `cce_response_chain.py:191` **不进聚合**。
所以 §19.5.14 关于九结「无空读数」的发现**不能外推到这一层**。

### 问题一 ✅ 证实：stage1 也没有「空读数」这一档

距均匀分布的 JS：**真人文本均值 0.3325 vs 无人称文本均值 0.3277，比值 0.99。**

| 层 | 一张**纯数字表**（Table 4，一列测量值） | 真人（车祸后无法忍受耳内异物） |
|---|---|---|
| desire | 控制欲 32% / 安全感欲 29% | 摆脱欲 40% / 拥有欲 20% |
| need | N01_确定性 39% / N02_掌控局面 24% | N06_摆脱痛苦 35% / N07_占有资源 25% |
| emotion | relief宽慰 36% / approval认同 23% | desire渴望 30% / fear恐惧 25% |
| action | attend关注 42% / approach趋近 33% | approach趋近 44% / attend关注 33% |

> **数字表那份画像看上去完全合理 —— 正因为看上去合理，才危险。**
> 它不是乱码，是一个可信的心理画像，而被读的东西是一列数字。

**⇒ P2 的指标必须是差分的：禁止写「这条读者有 X」，只能写「这条比那条更 X」。**
这一条现在对**喂 P2 的那一层**有直接证据，不再是从九结外推。

### 问题二 ❌ 我的假设被推翻，且我的检验设计不同口径

预期 `across/within > 1.5`（即 `confidence` 高估可靠性）。
实测 **中位 0.36，20 个「文本 × 层」格全部 < 1** —— 方向相反。

而 ≈ `1/k` = 0.33 正是「每 rep 已平均 k=3 次」应有的结果
⇒ **未检出超出组内抽样的跨次漂移**（与 §19.5.11 九结侧过散 1.20 / p=0.159 同向）。

⚠️ **这个比较不是同口径的**：`within` 比的是单次 draw，`across` 比的是已平均的向量，
聚合层级不同。它能答「有没有额外漂移」（答：没有），**答不了「confidence 数值本身合不合适」**。

⚠️ **前登记有缺口**：我写的两条判决线是 `>1.5` 与 `≈1`，**都没覆盖实际落点 0.36**。
前登记本来就是防事后编故事的，这次它漏了一整个区间。下次要把「显著小于 1」也写进去。

### 由此更正了 Observation 层改动的**理由**（改动本身保留）

`scripts/cce_response_chain.py` 的 `_measurement()` 新增两个字段：

```
across_run_reliability: None
across_run_reliability_reason: "未测量: 每条 observed response 只跑一次 CCE, 没有独立重复…"
```

- **保留**：单次测量给不出跨次信度 —— 这条理由是硬的。
- **删掉**：「confidence 可能高估」—— 对 stage1 四层**没有证据**。
- **字段含义是「未测量」，不是「已知不可靠」，两者不可混读。**
- `tests/test_cce_observation_gap.py` 加反向断言：禁止再用「高估」当理由，
  也禁止把该字段默认填 `1.0`（换个字段名把「组内稳」重新包装成满分，等于没改）。

### ⚠️ 文档自身的一处缺陷（一并记下）

本节写入前，§19.5.10–19.5.14 在文件里是**倒序**的（14 → 13 → 12 → 11 → 10），
且 §19.5.6 被挤到了 §19.5.14 之后。原因是每次新增都插在同一个锚点之前。
已重排为升序。**教训：追加式写作要校验最终顺序，而不是假设锚点还在原位。**

---

## 19.5.16 [2026-08-19] 弃权三处开口；仪器谱系 gen1→gen4；标定迁移律

外部源码审计确认「无空读数」是 **contract-impossible**，三处阻断（逐一核实）：
stage1 prompt 要求对「这一个人」反推（从未授权判断有没有主体）· stage2 的 `and d["knots"]`
使 `{"knots":[]}` 被当成解析失败 · ingest 的 `if total <= 0: raise`。

### 落地
- **stage2 与 ingest**：空 knots / 零分布改为**合法弃权**，不再是失败
- **stage1 prompt**：**追加**（非替换）弃权出口 `no_inferable_subject`，原「对这一个人反推」指令原样保留
  - 验收 gate（run **32223866100**，30 调用）：四份中性垫料**每一个 draw** 都弃权（`[3,3]×4`），
    真人文本 6 个 draw 零弃权 ⇒ **「给了权限模型不用」这一支被排除**
  - 假阳性收口（run **32224198135**，72 调用，全部 12 份真实语料不挑不排 + 阴性对照）：
    无一份被**整条**误判；但 T01/T02/T03/T10 出现部分弃权，**T02 两个 rep 都只剩 k_valid=1**
- **★ 众数占比的分母**由 `len(tops)` 改为 `len(draws)` —— 弃权若不计入分母，**弃权越多众数占比越高**（3/3=1.0 的假稳）
- **★ 全零守卫**：共享 `top_label` 对全零向量返回**第一个标签**（实测 `拥有欲`），而 `call_parse` 的 ok 判据是列表真值 ⇒ 全零能通过。**故弃权信号必须显式，绝不能拿全零当弃权**

### 仪器谱系与「标定能不能搬」
| 代 | hash | 变的是什么 | 标定可搬？ |
|---|---|---|---|
| gen1 | `57ec6cf478d3875e` | — | 当日六次实测的基准 |
| gen2 | `287d07a0ef1ea78e` | 把 s1 prompt 与 abstention 纳入指纹（**物理仪器未变**） | ✅ |
| gen3 | `ea70b373d5bef630` | **s1 prompt 真的改了** | ❌ **全部作废** |
| gen4 | `565470cf26c16d01` | 把 aggregation 移出仪器哈希（**物理仪器未变**） | ✅ |

**★ 补了一个真洞**：此前 `prompt_sha256` **只哈希了 `_stage2_template`** —— 改 stage1 prompt
**不会改变 instrument_hash** ⇒ **静默换仪器**，正是 instrument_id 当初要防的事。已拆成 s1/s2 两份。

**★ 迁移律的判据**（外部评审纠正我「prompt 相同即可搬」太松）：**每个标定声明自己的 `depends_on`**。
我把判据进一步换成**可操作的一条**：**改了它之后，已采集的原始 draw 还能不能用？**
不能用 → instrument；能用（可从 draw ledger 重算）→ qualification policy。
据此 `support_rule` / `intensity_stat` / `abstention` / `k_valid` 全部移出仪器哈希 ——
**否则每修一次资格协议就白白作废一次仪器标定，而重标定要真投料。**

---

## 19.5.17 [MEASURED 2026-08-19] gen3 资格实验：`ADOPT_PENDING_MARGIN`

### 前一条判决线是**错误设定**，按失效协议处理
原前登记「真人误伤率 >1/12 即回滚」被 4/12 触发。但该 endpoint 把 abstain 1/3、2/3、3/3
**压成同一个 Yes**，而三者后果完全不同（k_eff=1 会让 `within_js` **结构性不可计算**）。

**处理：原规则 TRIGGERED 的事实永久保留 · 规则有效性 INVALIDATED · 本轮结论 INDETERMINATE ·
恢复 confirmatory 必须用新数据。**
> **错规则不能被重写成对规则，但错规则也不应继续拥有决策权。**

### 新前登记（终点按系统后果定义）
主 `U = P(k_valid<2)` · 次 `F = P(k_valid=0)` · `B` · 阴性对称 `Nd/Nf` · `R_requested` vs `R_qualified`。
判决四分区穷尽互斥，且**每个阈值都不依赖从本语料倒推**：
`Nd=0 → INDETERMINATE(channel_dead)` · `F>0 → ROLLBACK` ·
`F=0且U=0 → ADOPT_PENDING_MARGIN`（**不是 ADOPT** —— ADOPT 需已标定 margin，它不存在，
该分支**结构上不可达**）· `F=0且U>0 → ADOPT_WITH_RESTRICTIONS`。

### 第一轮 run 32227550589 被判废 —— 而缺陷是我自己的
阴性对照读出 `Nd=0` ⇒ 判 `channel_dead`。**但通道是活的**（`abstained=True, k_abstained=3`）——
`Nd=0` 是**我方仪器缺陷**：stage1 弃权分支与非弃权分支不同构（`k_ok` 把弃权算成成功、缺
`k_valid`、`draws` 为空），而**真正让它变成假数字的是探针里的 `s1.get("k_valid", s1.get("k_ok"))`**。

> **★ 没有那条通道自检，我会报「gen3 零损害，采用」，而仪器当时正在错报。**
> 那一轮真人侧 U=0/F=0 经核**也是真值**，读起来完全像好消息。

**派生纪律：对自己的 schema 禁止 `.get(key, default)` —— 它把 schema 漂移变成自信的错数。**

### 重跑 run 32231676330：`ADOPT_PENDING_MARGIN`
阴性 `k_valid=[0,0,0,0]`、`Nd=1.0`；真人 `U=0.0000 / F=0.0000 / B=0.0208`，48/48 全合格。

**三条不许被这个零盖住的事**（已写进测试）：
1. **三法则**：0 事件/48 观测 ⇒ 只能说 **U < 6%**（精确单侧上界 ≈6.05%），不能说 U=0
2. **同一台 gen3 上一轮（run 32224198135）确实观测到 U>0**（T02 两个 rep 都是 k_valid=1，
   2/24=0.083）；合并两轮（探索性）2/72≈0.028 ⇒ **本轮 U=0 不得读成「从不发生」**
3. **部分弃权是逐 draw 的随机事件，不是文本的固定属性** ⇒ 只能按率处理，不能按白/黑名单

### 立即安全修复
`k_valid<2 → WITHHOLD`（不再静默退回单 draw；`cce_full_run` 的闸由 **raise 改为 WITHHOLD**，
因为弃权上线后「有效 draw 不足」是**合法测量结果**不是管线故障）。
**且不做「抽到够两个为止」** —— 那会条件化于模型愿意给读数，隐藏真实弃权倾向。

---

## 19.5.18 [2026-08-19] ★★ 因果天花板 = `DESCRIPTIVE`（结构性）；三种「显著性」拆开

### 因果不可识别，比预想的更硬
`cce_response_chain.py:93` 强制 `reached_members == seen_actors`（**防伪造触达，好设计**），
副作用是 **reached 窗在构造上等于响应者集合** ⇒ **响应者/触达者恒等于 1** ⇒
**「激活率」不是测量，是常数**。

观测到的是 `P(state|responded)`，不是 `P(state|reached)`，更不是 `P(state|assigned exposure)`。
三样同时缺席：**曝光分母 · 曝光前状态 · 同期未曝光对照**。

新增 `CAUSAL_CAPABILITY`：`max_grade=DESCRIPTIVE`，禁止词表覆盖
CAUSED/INCREASED/REDUCED/ACTIVATED_BY/STATE_TRANSITION_CAUSED_BY_CONTENT，
且 **`causal_grade` 随每条 measurement 走**。
> 这条闸防的是：**未来某个下游 agent 把「响应者分布变了」自动改写成「内容改变了人群」**。

⚠️ **没有**把因果从架构永久删除 —— 冻结的是**当前采集剖面**。解锁条件含
`repeated_cross_section_pre_post_control`（**DiD 可建在重复横截面上，不要求前后同一批人**）。

### 三种「显著性」（`SIGNIFICANCE_CONTRACT`）
| 档 | 不靠产品数据能标定吗 | 现状 |
|---|---|---|
| `measurement` / `delta_resolution` | ✅ 同文本重复 | NOT_CALIBRATED |
| `interpretive` / `semantic_sesoi` | ✅ **外部盲评人类锚** | NOT_CALIBRATED |
| `behavioral` / `behavioral_sesoi` | ❌ 需真实 outcome | NOT_AVAILABLE |

★ 第二档**推翻了「没有产品输入就永久黑着」的判断**。
⚠️ `delta_resolution` **绝不能改名叫 SESOI**（minimal detectable change ≠ minimally important change）。
⚠️ **禁止出现笼统的 `practical_significance` 字段**（有反向测试）——
**笼统字段迟早被塞一个数进去，那正是 0.06278 当初的下场。**

---

## 19.5.19 [MEASURED 2026-08-19] gen4 live R=8：型 I 真实受控；但 power 饱和

run **32241812064**，192 次真实调用，三臂（T0 / **T0b 同文本独立重跑** / T1）各 8/8。

> ⚠️ **前一轮 run 32240552713 因单点故障整轮作废**：T0 臂 8/8 跑完后，T0b 某个 rep 三档全失败
> ⇒ `stage1` 按设计抛错 ⇒ 已花掉的六十多次调用一起白费。
> 诊断：原始失败件**内容为空** ⇒ **API 调用本身失败**，不是 prompt 破坏解析。
> **修法不是加重试**（每档已内部重试 3 次；rep 级重试会条件化于成功、藏起真实失败率）——
> 而是**让失败成为第三种状态**（qualified / abstained / **failed**），如实记账、**不替补**。
> **派生纪律：长投料探针必须能在单点失败时继续并如实记账，否则瞬时故障会把整轮成本清零。**

**★ 三臂而非两臂**：拿一对真实文本算「拒绝率」，**只有当这对真的不同时它才是 power**；
若它们其实相同，同一个数就是型 I 错误 —— **用同一批数据分不开**。

### 两件真东西
1. **型 I 在真实独立 rep 上受控**（此前只有 bootstrap）：零参照拒绝率 R=4..8 全为 0.000–0.015；
   全 8 rep 直接比 `T=0.00611, p=0.835`
2. **第一个分辨率数据点** `T_same(T0,gen4,R=8)=0.00611` —— **但没有**把 `delta_resolution` 填上
   （一个文本不构成 profile，有测试钉住）

### power 饱和 ⇒ 判决范围很窄
R=4..8 的 power 全是 **1.000** ⇒ `RECOMMEND_R=4`，**只对 T≈0.0617 这个量级成立**。
原因：所选文本对**换代后变了性质** —— gen1 `T=0.02208/p=0.0571`（未分开，正因如此被选作边界对）
→ gen4 `T=0.06174/p=0.00016`，**效应量涨 2.8 倍**。

> **★★ 由此得到实测结论：效应量不跨代转移。**
> 此前「标定不可搬」是**论证**，现在是**实测**。

**自我更正**：撤回「R 的下限至少 8」—— 那是 conditional bootstrap on gen1 且条件于那一对。
正确记法：`empirical_minimum: UNKNOWN` · `next_live_candidate: R=8` · `transferable: false`。

**这一轮不是前登记失败，是问题问窄了** —— 我以为在问「生产 R 取多少」，
实际只问了「**对这一个效应量**，R 取多少」。

---

## 19.5.20 [MEASURED 2026-08-19] ★ 扰动阶梯 Phase 1：`LADDER_USABLE`

### 为什么不再找「边界文本对」
按观测 T 筛边界对 = **selection-on-outcome**；即便独立重采可救推断，仍有
**winner's curse** —— pilot 上的 T 可能只是噪声，重测大概率发现它根本不在边界。
⇒ 把**扰动强度变成设计变量**。

### ★ Axis A 没有采用外部评审的版本
它建议 A 轴为「更强/更弱 reward、audit」。但 §19.5.x 早已否决过这条：
**「剂量臂用 rubric 自己的触发词 = 拿仪器对它自己的定义做检验；一台自洽但什么都没测的仪器会全过。」**
改用**去词化扰动**：改变所述情境/立场，但只描述**处境与动作**，不命名感受/评价/动机（**机器验证**）。

### 结果（run 32246651860，192 调用，六臂各 4/4）
| 对照 | T | p | 判决 | 相对零参照 |
|---|---|---|---|---|
| L0 vs **L0b**（零参照） | 0.02944 | 0.114 | not separated | 1× |
| L0 vs **A1**（去词化·轻度） | **0.19278** | 0.0286 | **SEPARATED** | **6.55×** |
| L0 vs **A3**（去词化·中度） | **0.28931** | 0.0286 | **SEPARATED** | **9.83×** |
| L0 vs **B1**（同义+句序） | 0.00972 | 0.571 | not separated | **0.33×** |
| L0 vs **B2**（仅格式标点） | 0.01236 | 0.486 | not separated | **0.42×** |

> **为什么这是最强的正面证据**：此前「它在读内容」靠两对等长真实文本 ——
> 但那些对**同时**差在内容与措辞上。本轮把两者拆开：
> **措辞变、事情不变 ⇒ 一点不动**（T 甚至低于 L0 自己重跑）；
> **事情变、一个心理状态词都没用 ⇒ 强分开**。

### ★ 两处过度声称已封进数据
1. **不能说它专门在读「心理姿态」** —— A 臂同时改了**所说的事情**，姿态与其他内容改变**分不开**。
   可以说的只是：**对「所述情境/立场的改变」有反应，即使不用心理词汇**
2. **不能宣称 `T(A1)<T(A3)` 的单调性** —— 前登记明令这是 Phase 2 的检验对象

边界：**n=1 base text**；R=4 时 A 臂 p **恰为下限 1/35**。

### 设计前提的检查在投料前抓到四次
① 「A 臂不得含 rubric 词汇」是**空检查**（rubric 判别式中文 / 语料英文 ⇒ 必然通过）
② 心理词表把多词短语与单词同行 ⇒ `left ear` 命中 `left`，**假阳性**
③ **长度混杂**：A 臂初稿 405/450 字 vs L0 293 ⇒ 已改到 279–307（极差 10%）
④ 断言作用域错：「A3 不该是问句」被**标题行**问号绊倒

---

## 19.5.21 [2026-08-19] 当天的方法学总账

### 新增的可执行纪律
1. **对自己的 schema 禁止 `.get(key, default)`** —— 它把 schema 漂移变成**自信的错数**
2. **`k_valid < 2` → WITHHOLD**，绝不静默退回单 draw
3. **当前 subject_chain 的最高 causal grade = DESCRIPTIVE**（结构性，不是「以后再优化」）
4. **measurement resolution ≠ SESOI**；语义 SESOI 可由外部人类锚建立
5. **前登记必须穷尽结果域且各区互斥**；写判决线前先问「**这个东西是二元的还是分级的**」
6. **规则失效协议**：只有结构性失效（终点压缩不同后果 / 统计量与构念不符 /
   关键步骤结构性不可执行 / 结果域未穷尽 / 可用反例证明）才能停止其推断权限，
   且**原规则触发的事实永久保留**
7. **重试不是污染；「失败被重试成功后从记录里消失」才是** ⇒ `attempt ledger`，
   measurement 与 operational **两本账分开**
8. **同一个 bug 要查所有分支**（`k_ok` 那个只修了一处，第二处在弃权分支）
9. **断言字符串存在/不存在的守卫会抓住解释它的注释** —— 今天三次同形，须只扫非注释代码行

### 被自己或实测推翻的说法（不再引用）
- 「Jaccard 最低 = 给仪器最好的机会」—— Jaccard 更高那对 T 反而大 3 倍
- 「T0-T2 的分离约 82% 是长度」—— 长度 per se 判 EQUIVALENT
- 「存在全局 min_effect」—— 两对零分布水位差 2.4 倍
- 「confidence 高估可靠性」—— across/within 中位 0.36
- 「R 的下限至少 8」—— gen4 实测 R=4 就够（对那一对）
- 「没有产品输入，实践显著性永久黑着」—— 语义 SESOI 可由人类锚建立

---

## 19.5.22 [2026-08-19/20] 外部评审第三轮：三个我判不了的决策，逐条落地

外部评审（web ChatGPT 线程「CCE下游主体构建建议」）对 Phase 1 结果给出执行判决。

**去词化 A 轴替换是正确的，原 Axis A 降级。** 原方案（用 rubric 自己的触发词写更强/更弱 reward、audit 的插入句）会退化成闭环：`taxonomy 定义 reward → 文本直接写 reward 同义触发 → taxonomy 检出 reward → 宣称 construct valid`——**这只能证明自洽**。原 Axis A 改名 `EXPLICIT_CUE_POSITIVE_CONTROL`，只能回答「面对明确命名的心理线索是否有灵敏度」，不进 Phase 2 primary。

**资格 margin 定死**：`F_max = 0` / `U_max = 0.05`，`provenance = ENGINEERING_BUDGET`（**不是**「文献证明 5% 缺失安全」——缺失比例本身不决定偏倚可否接受，不存在普适阈值）。
★ 闸必须用**精确单侧 95% 上界**，不能用点估计。零事件上界 `1 - 0.05^(1/n)`：n=48 → 6.05%，n=58 → 5.034%，**n=59 → 4.951%**（过闸最小 n）。gen3 的 0/48 因此正确地停在 PENDING。
★ `CONCENTRATION_FLAG`：任一 base ≥2/4 unqualified ⇒ `ADOPT_WITH_RESTRICTIONS`，防「总体 4% 但全集中在一种表达形式」被均值洗掉。

**语义 SESOI 判 `BLOCKED_EXTERNAL_ANCHOR`**（不是 `NOT_CALIBRATED`——缺的是**外部真值**，不是算力）。拆成 `human` / `llm_proxy` 两个字段，LLM proxy 只能是 `AVAILABLE_EXPLORATORY`，**永远不解锁** human 档：独立模型 ≠ 独立真值。作者本人盲评亦不得进入 formal calibration。

**刺激文本不许我手写。** 我是 ontology 作者兼实验设计者，可能无意识地把 A 臂写成「碰巧读得出的那种改变」。改为双 ontology-blind 生成器（G1=qwen3.8 / G2=glm-5.2，均与测量模型不同家族）+ 交叉盲验，我的角色压缩成**可审计的机器验收员**。
★ 一条重要限缩：**扰动作者不污染 resolution profile**——L0 vs L0b 两边都是真实 base 的独立测量。作者只影响 discriminability 与 invariance；resolution 的偏倚源是 **base-text sampling frame**。

**窄语料不延期跑。** 固定 domain/format/source ecology 反而让第一个 measurement study 更干净；只有 24 个文本却同时铺多平台多话题，会把各种 variance 搅在一起却没有足够 observation 分离它们（Generalizability Theory：某 facet 只观察到一个 level 时其方差不可识别）。
⇒ 分辨率状态固定四级：`POINT_OBSERVED → ESTIMATED_SCOPED → VALIDATED_SCOPED → CALIBRATED_BROAD`，`global_resolution()` 永远返回 `NOT_CALIBRATED`，**禁止**拿 scoped median 顶替。

---

## 19.5.23 [2026-08-19/20] sampling frame 被换掉：历史语料是「为了回帖而挑的」

原本打算用 `run_items/*.json` 里的历史真人文本。**这批是脏的**——它们是为了回帖而挑出来的，选择机制与内容相关、非随机。混进 sampling frame = 把一个不可观测的选择偏倚烧进 frame。

改为一次无过滤的活动流抓取（r/HearingAids + r/HearingLoss + r/hardofhearing 的 `/comments` 与 `/new`，150–2000 字符，去重）→ **367 条**，站点 111/121/135 均衡。历史那批降为 `RESERVED`。

**长度改为事前分层抽样**（S 150–599 / M 600–1199 / L 1200–2000）。事前分层 ≠ 事后分层：长度在任何测量发生前就已知。分配规则「每层先 3 条 → 剩余按容量比例 → largest remainder」，得 **S=13 / M=7 / L=4**，权重 `w_h = 18.0 / 13.1 / 10.25`。L 层拿 4 条 > 自然比例 2.7 ——保底 3 条正是不让 41 条的长文本层被淹没。

**primary eligibility 按 domain/source_family 定，不按站点字符串**——否则同一生态内换个子版就掉出去。剔除 r/mcp、r/AI_Agents、dev.to、quora（各 1–2 条，既支持不了 source effect 估计，又让 generalization boundary 更糊）。

---

## 19.5.24 [MEASURED 2026-08-20] ★★ 两轮面板作废：我把随时间衰减的故障做成了实验效应

**第一轮（MiniMax，664 reps）看起来是个重大发现**：L0 真人原文 4% 不合格 vs B1 生成改写 **65%**——同样的内容只换措辞。

**是假的。** `panel_manifest` 里 24 个 base 的 L0/L0b **排在全部生成臂之前**，`ThreadPoolExecutor.map` 按顺序取任务 ⇒ L0/L0b 跑在前半程（未限流），生成臂跑在后半程（已限流）。「生成文本更难读」与「后半程被限流」完全混杂。

限流是实测确认的：裸调用 M3 返回空 content + `usage.total_tokens = 0`——**M3 的限流形态是 HTTP 200 + 空 content，不是标准 429**。实际跑到 73 calls/min，而稳态约 50。

打散后复测：不合格率按臂 **10–24% 齐平**，按生成器 **G1 14% / G2 15% / 真人 13%**。假发现被证否。

> **通用教训**：任何批量采集，任务顺序必须与被比较的因子无关。顺序执行 + 按因子排好的任务表 = 把任何随时间衰减的故障（限流、服务降级、配额耗尽、缓存变冷）直接**做成**一个漂亮的实验效应。这类假发现特别危险，因为它**符合直觉**，不会触发怀疑。

**同源的两处缺陷**：① 熔断器只盯 stage1 的 `n_infra_failed`，而 **stage2 没有 attempt ledger** ⇒ 213 次 stage2 空返回对它全程隐形；② 异常处理器把 stage2 崩溃**伪造成 `k_valid=0`**，即把基础设施失败误记成「stage1 重复不足」。

**第二轮（阿里云 gen5，294 reps）也没用**，但原因不同：完全打散虽消除了时间混杂，却让 294 个 rep 摊在 166 个臂上，**只有 3 个臂凑够 R=4 ⇒ 一个 base 都分析不了**。停因是**周配额耗尽**（`token-plan 1-week quota exhausted`），不是滚动限流。

⇒ 正解：**按 base 分块随机**——base 顺序随机、base 内所有臂连续跑完。臂间对比仍受时间保护（同一 base 的臂几乎同时跑，衰减对各臂等同作用），中断时已完成的 base **完整可分析**。两个性质同时拿到。

**换仪器的算术**：阿里云 294 reps ≈ 2350 次调用打光一周配额，整个面板需 5312 次 ≈ 2.3 倍，且订阅 08-22 到期 ⇒ **算术上跑不完**。MiniMax 订阅制无按量预算闸，只有滚动限流 ⇒ 长面板必须走它。gen5 的 294 reps 留档，**不与 gen4 混用**。

---

## 19.5.25 [MEASURED 2026-08-22] ★★ Phase 2 多 base 标定面板：三条 profile 与两个负面结果

**32 base × 7 臂 × R=4 = 880 reps，全部在 gen4 `565470cf26c16d01` 单一仪器上**（扩展块坚持同代，未混 gen5）。primary（盲验 FOLLOWS）与 sensitivity（全部机器验收通过）两套在所有 headline 上一致 ⇒ 无 `INDETERMINATE`。

### 成立的

- **型 I 受控**：29 个 base 的零参照 **0/29 分开**
- **分辨率 profile**：`T_same` 中位 **0.0315**，跨度 **0.0106–0.0789 = 7.5 倍**
  ★ 长度层中位数几乎持平（S .0317 / M .0400 / L .0315）⇒ **7.5 倍是文本间差异，不是长度驱动**。故不得按长度分层建阈值。
  ⇒ 「单一全局 `delta_resolution` 是错的」从论证变成 29 个文本的实测。状态升 `POINT_OBSERVED → ESTIMATED_SCOPED`，但 **`delta_resolution` 仍为 `None`**（拿本批分位数给同一批发合格证 = calibration 与 validation 混用）
- **灵敏度**：A1/A2/A3 的 `P(T > 同 base 零参照)` 全部 **= 1.0**；A3 19/20 分开

### 负面结果一：`SURFACE_SENSITIVE`，被独立盲评佐证

B1（同义改写 + 句序，**内容与处境不变**）**7/26 分开**。若真为不变性对照（α=.05），出现 ≥7 个的概率 **0.00022**。

★ 这 7 个对的 **盲评 `P(DIFFERENT)` 全部为 0.000**——760 次 ontology-blinded 盲评（190 对 × 2 家族 × 2 顺序），两个不接触九结定义、不看任何读数的模型家族**一致判「处境没变」**，而 CCE 判它们分开。

盲评本身先过验收：**阳性对照 L0b（两段逐字相同）128/128 判 SAME**；A3 127/128 判 DIFFERENT（确有分辨力）；顺序 0 vs 1 为 155 vs 148（无 position bias）。

B2（仅格式/标点）3/28，中位 0.0386 ≈ 零参照 0.0315 ⇒ 与不变性相容。

> **分界线落在「格式」与「措辞」之间：改格式不动读数，换词就动。**
> 「好比较器」这个定性对**词面级改写**必须下调。

### 负面结果二：T 不映射到被感知的差异程度

`P[A1<A2<A3]`：**CCE 0.18**（primary, n=17）/ 0.22（sensitivity） vs **盲评 0.81**（n=32）。

设计的剂量序**可被独立判读者按序感知**，但 CCE 的 T 不跟着走。这比「不单调」更强——外部评审当初坚持「只能叫 Designed Perturbation Ladder，禁止叫 Known Effect-Size Ladder」由此得到实测支持。

### 两个闸都没过（如实报）

- **coverage**：ladder 完备 **18/32 < 20** ⇒ 仍 `INSUFFICIENT_COVERAGE`。前登记**只允许扩一次且已用掉** ⇒ 不得再扩，缺口随结果标注。主因：A2/A3 弃权率 12%/17%（真人 2%）拉低完备性
- **资格闸**（真人原文 = 生产输入）：U = 9/256 = **3.5%**，但**单侧 95% 上界 6.05% > `U_max` 5%** ⇒ `ADOPT_PENDING_PRECISION`。点估计 3.5% 会误判通过

### 必须标注的限度

**弃权呈剂量梯度**（L0/L0b 2% · B2 3% · A1 3% · B1 5% · **A2 12% · A3 17%**）⇒ A3 的 T 分布**条件于合格的那 83%**，存活样本可能有偏。弃权机制按设计工作，但这个条件化必须随结果走。

**生成器家族合规率差 21 倍**（MAX_REGEN=3 时 qwen 1.7% vs glm 36.7% 失败；glm 输出长度中位数是要求的 31.5 倍）。协议修订 #1 把 MAX_REGEN 3→8 救回（判据：修订依据是 **operational 事实**而非 **实验 outcome**，且修订时一次测量都没做），但这条 operational 事实不因救回就抹掉。

**scope**：hearing consumer discussion / 三个子版 / 150–2000 字符。`across_source_families` 与 `across_domains` 均为 `NOT_ESTABLISHED`。

---

## 19.5.26 [2026-08-22] 本轮新增的方法学纪律

1. **任务顺序必须与被比较的因子无关**，且**按 block 分块**——完全打散会让中断后的部分数据不可分析（294 reps 换来 0 个可分析 base）
2. **测量模型 = 仪器身份**。`"M3"` 曾写死在 stage1/stage2/instrument_id **三处**，漏改一处就得到一台**半新半旧的嵌合仪器**，而 `instrument_hash` 只反映改过的那处、看起来还很正常。已参数化为 `CCE_MEASUREMENT_MODEL`
3. **测量模型不得参与刺激构造**（生成或筛选）——按它自己的判断筛刺激，留下的都是它认为变了的那些 ⇒ 可分辨性被系统性抬高
4. **协议修订要带时间戳 + 原因 + `outcome_dependent` 声明 + 修订前结果留档**。判据：依据是 operational 事实还是实验 outcome？前者在结果出现前透明更新不引入 outcome-dependent flexibility
5. **指纹要用真实内容导出**。Phase 1 传的是 `f"x{i}"` 合成串，等于把 `_check` 的缓存伪影守卫绕过去了
6. **dry run 不得继承真实 checkpoint**——否则空跑会把真实成功记录混进结果，让「失败必须落 `GENERATION_FAILED`」这类守卫恒真
7. **长任务必须有 checkpoint 与进度输出**：没 checkpoint = 一次意外把已花的钱清零；没进度 = 无法区分「慢」和「死」，会诱发错误的 kill

---

## 19.5.27 [2026-08-22] 外部评审第四轮：定性再次收窄；无假设界；B1 的层级拆解

### 我拟的定性被判「仍然说过头」

我写「**在处境层面是好比较器**，在词面层面不是」。第一句站不住——B1 已证明**处境与说话人状态被独立盲评认为没变**（124 次判断 `P(DIFFERENT)=0.000`），而 CCE 仍 7/26 判分开。

**正式定性**（写进 `cce_ksep.INSTRUMENT_CHARACTERIZATION`，由测试守住不许退回）：

> gen4 是**对「内容 + 表述方式」共同敏感的 representation-sensitive contrast detector**，不具备语义表述不变性。

- `semantic_form_invariance: FAILED` · `wording_method_effect: DETECTED`
- `SEPARATED` 只意味着 **CCE representation differs**，**不**意味着 subject situation / psychological construct 不同
- **T 只是仪器内部的分离统计量，不是语义差异大小**（非单调直接打掉这条）
- **允许**：同输入 QA / drift / 版本比较；表述被严格控制的实验对比；表征变化检测器
- **禁止**：自由文本 A vs B 判 SEPARATED 就推断主体真的不同；「T 越大 ⇒ 心理差异越大」

★ **术语归位**：这是 **alternate-form / wording-method invariance**，**不是**经典跨组 DIF——DIF 是同一 item 跨人群，这里改变的是**输入表述本身**。心理测量学里叫 wording/method effect，是成熟问题。

### 度量不换，只开研究轨

非单调可能来自四层中任意一层（文本 → 九结表征 → rep 聚合 → 均值向量 → L1 距离），**不能先把最后一层判有罪**。
★ 我提的 pair-local 马氏距离有硬问题：每臂 R=4 而维度 p=9 ⇒ **n ≪ p**，样本协方差病态甚至不可逆，必须 shrinkage。
★ 换度量后 null / 型 I / resolution / discriminability / equivalence **全部要重标**；若在 Phase 2 上选中某度量，Phase 2 只算 **metric-development set**，必须新数据确认。

### ★★ Manski 无假设最坏界：两条 headline 都活下来

二元终点用 partial identification：`lower = S/N`（所有弃权都不分开）· `upper = (S+M)/N`（都分开）。

| 臂 | 下界 | 上界 | 条件值 |
|---|---|---|---|
| **B1** | **0.226** | 0.387 | 0.269 |
| **A3** | **0.594** | 0.969 | 0.950 |
| L0b | 0.000 | 0.094 | 0.000 |
| A1 | 0.719 | 0.812 | 0.793 |
| A2 | 0.688 | 0.906 | 0.880 |
| B2 | 0.103 | 0.138 | 0.107 |

- **B1**：即便所有缺失都不分开仍有 **22.6%**，远高于不变性期望 ~5% ⇒ `B1 FAILED` **不依赖任何缺失机制假设**
- **A3**：下界 59.4% 已远高于零参照 ⇒ 灵敏度结论同样无假设成立

★ **禁止**把弃权填成 `T=0` 或 `T=max` 再当真实值——**T 根本没被测出来，不是「测出来为零」**。
★ **不用 IPW**（需 `qualification ⟂ 未观测 T | 协变量` 即近似 MAR，而 A2/A3 本身就改变 qualification rate）；**不用 Lee bounds**（需更强的个体级 monotonic selection 假设）。

### 分端点状态（整轮不作废，但 ladder 终点必须判）

`overall: PARTIALLY_CONCLUSIVE` · `resolution: ESTIMATED_SCOPED` · `type1: SUPPORTED_IN_SCOPE` · **`joint_ladder: INCONCLUSIVE_COVERAGE`**（18 < 20，扩展已用尽，**不得再说 ladder confirmed**）· `B1: FAILED` · `B2: COMPATIBLE` · `A3: CONDITIONAL_ON_QUALIFICATION`。

### 资格闸还差多少（算术已独立复核）

x=9 时：**n=311 → upper95 = 0.049955（过）**；n=310 → 0.050114（不过）。现状 n=256 → 0.06055。
⇒ 再收 **55** 个。事件升到 10/11/12 则最小 n 为 336/361/386。
★ **固定 n、只看一次**——固定-n Clopper–Pearson **不是**为 optional stopping 设计的；要边跑边停必须改用 **anytime-valid confidence sequence**。

### ★ B1 的层级拆解（零调用，本地分析）

问「假灵敏度是哪一层在动」，三条结果：

1. **不是单个结失灵，是九维弥散变化**——前 2 结占总变化的比例：B1_separated **35.4%** vs A3_separated **31.1%**，几乎相同 ⇒ **不能靠修某一条 rubric 解决**
2. **B1 分开时的位移量约为真实内容变化的一半**——总 |Δ|：B1_separated 0.944 vs A3_separated 1.851（**51%**），且是 B1_not_separated 0.403 的 **2.3 倍** ⇒ 不是边缘噪声
3. **★ 词面效应不是整体电平漂移**——检验假设「若为电平漂移，去电平后 B1 应比 A3 缩得多」：实测 B1_separated 缩减 **−2%**、A3_separated **+1%**，都约等于零 ⇒ 词面改变的是**分布形状本身**，**任何只移除公共成分的度量都救不了**

⇒ 该候选已写入 `METRIC_BAKEOFF.pruned_candidates`。**否定**一个候选是有效剪枝，不需新数据确认；**选中**某度量才必须新数据确认。

### `confidence = 1.0` 的三处硬编码已处理

一个**永远等于 1.0** 的置信度字段比没有这个字段更坏——下游会以为那是测出来的。三处语义并不相同，故分别处理：

| 位置 | 语义 | 依据 |
|---|---|---|
| `cce_event_assemble.py:57` | 事件是既有观测的 1:1 复述 | `definitional` |
| `cce_event_assemble.py:78` | 「两区间重叠」由时间戳算出 | `definitional` |
| `cce_foundation_adapter.py:100` | `shot_boundaries` 只是一串时间戳，**检测器不给置信度** | `unreported_by_detector`（占位） |

契约新增规则：`confidence == 1.0` 时**必须**声明 `confidence_basis ∈ {definitional, unreported_by_detector, measured}`，且**只有 `measured` 允许进入下游加权**。测试含反向用例：裸 1.0 被拒、编造依据被拒、源码扫描无遗漏。

---

## 19.5.28 [MEASURED 2026-08-24/25] ★★ 跨域复现：词面不变性失败是 instrument property

### 起点：一个我自己指出的风险

Phase 2 的 `SURFACE_SENSITIVE` 只在**一个 source_family**（hearing consumer discussion）上测到。`across_domains` 是 `NOT_ESTABLISHED`——Generalizability Theory 的要求：某 facet 只观察到一个 level 时，其方差**不可识别**。

Phase 2B 就是为回答这一条设计的：3 source/format family × 2 domain × 3 长度带，四支结局跑前写死。

### 结果

**864/864 reps，合格 769，gen4 `565470cf26c16d01`**（与 Phase 2 同一台，否则跨域对比不成立）。
覆盖 **13/17 = 76% ≥ 前登记阈值 67%** ⇒ 可判。

**型 I：两域均受控**（hearing 0/15 · personal_finance 0/14）⇒ 结局④不适用。

| domain | primary | sensitivity | Manski 界 | 判决 |
|---|---|---|---|---|
| **personal_finance** | 3/13 (p=0.0245) | 3/13 (p=0.0245) | [0.200, 0.333] | **FAILED，两套一致** |
| hearing | 2/11 (p=0.102) | 4/13 (p=0.0031) | [0.133, 0.400] | **INDETERMINATE** |

合并两域：5/24，`P(≥5 | α=.05) = 0.00597`。

**hearing 判 INDETERMINATE 是按前登记规则**（两套分析集不一致），不是挑好看的那套。它的分开**率** 18–31% 与 Phase 2 的 27% 同量级，是 n 小导致功效不足，**不是反向证据**。

### 判决：前登记结局①支持，但表述必须精确

> **B1 的词面不变性失败，在一个与听力毫无关系的域（个人财务）独立复现**，两套分析集一致，Manski 下界 0.200 远高于不变性期望 0.05。

叠加 Phase 2 已确立的 hearing 域失败（7/26，p=0.00022）⇒ **这不是听力语料的特性**。
`semantic_form_invariance = FAILED` 的适用范围从单一 source_family 扩到**至少两个互不相关的 domain** ⇒ 更像 **instrument property**。

**明确不宣称**（写进 artifact，不只写文档）：
- 只测了 **2 个** domain，`across_domains` 仍**非** ESTABLISHED
- hearing 子集本轮 INDETERMINATE，**不得**拿 Phase 2 的结果去填这一格（不同轮次、不同盲验强度）
- 两轮 `blind_rule_check` 违规率**不可互比**（判官不同，见下）

### ★ 中途那次「不出结论」

跑到 552 reps 时覆盖 **65%，差一个格**（阈值 67%）。当时两域各有 5–8 个完整不变性 base，数据已经很像样。

**没有出结论。** 跑满后 personal_finance 是 3/13、hearing 变成两套分歧——若当时按 65% 出结论，给出的会是一个**没有 INDETERMINATE 这一格**的干净故事。

这就是前登记覆盖线的全部价值：它在那一刻拦住的是我自己。

---

## 19.5.29 [MEASURED 2026-08-24] 判官本身要被检验：两判官对照与三家族对照

阿里云订阅到期（报错从 `1-week quota exhausted` 变为 `Access to model denied`）后接入 DeepSeek。
★ 它**不替代** G1/G2——只有一个家族，撑不起「两个生成器」这个 facet。它补的是一个**更好的位置**：真正独立的第三方盲验者（≠G1 千问 · ≠G2 GLM · ≠测量模型 MiniMax-M3）。

### 两判官对照：同一批 Phase 2 刺激

| 判官 | 违规率 |
|---|---|
| 交叉家族（验证者=另一个生成器）| **3/158 = 2%** |
| 独立第三方 DeepSeek | **43/158 = 27%** |
| *对照：Phase 2B 的 DeepSeek* | *51/150 = 34%* |

⇒ **差距主要来自判官，不是刺激**（27% vs 34% 只差一点）。Phase 2 的 2% 确实被共享先验放水——正是当初写进代码的那条已知限度被实测坐实。
⇒ **两轮 `blind_rule_check` 不可直接互比**，已写进 `not_comparable_to` 字段。

★★ **但最有价值的是这一行**：DeepSeek 在 Phase 2 上 **B1 违规 0/31**（交叉家族 1/26）。
**最严的判官也认定这批 B1 变体确实「内容与处境未变」**，而 CCE 仍判 7/26 分开 ⇒ `SURFACE_SENSITIVE` **被加强，不是被削弱**——它不是刺激污染造成的假象。

A3 在 DeepSeek 下 19/32 判违规，但主要是**标尺不同**：理由多为 "shifts the situation but still **implies** the speaker's goals"——规则写的是不得**命名**（name），DeepSeek 按不得**暗示**判；另有 B2 违规实为**弯引号 vs 直引号**（`What’s` → `What's`），我的机器检验归一化时抹掉了，它没抹。

### 三家族 proxy 对照：0.000 会不会是共享先验？

`SURFACE_SENSITIVE` 的关键佐证是「B1 那 7 对盲评 `P(DIFFERENT)=0.000`」——而那 760 次**只有千问+GLM 两个家族，且都在阿里云上**。用 DeepSeek 复核 380 次：

| 臂 | qwen | glm | **deepseek** |
|---|---|---|---|
| L0b（逐字相同）| 0.000 | 0.000 | **0.000** ← 阳性对照三家全过 |
| **B1** | **0.000** | **0.000** | **0.000** |
| B2 | 0.000 | 0.000 | 0.000 |
| A1 | 0.469 | 0.766 | 0.594 |
| A2 | 0.656 | 0.859 | 0.703 |
| A3 | 0.984 | 1.000 | 0.953 |

★ **关键在 A1 那一行**：三家分歧不小（0.469 / 0.766 / 0.594）——它们**不是在机械复述同一套先验**。正因为在有分歧处真的分歧，**B1 上三家一致判 0.000 才有分量**。
★ 另一条反证：**同一个 DeepSeek 在盲验那轮与交叉家族差 13 倍**——它不是「什么都点头」的判官。
★ 剂量序 A1<A2<A3 在**三个家族**里都成立，而 CCE 的 T 仍是 0.18 ⇒「T 不映射到被感知的差异程度」再获独立支持。

### ★ 纪律：换判官只能是事后敏感性分析

DeepSeek 是更强的判官，**但没有拿它重定 Phase 2 的 primary**。Phase 2 前登记的验证者是交叉家族——**看到结果后换验证者重定 primary 就是事后改判据**。
正式件恢复为 `blind_verify_frozen.json`(CROSS_FAMILY)；DeepSeek 另存 `blind_verify_deepseek_posthoc.json`。测试强制正式件 `mode` 必须仍是 `CROSS_FAMILY`。
proxy 同理：前登记是 qwen+glm，原件另存 `llm_proxy_anchor_qwen_glm.json`。

---

## 19.5.30 [MEASURED 2026-08-24] 资格闸：精度达标，但集中度旗标拦住全量 ADOPT

真人原文 U = 9/256 = 3.5%，**看着达标**；但精确单侧 95% 上界 **6.05% > U_max 5%** ⇒ `ADOPT_PENDING_PRECISION`。
x=9 时 n=311 → 上界 0.049955（过）；n=310 → 0.050114（不过）。⇒ 再收 **55** 个。

**纪律：固定 n、只看一次。** 固定-n Clopper–Pearson **不是**为 optional stopping 设计的——边跑边看上界、一过 5% 就停，报出来的 95% 就不是 95%。

**结果**：新增 56 reps **零不合格**。合并 **n=312 · U=9 = 2.88% · 上界 0.04980 ≤ 0.05 ⇒ 精度闸过**。
★ 但判决是 **`ADOPT_WITH_RESTRICTIONS`**——`CONCENTRATION_FLAG` 触发。

**旗标成因干净可解释**：base `3fb58419ad8f` **8/8 全不合格**，而它是一份 **Samsung Newsroom 链接罗列贴，不是个人表达**。8 次里 **6 次是合法弃权** `no_inferable_subject`——**仪器正确地说了「这里没有可推断的主体」**。
⇒ 集中度来自**内容类型**，不是对某类人的隐性偏倚。除它之外 311 reps 里只有 1 个不合格。

**一条没走的捷径**：剔掉那条链接贴后 n=304、U=1=0.33%、上界 0.01551 ⇒ `ADOPT`。数字很漂亮，**但没当判决**——**看到结果再决定剔谁，就是 selection-on-outcome**。它只作为事后诊断存进 artifact，且测试强制它自带「不得当正式判决」的警告，并要求**正式判决不得等于事后剔除后的判决**。
正确修法：**下一轮新开前登记**，把「链接罗列/无个人表达的汇总贴」写进 eligibility 排除项；**不许回头改本轮 frame**。

---

## 19.5.31 [2026-08-25] gen4 当前总账

### 已确立

| 结论 | 证据 |
|---|---|
| 型 I 受控 | 0/29（Phase 2）+ 0/15、0/14（Phase 2B 两域）|
| 分辨率 profile | 中位 0.0315，跨 **7.5 倍**，与长度无关 ⇒ `ESTIMATED_SCOPED`（`delta_resolution` 仍为 `None`）|
| 灵敏度成立 | A 臂 `P(T > 同 base 零参照)` = 1.0 |
| **词面不变性失败** | 两个互不相关 domain 均复现 ⇒ **instrument property** |
| **T 不映射到感知差异** | CCE 单调性 0.18 vs 盲评 0.81（三家族全成立）|
| 资格 | n=312，上界 0.04980 ⇒ `ADOPT_WITH_RESTRICTIONS` |

`SURFACE_SENSITIVE` 的**五层独立支撑**：两个独立判官都判 B1 变体合规 · 三个模型家族盲评都说「处境没变」· Manski 无假设下界 0.226 · 二项检验 p=0.00022 · 跨域独立复现。

### 仍然不知道的（如实列出）

- **语义 SESOI**：`BLOCKED_EXTERNAL_ANCHOR`，需 ≥3 名独立真人评审员。LLM proxy 采了 1140 次三家族，**永远解锁不了**这一档
- **`across_domains`**：仍**非** ESTABLISHED，只测了 2 个 domain
- **hearing 子集**在 Phase 2B 判 INDETERMINATE，要补需**新开前登记**
- **度量 bake-off**：已剪掉「去公共成分」候选；其余候选需**新数据**确认（Phase 2 只算 metric-development set）
- **`EXPLICIT_CUE_POSITIVE_CONTROL`**：原 Axis A 降级后的用途，未跑
- **因果**：`CAUSAL_CAPABILITY.max_grade = DESCRIPTIVE`，结构性不可识别，未变

---

## 19.5.32 [MEASURED 2026-08-25/26] 判官的更正、2×2 解耦、within-base 重分析、被撤回的生产建议

### ① 判官对照的两处归因错误（我自己的，已更正）

`tests/data/phase2/inter_verifier_three_way.json` · `★★CORRECTION_2026-08-26`

| 我写过的 | 实际 |
|---|---|
| 「GLM47 作为判官偏弱，31% 不按格式作答」 | **全部是 HTTP 429 限流**（error 字段逐条可核）。降并发到 2 + 429 退避后，Phase2 **158/158**、Phase2B **150/150**，零 UNPARSED |
| 「两个独立判官一致度基本等于随机」 | kappa≈0 对，但**原因不是随机分歧，是零方差**：GLM 在 Phase 2 上 **158/158 全判 FOLLOWS**。永远说「合规」的判官按构造 kappa 就是 0 |

第一条是**把基础设施问题读成了判官能力** —— 正是我在别处一路在防的那类错。

**精确状态（比「分歧」更糟）**：违规率 交叉家族 3/158=1.9% · GLM-Phase2 0/158=0.0% · GLM-Phase2B 2/150=1.3% · **DeepSeek 27.2%–34.0%**。
⇒ **只有一个有分辨力的判官（DeepSeek），且无法验证它**。两个有分辨力的判官分歧至少说明题难；只有一个，意味着**所有 primary 划分等于一家之言**。

**教科书式的一对**：交叉家族 vs GLM47 一致率 **98%** 而 kappa = **−0.010** —— 两个判官都几乎从不说 VIOLATES，一致率高得没有任何信息量。这就是为什么必须报 kappa 而不是一致率。

**headline 反而更强了**：B1 干净这一条是**最严的那个判官**给出的 —— DeepSeek（整体违规 27–34%）在 B1 上 Phase2 **0/31**、Phase2B **2/30**。宽松判官说「干净」不提供信息；**严格判官说「干净」才提供信息**。

**被削弱的**：A 臂（尤其 A3）的 primary 划分。DeepSeek 判 A3 **19/32 违规**而无任何独立判官可复核。逐臂一致率（更正后 Phase2 DS vs GLM）：B1 **100%** · A1 81% · B2 74% · A2 69% · **A3 41%**；Phase2B：B1 91% · B2 88% · A2 58% · A1 53% · **A3 38%**。
⇒ **盲验可信度是臂类型依赖的**：「内容是否相同」（B 臂，事实题）判官高度一致；「处境变了几分」（A 臂，判断题）判官崩溃。

**前向规则修订**：「至少两个家族并报 kappa」**不够** —— 还须先检验**每个判官是否有分辨力**（违规率既不接近 0 也不接近 1）。**零方差判官不计入一致性证据。**

### ② 2×2 解耦：稀释是主因，不是长度

`tests/data/length_vs_dilution/verdict.json` · gen4 `565470cf26c16d01` · 192 reps / 142 qualified

| cell | 总长 | 占比 | base字符 | 不合格 | 该 base L0 基线 |
|---|---|---|---|---|---|
| A 短·密 | 1459 | 0.69 | 1004 | 5/24 = **21%** | 4/24 = 17% |
| B 短·稀 | 1457 | 0.32 | 459 | 23/24 = **96%** | **0/24 = 0%** |
| C 长·密 | 2954 | 0.62 | 1841 | 5/24 = **21%** | 0/24 = 0% |
| D 长·稀 | 2976 | 0.31 | 928 | 13/24 = **54%** | **0/24 = 0%** |

- **长度主效应**：~1500 → 58% vs ~3000 → 38%，Fisher **p=0.065，不显著且方向相反**
- **占比主效应**：高~65% → 21% vs 低~31% → 75%，Fisher **p<0.00001，显著**
- 最干净的一对是 A 与 B：**总长几乎相同**（1459 vs 1457），只有占比不同（0.69 vs 0.32）⇒ 21% vs 96%

**必须报的残差**：B 与 D 占比几乎相同（0.32 vs 0.31）却是 96% vs 54% ⇒ **占比一个人解释不了**，个人内容的**绝对量**也在起作用，而本设计没把二者分开（固定总长与占比 ⇒ base = 总长 × 占比，三者不独立）。

**最刺眼的一条**：B 与 D 的 **L0 基线都是 0%** —— **那段 450 字符的个人文本单独跑完全没问题，加上 1000 字填充后 96% 读不出。** 不是「个人内容太少」，是**非个人内容的存在本身**在压制读出。

**功效告诫（前登记已写死）**：每格 6 个 base。长度主效应不显著**不得**读成「长度无影响」。

### ③ within-base 重分析：0 次调用，比横截面回归更强

起因是 owner 的批评「你这总是调用，不是错这里就是错那里在这里瞎猜」。外审判定：我数据里**已有**比回归更强的证据没用上 —— **within-base intervention**（同一条文本自己跟自己比），而我却在琢磨怎么把回归系数估准。

前提逐条核过：24/24 的 PAD 臂确认为同一 base 的**严格前缀扩展**。

**结果：变差 17 · 持平 7 · 变好 0**（n=24），符号检验单侧 **p = 8×10⁻⁶**。
逐 cell 中位增量：A 短·密 **+0%** · C 长·密 +25% · D 长·稀 +62% · B 短·稀 **+100%**。

**为什么更强**：配对把 base 消掉了 ⇒ **不需要任何关于 base 长度的假设**，也不受聚类问题影响（外审指出我按 192 reps 算 SE，而独立 cluster 只有 24 个 base）。**没有一条文本变好。**

⇒ 横截面 logistic（β_base −1.034 / β_pad +1.214）降级为 **exploratory association**。r(base,pad)=0.001 只说明无线性共线，**不说明** SE 正确、重复测量独立、函数形式正确。

一处如实记的运气：设计支撑点 n_unique(base_chars, pad_chars) = **24**（外审阈值 ≥12，通过）—— 但这是**运气**。我按「最接近目标长度」挑真人文本，各条实际字符数天然不同；我当时**并没有把「支撑点数」当成要满足的条件**。（这正是 §19.5.33 那道门要制度化的东西。）

### ④ 被撤回的生产建议

**彻底撤销**我此前给的「输入 >1500 字符则截断/降级」。

- **为什么当时错**：那一轮**长度与占比混杂**（填充按 base 成比例加），我当时自己记下了这处混杂却仍据它给了建议
- **为什么截断会主动帮倒忙**：截断**不提高个人内容占比** —— 它按位置砍，而稀释是**成分**问题。在 B 那种情形（450 字个人内容 + 1000 字产品规格），截尾只会砍掉更多内容，占比不变甚至更差

**同时禁用**的四个数字门槛：`total_chars > 1500` · `personal_share < 0.3` · `pad_chars > 1000` · `personal_chars < 500`。
现有证据**不足以**把这些数字升级成稳定的 production threshold。⇒ 闸必须是**结构性**的，见 §19.5.33。

---

## 19.5.33 [2026-08-26/27] 两道零调用的闸：投料前设计门 + 测量前结构闸

本节两样东西**都没有花任何 API 调用**，且都直接源于 owner 那句批评。

### ① `scripts/design_preflight.py` —— 投料前设计门

外审的判定是：**「你缺的不是再做一次实验」**。三轮长度实验每轮都是跑完才发现设计缺陷，而其中两处纸面上就能算出来，「理论上都应该在 **0 次 API 调用阶段被 CI 拒绝**」。

六道 gate：① 代数依赖 ② 孤立对比 ③ 设计矩阵秩与条件数 ④ 支撑与正性 ⑤ **实验单位审计**（pseudoreplication）⑥ **合成结局反测**。不过则非零退出 = 禁止产生任何 API job。

**拿我自己犯过的两个错做验收**（`tests/test_cce_design_preflight.py`）：

| 设计 | 判决 | 命中 |
|---|---|---|
| 第一轮（填充按比例加） | FAIL | g3 **秩亏**（base 在设计里恒定）· g6 **合成还原失败** · g2/g4/g5 |
| 第二轮 2×2 | FAIL | g1 **结构不可分辨**（free_dof=2，却声明估 4 个 estimand）· g2×3 · g4 · g5（声称 n=192 而单位只有 24）|
| 正交干净设计 | **PASS** | — |

第三行不是凑数：只测「坏设计会红」**无法区分「门有判别力」和「门永远说 FAIL」**。另加一条归因测试——只谎报 n 时必须**只**触发 gate 5。

gate 6 是外审最推荐写进 CI 的一条：用**已知真值**造 outcome，看计划中的分析能否还原。第一轮设计在「只有 base 有效应」的合成世界里估出 **+0.00**（因为 base 根本没变）——**连已知答案都还原不出的分析，不该用来分析真实数据。**

**中途修掉门自己的两个洞**：
- gate 3 条件数原先在**未归一化**的列上算 ⇒ 纯量纲差异（base~10³ vs 截距 1）被误读成共线性，干净设计条件数 **4011** 被硬拦。按 Belsley 先做列 L2 归一化 ⇒ **5.23**。修掉这个假阳性后 2×2 仍被 g1/g2 拦下 ⇒ **印证了「结构性 gate 不能由数值检查替代」**（此前只是文件里的一句主张）
- gate 6 写死取 `formula_terms[1]`，单变量设计直接 IndexError。**会崩的闸比判错更糟** —— 在 CI 里像工具坏了，会被绕过去

第二个洞是**拿这道门去审我自己拟议的下一个实验时撞出来的**。那个实验（同一 base 过闸 vs 不过闸，各 8 draw）随后被 **gate 5 判为伪重复**（1 个实验单位却声称 n=16）⇒ **该实验没有做**。真要做需跨 13 个 base，不是 1 个。

### ② `scripts/cce_structural_gate.py` —— 测量前结构闸

补的是 §19.5.32 ④ 留下的缺口：闸必须测**成分**而不是字符数。

**判据只有一条**：对每段问「**能不能证明这段不是作者自己写的话？**」证得出才摘，证不出一律保留。
⇒ 误判方向必然是**漏摘**（退化回原行为），不是错摘。`PERSONAL` 只用于报告，**不参与去留决策** ⇒ 结构上**不存在可调阈值**。
`subject_text = PERSONAL + AMBIGUOUS − NONPERSONAL`（保序）；摘完无任何 word char ⇒ `ABSTAIN_NO_INFERABLE_SUBJECT`，**零 API 调用**。

**真实语料实测**（`frame_reddit_20260819.json`，367 条）：混合型 **13 条（3.5%）**被摘除引用/链接；零调用弃权 **0 条**。
⚠️ **如实记录**：弃权分支在本语料**没有实例**，只由构造样本守住，测试里显式写明并把这两个数钉成断言 —— 规则改动一旦改变真实语料上的行为就会红。

**★ 已实现的是登记规格的一个子集，差额必须写明**：
§19.5.32 ④ 登记的 NONPERSONAL 类别是**语义类**（产品规格 / 条款 / 手册 / 操作步骤 / 目录 / 日志）。当前确定性 segmenter 只覆盖**标记可证**的子集 —— 代码围栏、引用标记（含 HTML 转义 `&gt;`）、整行只有链接。
那个 8/8 失败的 base `3fb58419ad8f` 的规格段**恰好带 `&gt;`**；不带标记的产品规格段**当前漏摘**，仍只能靠模型自己的整篇弃权兜底。这是一个**已知缺口**，不是已解决项。

**★ 与仪器身份的关系（别混）**：
- `s1_prompt_sha256` 哈希的是**模板**（`_stage1_template`）。结构闸**一个字都不碰模板** ⇒ sha 仍是 `eadcdcdac46a5180` ⇒ **不换仪器**，gen4 那 311 样本的资格标定仍适用。测试直接钉住这个哈希
- 但**制备不同的读数同样不可直接比较** ⇒ 另立 `preparation_id` + `assert_same_preparation`，与 `assert_same_instrument` 同形；无该字段的历史读数归入 `prep_raw_unfiltered`

> **一般化的一条**：改「送进去的文本」= 换**样品制备**（不换仪器）；改「prompt 模板」= 换**仪器**。两者都让读数不可比，但**作废的东西不同** —— 前者不作废仪器标定，后者作废。

**中途修掉的一个洞**：markdown 链接原先被整条剥掉，把**锚文本**也吞了。真实反例 `f062a35fb9d2`：`[Look, I know the camera angle is simply weird, but this arm is SHORT!](url)` —— 锚文本是作者原话，被当成 link-only 整行摘掉，**直接违反我自己写的判据**。改为只剥 URL、保留锚文本。
代价：`3fb58419ad8f` 的 `- [新闻标题](url)` 也被保留 ⇒ **不再零调用弃权**（我的头条数字从 1/367 掉到 0/367）。**没有**为保住那个结果去加「列表记号 = 引用条目」的规则 —— 那是照着想要的结论调规则。

### 本节的通用纪律

1. **一道从来没被看见拦下过任何东西的检查，与没有检查等价。** 守卫测试必须同时有：已知坏例 FAIL 且命中**指定 code** · 已知好例 PASS · 只改一个缺陷时**只**触发对应那道门
2. **新工具的第一个用户应该是自己的下一个提案。** 两个洞里有一个就是这么撞出来的，一个不该做的实验也是这么拦下的
3. **不为保住一个漂亮结果去加规则。** 规则要能独立于它产生的结论而成立

---

## 19.5.34 [2026-08-27 / 2026-09-01] 外部评审第五轮；链路 15 段补齐；四处「结论≠执行」

### ① 外审第五轮（三个我判不了的问题）

`scratchpad/cce_three_open_questions.md` · ChatGPT Pro 深度检索 11m51s / 28 站

| 问题 | 判定 |
|---|---|
| 结构闸的语义类缺口，要不要上分类器 | **不要接进生产删除链**。理由不是「LLM 做不好」：① 误删真实个人表达的损害高于漏摘 ② 自然语料上**没有独立 span 级参考标准** ③ 分类器是新的测量部件，需自己的信度/漂移/弃权体系 ④ 它的错误发生在 CCE **之前**，下游无从知道吃到的是被错切的样本 |
| `preparation_id` 与资格标定 | 我的「换制备不换仪器 ⇒ 标定仍适用」**表述太宽**。完整结果对应 **measurement procedure = preparation + instrument + qualification policy**（ISO 把 extraction/separation 算在内）。**但不必全部重跑**：逐字节未变的 item 精确复用（`EXACT_INPUT_IDENTITY`），只重跑被改动的，规模 = 资格 frame 与改动集的**交集**，不是固定 13 |
| 无真人能否建立语义 SESOI | **不能**。锚必须来自真人判断或真人可解释行为；CCE 自身 / 另一个 LLM / 多 LLM 共识 / 词面相似度**全部不行**。最小可行 **5 人 × 60 对**（不是 3×30），40 calibration + 20 holdout 拆开，Krippendorff ordinal alpha ≥0.80 且下界 ≥0.67 |

**唯一被判「该直接放弃」的**：继续增加 LLM 判官数量，试图在没有真人的情况下解锁人类语义 SESOI。

外审同时**不同意我把问题一整体挂起**：生产语义分类器挂起，但 **source-aware preparation 与 provenance contract 立即做**（上游若知道 segment 来源必须传，禁止先拼平再让模型猜）。

### ② 链路 15 段：从 11 段有实现 → 15 段全有实现且全有测试

此前 §48 图末尾那个 `↺` 是断的 —— MECHANISM 与 STRATEGY **连文件都没有**。

**P6 机制登记**（`scripts/cce_mechanism.py` + `config/mechanism_registry.json`）
判据用 §44.9 事先写好的那条：*每条 mechanism 记录都能追到 evidence_refs，且至少一次 replication；反向：造一条无 evidence 的 mechanism，注册必须被拒*。`register()` 是**闸**，拒五种：evidence 为空 / 指向不存在的文件 / ESTABLISHED 零复现 / 声称 preregistered 却无冻结件 / status 越界。

首批五条，证据均为仓库内真实 artifact：

| status | id |
|---|---|
| ESTABLISHED | `semantic_form_invariance_failed`（两 domain 复现 ⇒ instrument property）|
| ESTABLISHED | `dilution_not_length`（长度 p=0.065 不显著且方向相反，占比 p<1e-5）|
| ESTABLISHED | `causal_ceiling_descriptive` |
| TESTED | `mixed_content_interference`（pad 量/占比/语义类型未分离，故未升级）|
| **REJECTED** | `length_threshold_1500`（被 `dilution_not_length` 取代）|

两条自加的强制：**REJECTED 必须能登记且带 reject_reason + superseded_by**（被否决的方案不留档，下一个 agent 就会重做它 —— 本项目实际发生过）；**ESTABLISHED 必须带 falsifier**（说不出「什么结果会推翻它」的结论不是结论，是信念）。

**P7 生成物闸**（`scripts/cce_strategy_gate.py`）
接上三闸，并让「**不得引用未达标层的读数**」第一次可执行 —— 此前它无法执行，因为「未达标」没有可查询的定义。现在生成物用 `[[mech:<id>]]` 引用，`status != ESTABLISHED` 即拦，已否决的还会报出取代者。`check_boundary` 缺席时如实标 `AVAILABLE_NOT_RUN`，**不冒充 PASS**。

### ③ 四处「结论写进记录 ≠ 结论进了执行队列」（同一天内）

§44.13 记过这句。2026-09-01 一天之内又撞四次：

1. **§44 八阶段重构写进文档** —— 我连续多周只读 §19.5 尾部并往后追加，从未打开 §44/§45。owner 问「还剩什么」时给的清单只有测量线欠账，八阶段一个字没提
2. **「s5–s8 已退役」写进文档与记忆** —— 而 `.github/prepare.py` 一直允许 `mode=post`，代码里那条路是通的（该误用**复发过三次**）
3. **E0–E4 判为「最值钱的可迁移件」** —— CLAUDE.md / cce-engine / skills 三处命中 **0**，且装错了端
4. **`design_preflight` 与其守卫测试都在** —— 但**没有任何 workflow 调用它**；本仓库自己记着「新 gate 不接 CI = 形同虚设」

四处均已修：§44/§45 已纳入视野并逐 Phase 对代码核过 · 旧链从入口删除并加守卫 · E0–E4 已装到本端并配了确定性校验器 · `design_preflight` 已接到 `probe.yml`（唯一持有 API key 的入口）且在密钥注入**之前**。

### ④ 本轮补的测试与它们各自抓到的东西

| 补的 | 抓到的 |
|---|---|
| `test_cce_style_gate` | 旧文风闸**判别力 ≈ −1%**（拦真人 69% vs 拦我方稿 70%）—— 它不是闸，是近乎无差别的拦截器。重标定后 **+55%** |
| `test_cce_consistency_check` | 四类配置↔代码漂移逐类注入，**全部见红** |
| `test_cce_outbound_guard` | `import cce_outbound_guard` 抛 NameError，**该缺陷记在库里三周**（命令行走另一条路，生产没暴雷） |
| `test_cce_platform_adapter` | subreddit 不得冒充 adapter id；`observed_at` 必填 —— 没有观测时间就无法判断 surface 是否过期，那正是「冻结动态人群」的入口 |
| `test_cce_mechanism_registry` / `test_cce_strategy_gate` / `test_cce_preflight_wired` | 见 ②③ |

### ⑤ 两条方法学，来自本轮反复踩的坑

**判别力必须自己成为断言。** 只测误杀率会奖励把闸放松到关掉；只测拦截率会奖励把闸拧死。守 `拦目标 − 误杀本底 ≥ X` 才守得住。给一个二分类闸重标定前，**先量它在两个集合上的率** —— 若两率接近，它没有判别力，调阈值是白调，要换判据不是换数。

**断言要锚在可执行的那一行，不是散文。** 对 YAML/配置/Markdown 做断言时子串存在性几乎总是不够 —— 同一个符号极常出现在注释里，而**注释不执行**。本轮两次栽在这上面（`"design_preflight.py" in WF` 命中我自己写的注释；`WF.index("MINIMAX_API_KEY")` 命中文件头注释）。

CI 测试文件下限 33 → **42**。

---

---

## 19.5.35 [MEASURED 2026-09-01] §44 八阶段收口：链路 15/15，Phase gate 8/8，但**内容已建只有 6/8**

提交 `2dd8111` · `90c00cb` · `ac928b3` · `88bc541` · `d797a65` · `7df435b` · `225cfb8`（67 文件 +6863/−167）。
50/50 测试绿；四条独立闸（本体迁移 / Core 边界 / Archive / 链路符合性）全 PASS，均已接入 `cce-submit.yml`。

### 一、★ P1 的验收标准本身写错了 —— 不是没达标

原 gate：「旧名在生产路径上 grep 命中 = 0」。外部裁决（网页 GPT Pro，思考 3m16s）判定**这条标准写错了且不可达**：
它把四种本质不同的情况混成了一个文本搜索结果 —— 仍在使用的旧本体 / 冻结证据里的历史字段 /
必须保留的黑名单哨兵 / 与本体无关的同名符号（`segment(text)` 是文本跨度，不是人群分群）。

**实测又撞出第五类，外部裁决也没预见到**：被测语料自己的英文单词。
`tests/data` 里真人写的 "susceptible individuals" 出现 60+ 次 —— 那是 payload，不是本体使用。
第一版闸把它判成活跃旧本体依赖，**127 条假阳性**。

⇒ 闸按 surface 分扫描模式：`EVIDENCE` 只扫 JSON object key，**绝不扫 value**；
`.py` 出现在未声明的面上直接红（`UNDECLARED_CODE_SURFACE`），防止新代码靠换目录逃闸。

新判据：

```text
P1_PASS = canonical_v2_writes_only
          AND active_legacy_dependency == 0
          AND unclassified_occurrence == 0
          AND legacy_envelope_rejected
          AND frozen_artifacts_replayable_read_only
          AND negative_tests_observe_failure
```

**grep 只能是 inventory，不能是 verdict。** 判据不是「搜不到旧名」，而是
「搜到的每一处旧名都有唯一、明确、可审计的合法类别」。

状态写作 **`P1 = DONE_WITH_LEGACY_CONTAINMENT`**，不写模糊的 DONE。
冻结件 65 个 SHA-256 与迁移前**逐字节一致**（另新增 1 个桥接产物文件）。

### 二、制备桥接（外部裁决判为真正的 P0，优先于 P2）

补上第三个身份分量。实测那个洞：

| | raw 制备 | prep_struct_v1 |
|---|---|---|
| `instrument_hash` | `eab1a35666b33996` | **相同** |
| `qualification_policy_hash` | `b41ef5217a77d311` | **相同** |
| `measurement_procedure_id` | `mp_24a018c806426971` | `mp_cdf545a9d3058bc2` ← 只有它能分辨 |

换了送进仪器的文本，两个旧哈希都不变，上层看到「同尺同解读」就照常对账。

三层拦截（缺一层就能绕过去）：typed `PreparationMismatchError` /
结果 schema 必带 `comparability.status` / manifest 混制备且非 `bridge_mode` ⇒ `complete=False`。
测试里演的就是「下游 catch 掉异常之后，照样拿不到合法 production artifact」。

**gen4 标定 frame 完整重建，复现历史记录 U=9/312，upper95=0.04980：**

```text
39 base  ->  37 EXACT_INPUT_IDENTITY (直接复用, 0 次调用)  ·  2 NONTRANSFERABLE
312 rep  ->  296 复用 (U=1)  ·  16 需重跑 (旧 U=8)
```

★ **旧 9 个 U 事件里 8 个落在 base `3fb58419ad8f`** —— 正是被新制备改动的两条之一。
改动组与未改动组事件率极不相同，**总体率绝不可直接搬**。

新制备下的资格闸只能给 Manski 区间：

| | U | upper95 | 假设 |
|---|---|---|---|
| 下界 | 1/312 | **0.01511** | 16 个重跑全 qualified |
| 上界 | 17/312 | **0.08061** | 16 个重跑全 unqualified |

**区间跨越 U_max = 0.05 ⇒ 不重跑那 16 rep 就判不了。**
禁止拿旧的 0.04980 冒充 `prep_struct_v1` 下的上界。代价 16 次投料，不是 312 次。

### 三、P2 六字段：全部落地且写进契约

契约 `cce_subject_window_contract_v1.json` 2.2.0 → 3.0.0，三个单窗口字段列为**必填**。

- `field_structure` —— 0 个模态报 `no_supported_mode`，不许把「没测出结构」说成「结构是一个」
- `mode_coverage` —— 分母写死 `known_member_count`，并显式 `not_denominator: target_population_size`
- `mode_activation` —— 恰好卡在 `min_mode_size` 上的模态必须进 `minimally_supported_mode_ids`
- `window_transition` —— ★ **这段逻辑本来就在**（`compare_population_projections` 的 events），
  只是从来没有以 P2 要求的名字出现在产物里。**「实现了」≠「契约上可被下游依赖」。**
- `field_drift` —— 成员集合变了必须 `confounded=true`：结构差里同时含「换了一批人」与
  「同一批人变了」，二者不可分
- `partition_projection` —— **没有抽样框一律拒绝投影**。这不是保守是算术：
  已观测 n 个成员在总体 N 中的占比，N 未知时无界。观测占比换个名字不是投影结果。
  实测有框时投影 2/3 : 1/3，确实不同于观测的 1/2 : 1/2（有反向断言钉住放大系数真的起作用）。

### 四、P3 / P5 / P4：把三条「一句话」变成可执行

**P3 = `GATE_ONLY_CONTENT_NOT_BUILT`。** 铁律 20 做成可执行：Core 4 个文件钉 sha256 +
`instrument_generation`，改 Core 而不换代 = 静默换仪器 = 红；把文件移出清单或塞进 Parser 清单蒙混，同样红。
**内容未建** —— 生产化 media ingest / 独立图像音频 ingest / 音源分离 / 说话人分离 / 韵律 /
mix metrics / 完整跨模态事件语义，逐条列在 `not_built` 里，不冒充 DONE。

**P5 = `DONE_WITH_RECORDED_LOSS`。** 实测结果不好听但这是真的：

```text
被引用的 GitHub run_id        32
本地有 artifact 的             0
远端还留着的                   0   (gh api actions/artifacts -> total_count = 0)
```

⇒ 这 32 个 run **已经不可重建，且追不回来**。§44 P5 担心的事不是将来会发生，**是已经发生过了**。
不假装能重建，只做三件能做的：如实登记损失（不留一份看起来完整的索引）· 今后每 run 落本地 ·
守住「机制证据不得引 run_id」。
★ 好消息且是重点：机制注册表 14 条 `evidence_refs` **全部指向本地文件，0 条指向 run_id**
⇒ Population/Mechanism 学习链本来就没建在会过期的东西上。闸把这条钉死。
本地尚存的 3 个 run 已落 `archive/`（26 个 artifact + 3 份 run manifest = 29 个文件），按 run_id 重建 + sha 校验全通过。

**P4 = `GATE_READY_NEEDS_API_BUDGET`。** 补上 §23 明写「不做这一步的 K1 等同于没有 K1」的那一步，
当场抓到真洞：原判据 `len({r["sha"]}) == 1`，8 份 manifest **全都缺** `text_sha256` 时集合是 `{None}`，
长度也是 1 ⇒ 闸打印「输入指纹唯一 ✅」而它一个指纹都没看到。
总判决碰巧是红（极差与 top-1 不达标），所以那行假绿三周没被发现。
**缺指纹 ≠ 指纹相同。** 现改为任一份缺 sha 即拒判（exit 2）。
判据也从 `main()` 抽成 `judge(rows)` 纯函数 —— 埋在 main 里的判据 CI 测不了，等于没有测试。

### 五、链路符合性核对：把对照表做成可执行的

`scripts/cce_chain_conformance.py` + `config/cce_chain_conformance.json`，已接入 CI。

```text
链路 15/15 已实现 · 15/15 已测
Phase gate 8/8 通过 (6/8 内容已建)
  ✓ P0 · P1 · P2 · P5 · P6 · P7
  ◐ P3 (只有 gate) · P4 (只有判据)
```

★ 显示上用 `✓` 与 `◐` 区分，不用同一个对勾 ——
**把「闸绿」显示成「内容做完了」，正是本项目栽过的那类假绿。**
半成品状态**必须**写 `why`（还差什么），缺 `why` 即红。
这张表自己有 7 条反向测试（含「真删一个实现文件」），全部实际见红。

### 六、[LESSON] 本轮新增的七条方法论

1. **一条 gate 可能本身就是错的**，不只是没达标。发现「gate 不可达」时，先问「这条判据写对了吗」，
   而不是先想怎么把它做到。
2. **突变测试必须先证明突变真的写进去了。** 本轮 N1 报绿，复核发现是替换串没匹配上的**空突变**；
   改对后立刻见红。一次没生效的突变，读起来和「测试是假的」一模一样。
3. **`git checkout -- <dir>` 管不了 untracked 文件。** 拿它做突变测试的 restore，
   把当轮的迁移工作也一起回滚了，白做一遍。
4. **macOS 没有 `timeout`。** 用它包住测试循环，42 个测试全报红 —— 是脚本坏了，不是测试坏了。
5. **假断言两连**：用裸字符串 `"http"` 判有没有网络调用（链接正则 `https?://` 会命中）；
   用方法名 `.get`/`.post` 判（`dict.get` 会命中）。改为只查 import 白名单 ——
   不导入网络模块就发不出请求。
6. **陈旧 `__pycache__` 会伪造突变结果。** 每一步突变前后都要清缓存，
   否则那个「红」可能来自上一次的字节码。
7. **反向测试自己必须写出被禁的词/id。** 因此需要 `NEGATIVE_TEST` 类别登记，
   且限定**只许出现在那一个文件里** —— 否则「登记一下」就成了绕闸的办法。


---

## 19.5.36 [MEASURED 2026-09-01] 两轮真实投料：制备桥接资格闸 **ADOPT**，K1 首次判定 **FAIL**

提交 `e88e31b` · `ccbb64d` · `36ad008`。MiniMax-M3，gen4 仪器 `565470cf26c16d01`，
共 **112 次调用**（48 + 64），INFRA 失败 0。51/51 测试绿，四条闸 PASS。

### 一、制备桥接重跑 —— `prep_struct_v1` 下资格闸 **ADOPT**

前登记 `tests/data/phase2/preparation_rerun_prereg.json` 跑前冻结；固定 n=16，只看一次。
唯一变量是 `text = structural_gate(raw)["subject_text"]`；仪器与资格协议一个字节不动，
context 与主面板/扩展块逐字相同。stage1-only（资格由 stage1 决定），48 次调用，154 秒。

```text
3fb58419ad8f   unqualified  8/8  ->  6/8    (链接堆帖子, 过闸摘掉 65% 字符)
421287e62d06   unqualified  0/8  ->  0/8

复用 296 rep (逐字节未变, 0 次调用)   U = 1
重跑  16 rep                          U = 6
──────────────────────────────────────────
raw 制备        U = 9/312   upper95 = 0.04980
prep_struct_v1  U = 7/312   upper95 = 0.04173   <= U_max 0.05  ⇒  ADOPT
```

跑前 Manski 区间 `[0.01511, 0.08061]` 跨越判决线，实测定点 **0.04173 落在区间内** ——
有断言钉住这一点：落在区间外就说明合并口径或区间算错了。

★ **范围限制（写进产物且有断言）**：不得读作「结构闸改善了整体资格率」。
改动只发生在 2/39 个 base 上，全部改善来自 `3fb58419ad8f` 那一条；
另一条原本就 0/8，制备后仍 0/8。**n=16 的组内变化不支持任何一般性机制陈述。**

★ 顺手修的错：桥接产物首版记的 `instrument_hash` 是 `eab1a35666b33996` ——
那是 `knot_n=9 / s1_pairing='paired'` 口径算出来的，**不是 gen4 面板的仪器**。
面板口径 `knot_n=5 / round_robin_over_3_s1_draws` = `565470cf26c16d01`。已改正并加断言。

### 二、P4 K1 首次真实判定 —— **FAIL**

前登记 `tests/data/phase2/k1_reliability_prereg.json`。**选文规则跑前冻结且与稳定性无关**：
「L0 四次历史重跑全部 qualified 且属 `analysis_sets.primary` 的 base 中取字典序第一」
→ `050f0f2403f7`（合格池 30/32）。
① 不能在「没有读数」的文本上测读数稳定性 —— 资格是可评的前提，不是结果挑选；
② 字典序第一与稳定性无关，排除按结果挑 base。

n=8 同指纹，每 rep = stage1(k=3) + stage2(n=5) = 64 次调用，198 秒。

| 判据 | 阈值 | §23 历史基线 | 2026-09-01 |
|---|---|---|---|
| 同稿重跑次数 | n ≥ 8 | 8 ✅ | 8 ✅ |
| 完全相同的读数对 | ≥ 6/28 | 0/6 ❌ | **0/28 ❌** |
| 单结权重极差 | ≤ 0.10 | 0.37 ❌ | **0.40 ❌**（最大项 `reward`）|
| top-1 结一致率 | ≥ 7/8 | 7/8 ✅ | **8/8 ✅**（全部 `pain_seek`）|

**四项里两项不达标 ⇒ K1 = FAIL。** 两项仍不达标，top-1 从 7/8 改善到 8/8。

★ **结论是分层的**：首结（top-1）稳定，绝对强度不稳定。
这正是**铁律 24**（九结 absolute intensity 与 relative composition 必须分离）
要求分开的那两件事 —— 本轮实测给出了那条界线的位置。
有断言钉住这个形态：「变成同进同退就说明重算错了」。

★ **范围限制**：本次 K1 只对「稳定合格的真人文本」成立，
**不**说明仪器在边缘文本（资格摇摆、混合内容）上的读数稳定性 —— 那是另一个问题。

### 三、§44.9 P7 那条反向测试终于可执行

> **7 Strategy** | …**且不得引用未达标层的读数** | 反向：喂一条引用了 K1 未达标读数的生成物，必须被拦

这条此前**无法执行** —— K1 只有判据没有判定，「达标没达标」查不到。现在可查了：

```text
[[knot:<key>]]                  首结层    -> 放行  (top-1 8/8 支撑)
[[knot_intensity:<key>=<v>]]    绝对强度  -> 拦下
[[knot_delta:<key>]]            跨稿比较  -> 拦下
```

§23 原话：「在 K1 达标之前，任何『A 稿 display 高于 B 稿』的说法都不成立。」
**缺 K1 判定时同样拦下 —— 缺判定不等于判定通过。**
实现在 `scripts/cce_strategy_gate.py::check_knot_readout_claims`。

### 四、进机制注册表

`knot_intensity_not_reproducible` = **ESTABLISHED**，两次独立测量支撑
（§23 历史基线：不同文本、较早协议；2026-09-01：gen4 n=8 同指纹）。
falsifier 写明「同仪器重做 n≥8 达标即推翻；换仪器（gen5+）不推翻本条，只说明新仪器另有性质」。
`downstream_enforcement` 指向生成物闸。注册表现 6 条（ESTABLISHED 4 / TESTED 1 / REJECTED 1）。

### 五、对照表：P4 显示成 ✗ 不是 ◐

`P4` 从 `GATE_READY_NEEDS_API_BUDGET` 改为 **`MEASURED_NOT_PASSING`**。
断言强制 `why` 里写明：**gate 命令退出 0 验的是「判定机制可用且判决可从原始行重算」，
不是「K1 过了」** —— 两者混为一谈就是假绿。

### 六、[LESSON] 本轮新增三条

1. **缺判定 ≠ 判定通过。** 闸在找不到判定文件时必须拦，不是放行。
2. **闸必须由判定驱动。** 测试里伪造一个 PASS 判定，验证它确实会放行 ——
   恒拦的闸和恒放的闸一样没有信息量。
3. **既有测试钉住产物形状是对的。** 我给生成物闸加 `knot_readout_claims` 分项时，
   P7 的测试如实见红。正确做法是跟上它并写明为什么加，不是绕过它。


---

## 19.5.37 [MEASURED 2026-09-01] K1 极差 0.40 的根因 —— 问题本身问错了

提交 `51306ac`。270 次调用，20 rep × 12 draw，693 秒，零失败。
前登记 `tests/data/phase2/k1_rootcause_prereg.json` 跑前冻结（四个互斥假设 + 判决线）。
**全部分析跑在闸前 `draw_ledger` 上。**

### 一、★ 问的是「抽样噪声 vs 尺度无锚点」，答案是**两个都不是**

```text
每 rep 都点火的 6 个结   变异系数中位数  0.31
稀有结 3 个             变异系数中位数  6.27      ← 相差 20 倍
```

K1 报的 0.40 来自 `reward` —— 它在 10 个 rep 里**只点火 2 次**。
`median(非零)` 对「没点火」返回 `0.0`，这个 0.0 被拿去和 0.42 算极差。
**那是出现率现象，不是强度现象。** 剔除后 `reward` 的纯强度极差是 **0.17**。

| 结 | 点火 rep | R_all | R_fired | 出现率驱动 |
|---|---|---|---|---|
| reward | 2/10 | 0.420 | 0.170 | **60%** |
| inertia | 3/10 | 0.380 | 0.230 | **40%** |
| itch | 1/10 | 0.100 | 0.000 | **100%** |
| 其余 6 个 | 10/10 | 0.085–0.250 | 同 R_all | 0% |

### 二、四个假设

| 假设 | 判定 | 依据 |
|---|---|---|
| H1 抽样噪声 | **全局拒绝** | n 5→12 极差反而**变大** 2.1 倍 —— 更多 draw = 稀有结更多机会点火 |
| H1 **限常火结** | **成立** | n 效应比值中位数 **0.592**，纯零均值噪声理论预期 √(5/12)=**0.645**，几乎正中 |
| H2 估计量缺陷 | **拒绝** | 见下 |
| H3 s1 传播 | **拒绝** | 冻结 s1 后极差**普遍更大**（6 个常火结里 5 个变差，中位比 1.476）|
| H4 尺度无锚点 | **在常火结上被排除** | 若无锚点，加大 n 不该起作用；实测起作用且幅度正中 √n ⇒ 存在可收敛潜值。**不覆盖稀有结** |

★ 同一个假设在两个子集上结论相反。**不分层就会得到一个错的单一答案。**

### 三、★ 我前登记的 C2 有两个洞，如实降级

1. **可被恒定估计量满足**：`median(含0)` 把 `reward` 序列压成恒 0，极差按构造 = 0。
   那不是改进，是把信号删掉。
2. **极差不是尺度无关量**：`mean_all(含0)` 把值整体缩小 6 倍，极差当然小。
   按「极差/均值」归一化后 `mean_all` 比值 **0.867 > 0.65** ⇒ 优势消失。

两个洞都是事后发现的，C2 的结论按加守卫之后的口径给，**不是原前登记口径**。
库里的元教训「统计量退化 → 返回有利数」——**这次我又踩了一次**。

### 四、根因：不是新发现

> **稀有结的点火/不点火二值不稳定**，经 `median(非零)` 把缺席编码成 `0.0` 后混进极差。

这与 **2026-08-18 已确立的 P1a 根因「support 闸二值化」是同一个根因** ——
两个统计量（布尔结集翻转 / 单结极差）穿着不同的衣服。
处方也早就有了：**停止把缺席编码成 `intensity=0.0`，分开报 `occur/n` 与 `intensity|fired`。**

本轮相对 2026-08-18 的**新增量**只有一条：
「加大 n」既不是通解也不是错处方 —— 对常火结的纯强度有效（√n），对稀有结的极差**反而更差**。
**适用面必须按点火率划分。**

### 五、★ 不推翻 K1 的 FAIL

剔除全部出现率成分后，最大纯强度极差仍是 **0.25（`audit`）> 0.10**。
所以 K1 的 FAIL **不是**判据编码造成的假阳性 —— 但 **0.40 这个数字是**。
按 √n 外推压到 0.10 需 **n ≥ 75**（生产 n=5 的 15 倍成本）。
⚠️ 这是**两点外推**（n=5→12），不是标定，**不得当作承诺**。

### 六、边界

- **诊断不是判据。** `D_var` 正是因「闸前算、闸后判」被否决；要当判据必须另走前登记。
- experimental unit = **1 个文本**，零复现 ⇒ 机制 `k1_range_is_occurrence_not_intensity`
  登记为 **TESTED** 不是 ESTABLISHED。
- `s2_n` 5→12 **就是换仪器**（`0cf97f605ced04fc` vs 生产 `565470cf26c16d01`），
  本批不得与生产读数合并；但 n=5 前缀严格复现生产的 round-robin 分配 ⇒ 前缀可与生产口径对话。

### 七、[LESSON] 本轮新增三条

1. **极差不是尺度无关量。** 跨估计量比较之前必须先归一化，
   否则「更小的极差」可能只是「更小的值」。
2. **任何「最小化某个散度」的判决线都可被恒定估计量满足。** 前登记时就该带退化守卫。
3. **先分层再下判断。** 全局比值 2.1 说 H1 拒绝，限常火结比值 0.592 说 H1 成立 ——
   不分层的单一答案是错的。


---

## 19.5.38 [MEASURED 2026-09-02] K1 判据修正 —— 缺席不是强度 0，以及「只拆不补」被反例抓到

提交 `4917b48`。**0 次 API 调用** —— 在既有 8 rep 数据上重判。
处方来自 2026-08-18 已确立的 P1a 根因（support 闸二值化），**早于本轮数据**，不是拟合。

### 一、单结极差只在该结点火的 rep 上算

原实现 `dict(r["knots"]).get(k, 0.0)` 把**缺席**编码成 `intensity=0.0`，
再与真实强度值一起算极差。判据因此**非单射** ——
同时被「出现率翻转」和「强度漂移」触发，会**误判病灶**。

| | 最大极差 | 归因 | 该结点火 |
|---|---|---|---|
| 修正前 | 0.40 | `reward` | **1/8** |
| 修正后 | 0.39 | `display` | **8/8** |

**数字几乎没变，病灶完全变了。** 这才是修它的理由 —— 不是为了改判决。
另：点火 <2 rep 的结（`itch` / `reward`）标为「强度信度**未被测量**」，不是「很稳」。

### 二、★ 第一版只拆不补，把闸改弱了 —— 靠构造反例才发现

第一版的理由是「出现率不稳定由『完全相同的读数对』那一项兜住」。
**构造验证证伪了这个理由。** 造一个「出现率 4/4 翻转、强度恒定、top-1 不变」的仪器：

```text
n>=8 ✅ · 相同读数对 12/28 ✅ · 强度极差 0.0 ✅ · top-1 8/8 ✅   ⇒ 四项全过
```

只拆不补 = 把闸改弱。所以补第五项 **「出现率一致 ≥ 7/8」**。

阈值**不是新拍的数**：复用 §23 自己的 top-1 一致率，**同形同数** ——
「同一个结的出现与否在 rep 间一致」与「同一份稿子的首结在 rep 间一致」是同一种要求。
**选定顺序**：先按对称性定 7/8 → 再验证它抓得住构造反例 → **最后**才看真实数据。

### 三、K1 重判（五项）：仍然 FAIL，判决未变

| 判据 | 阈值 | 实测 |
|---|---|---|
| 同稿重跑次数 | n ≥ 8 | 8 ✅ |
| 完全相同的读数对 | ≥ 6/28 | 0/28 ❌ |
| **单结强度极差**（仅点火 rep）| ≤ 0.10 | **0.39**（`display`；7/9 个结可测）❌ |
| top-1 结一致率 | ≥ 7/8 | 8/8 ✅ |
| **出现率一致率**（新增）| ≥ 7/8 | **5/8**（`inertia`，3/8 点火）❌ |

### 四、[LESSON] 本轮最值钱的一条

> **「拆掉重复计数」和「把闸改弱」只差一步，区别在于拆出去的东西有没有被接回来。**

我给出的接管理由（「由另一项兜住」）**听起来合理但实际是错的**，
是靠**构造一个该被抓住的输入**才发现的 —— 不是靠推理，是靠动手造反例。
这是库里那条规则的又一次兑现：
**写完任何守卫/闸门，必须构造一个它应该抓住的输入，确认它真的触发。**

推论（新增）：**修判据时，「移除」这个动作本身必须配一个反例验证。**
否则「我认为另一项会兜住」就是一句没被检验的话。

### 五、证据

52/52 测试绿；本体 / Core 边界 / Archive / 链路符合性 四闸 PASS。
6 条反向突变全部实际见红，还原后绿：
退回「缺席记 0.0」· 点火 1 次也算可测 · 出现率阈值放到 1/8 ·
出现率项不进 checks（只拆不补）· 出现率一致率恒等于 n · 不标记「未被测量」。
另三条：7/8 恰好过 · 6/8 必红 · 恒不出现算一致不算不稳定。
并有断言钉住：**新旧口径在常火结上必须给出同一个极差** —— 确保修正只拆了出现率，没顺手改别的。


---

## 19.5.39 [MEASURED 2026-09-02] K1 判据冻结为四项 —— 又删掉两条形态错误的 gate

提交 `f2b52ba`。**0 次 API 调用** —— 在既有 8 rep 数据上重判。
外部裁决（思考 6m22s，带 ISO 5725 / ASTM C670 文献支撑），四处算术已逐项复核通过。
**三版判据，判决都是 FAIL —— 改判据没有改判决。**

### 一、删「完全相同的读数对 ≥ 6/28」—— 0/28 不构成仪器失败证据

它测的不是 repeatability，而是**九维向量的 exact collision probability**：

```text
P(V₁ = V₂) = Σ_v P(V = v)²
```

这个量取决于保留几位小数 / intensity 网格多细 / 中位数会不会产生 0.325 这类新值 /
九维联合基数 / 有没有 rounding。
**把三位小数改成一位小数，它就可能从永久红变绿 —— 而被测属性一个字没变。**

量级证据（实测 n=8，28 对）：相同坐标共 `2×4+13×3+9×2+4×1 = 69` 个，
单坐标 exact-match 率 `69/252 = 27.38%`；
而要达到 `6/28 = 21.43%` 的全向量匹配率，单维需约 `(6/28)^(1/9) = 84.27%` —— **差 3.1 倍**。

ISO 5725 把连续测量的 repeatability 定义为**结果的离散程度**，且明确允许一个 test result
由一组 observations 算出（与「多 draw → 中位数」相容）。标准从不把逐字节完全相等当作定义。

### 二、删「单结强度极差 ≤ 0.10」—— 严格度是观测数的函数

极差是极值序统计量，`R_{m+1} ≥ R_m` 是**数学恒等性质**。
实测抽子集（draw 数不变），rep 数 3→8 对应最大极差 **0.288 → 0.390** 单调上升
⇒ 同一台仪器，跑的 rep 越多越容易不达标。**判据在惩罚「多测量」。**

**ASTM C670** 对此有明确处理：若用 max−min 作验收量，其 critical multiplier
**必须随 test-result 数改变**（2 个结果 2.8 → 3 个 3.3 → 4 个 3.6 → … → 8 个 4.3）。
固定一个 range cutoff 跨不同 rep 数使用，本来就不是正确的统计构造。

### 三、换成：逐对容差一致率

```text
A_j(δ) = #{a<b : |x_aj − x_bj| ≤ δ} / C(m_j, 2)     要求 ≥ 0.95，δ = 0.10
```

- `δ=0.10` 沿用既有工程容差
- `0.95` 取自 ISO 5725/ASTM 的 repeatability limit 语义（两个重复结果之差以约 95% 概率落在界内）
- **不用 `r ≈ 2.8·s_r` 的正态近似** ——「5 个 draw 的中位数」不能假定正态
- 两个数都**不是**从本批数据拟合

★ **只读闸后最终输出**，不读 `draw_ledger` —— 这正是 `D_var` 被否决的那条（闸前算、闸后判）。
若闸后逐字节相同，output repeatability 就该 PASS；闸前内部波动属于另一个 robustness gate。

### 四、K1 = 四项，重判仍 FAIL

```text
✅ n >= 8 (由 early-return 保证, 展示项)   8
❌ 出现率一致 >= 7/8                      5/8    最差 inertia (3/8 点火)
❌ 逐对容差一致 A(0.10) >= 0.95            32.1%  最差 display (8/8 点火)
✅ top-1 一致 >= 7/8                     8/8
```

逐结 A：display 32% · injustice 54% · suspend 54% · audit 61% · belong 64% · **pain_seek 100%**
稳定缺席 `itch`/`reward`（强度**不适用**）· 出现率不稳 `inertia`（强度**未评估**，绝不填 0.0）

### 五、display 是确定性 FAIL，不是判据伪影

`R = 0.39 > 2δ = 0.20` ⇒ 最小值与最大值不可能同时与任一第三点在 δ 内
⇒ 其余 6 个 rep 各贡献至少一个坏对，加 (min,max) 自身 ⇒ **至少 7 个坏对** ⇒ `A ≤ 21/28 = 75% < 95%`。
实测 `A = 32.1%`（19 个坏对）。**不依赖正态假设，也不依赖极差作为验收量。**

### 六、分类改正 —— 我原来的分类是错的

我说「一真一假一不确定」。实际是 **两个真实质量问题 + 两条坏 gate**：

| | |
|---|---|
| 真实仪器问题 | 稀有结出现率不稳 · 常火结数值不可复现（6 个里 5 个不达标）|
| 判据形态问题 | 完全相同读数对 · 单结极差（它恰好碰巧揭示了一个真问题）|

### 七、`n ≥ 75` 的口径作废

它是从被删掉的 `R ≤ 0.10` 推出来的。现在只能写成
「基于两个 draw-count 点与 `1/√n` 假设的**量级级成本诊断**」，不是 K1 达标采样数。
新成本曲线应直接测 `A_j(0.10)` 随 stage2 draw count 的变化，
**目标已于今日冻结** ⇒ 之后测到的 draw count 不是事后拟合。

### 八、★ 顺带抓到一个装饰项

突变测试把「n ≥ 8」这一项改成恒真，**没有任何测试变红** ——
因为 n 不足在 `judge` 开头就 `early-return 2` 了，这一项**结构上永远为 True**。
已在名字里标为「展示项」，不假装它是判据。

> **教训：突变测试报绿时，先问「这一项是不是根本不可能为假」，再问「测试是不是假的」。**

### 九、[LESSON] 判据形态错误的识别法

> 问：**不改变被测属性、只改表示层（小数位 / 网格 / 舍入 / 观测次数），这条判据的结论会不会变？**
> 会变 ⇒ 形态错误。

这一条同时解释了本项目发现的三条错判据：
`grep = 0`（改目录结构就变）· `exact-match ≥ 6/28`（改小数位就变）· `range ≤ 0.10`（改 rep 数就变）。

配套的一条：**跨统计量比较前先问它是不是尺度无关、观测数无关。**
极差两样都不是；比例量（`A(δ)`、出现率一致率）两样都是。


---

## 19.5.40 [MEASURED 2026-09-02] A_j 成本曲线 —— 落入 B4_noisy，说不出 n*

提交 `7730aa3`。**0 次 API 调用。**
前登记 `tests/data/phase2/k1_cost_curve_prereg.json` 跑前冻结，**五个分支全覆盖**。

### 一、「先冻结再测量」有 git 证据，不是自称

判据阈值（δ=0.10，A ≥ 0.95）冻结在 commit **`f2b52ba`**，早于本测量。
测试用 `git show f2b52ba:probes/k1_gate.py` 验证那两个阈值确在其中，
并断言那个 commit 里**还没有**曲线产物 —— 有就说明是先测后冻。

### 二、0 次调用怎么做到的

s2 抽样按 `i % 3` 轮转 3 份 s1 prompt（逐条核对 `draw_id` 与 `prompt_idx`）。
所以取前 n 个 draw **严格复现**一次 n-draw 运行的 prompt 分配 —— **不是近似**。
整条 n=2..12 曲线从既有 10 rep × 12 draw 的 `draw_ledger` 算出。

### 三、曲线

```text
n      2     3     4     5     6     7     8     9    10    11    12
minA  .333  .533  .444  .489  .511  .622  .689  .556  .578  .667  .733
合格结  4     4     6     6     6     6     6     6     6     6     6
```

n=4 的跌落恰好赶上合格结数 4→6 ⇒ 可能是**合格集变了**而非统计量退化。
做了事后敏感性分析（如实标注**不是**前登记口径）：固定合格集后**仍然非单调**
（`suspend` 在 n=5 冲到 1.000，n=6 掉回 0.711）⇒ B4 不是合格集变化造成的假象。

### 四、为什么是噪声不是 n 效应 —— jackknife

`C(m,2)` 个对**不独立**（共享 rep），**不得套二项 SE**。留一 rep 的 jackknife：

| | |
|---|---|
| 平均 jackknife SE | **0.085** |
| 二项 SE 低估 | 约 **2.1 倍**（三个结一致）|
| 曲线相邻 n 的最大抖动 | **0.200** |

抖动与 SE 同量级 ⇒ **曲线起伏基本是估计噪声**。

### 五、能 firmly 说的 / 说不出的

- ✅ **n=12 明确不够**：min A_j = 0.733，留一区间 [0.667, 0.750]，距 0.95 有 **2.6 个 SE**。
  连留一最好情况都够不到 0.95 —— 这条结论不受曲线噪声威胁。
- ✅ 方向明确向上：n=2→12，0.333 → 0.733。
- ❌ **说不出 n\***。要说得出，需先把 SE 压到能分开 0.95 与 0.85，即 ≈ **29 rep = 429 次调用**。
  **不从噪声里拟合一个数** —— 有断言钉住 `n_star` 必须是 `null`。

### 六、★ 建议不花那 429 次 —— 理由是 scope，不是省钱

前登记明写 experimental unit = **1 个文本**。即便花掉这 429 次，得到的 n\* 也**不外推**，
不能当生产采样数。要真做，正确顺序是 **先扩文本再扩 rep** ——
多条文本各少量 rep，比单条文本 29 rep 更能支撑一个能当生产参数的 n\*。那是另一次前登记。

### 七、[LESSON] 新增两条

1. **「先冻结再测量」这句话本身要可验证。**
   用 git 证明阈值在哪个 commit、以及那个 commit 里还没有产物 ——
   而不是在文档里写一句「已冻结」就算数。
2. **前登记必须覆盖全部方向。**
   这次写了五支（达标 / 上升 / 平坦 / 非单调 / 下降），实际落点是「非单调」。
   §19.5 早前那次只写了两支（>1.5 与 ≈1），实际落点 0.36，两支都没覆盖 —— 同一个坑。


---

## 19.5.41 [MEASURED 2026-09-02] usable 读数改由 K1 判定路由 —— 系统内部自相矛盾的那一处

提交 `b8e8354`。**0 次 API 调用。**

### 一、洞

出站闸（`cce_strategy_gate`）按 K1 判定**硬拦** `[[knot_intensity:]]` 的引用；
而 `cce_full_run.usable_readouts` 把同一份 `intensity` **无条件**放进 `usable` ——
`usable` 的定义是「允许进入下游 / Population Field」「只有 usable 里的东西允许被引用」。

**同一份读数，一条路上被拦、另一条路上宣布可引用。**

它靠的是一句散文 caveat：「分布类读数**始终可用**，但必须带 n 与不确定性一起引用」。
而本项目已确立：**散文式 caveat 在这个项目已被证伪** ——
13 条 Notion 读数都标了「不可单独使用」，照样被当读数引用。
⇒ 改成由判定驱动的**路由**，不是再加一句话。

### 二、★ 先测再决定，结果推翻了我的假设

我原以为「派生量一律继承 intensity 的不可靠」。实测（生产 n=5 口径，10 rep，0 调用）：

| 量 | A(0.1) | 判定 |
|---|---|---|
| `intensity.*` | 0.7333–1.0000 | 多数不达标 |
| **`weight.*`** | **0.9111–1.0000** | **3/4 达标 —— 比原始 intensity 更稳**（归一化抵消共模噪声）|
| `mass.*` | 0.6222–0.7333 | **更差**（noisy 值取 max 当然更抖）|
| `composition.*` | 0.5714–0.9556 | 逐结分化 |
| `drive_brake.quadrant` | 1.000 | ⚠️ 10 rep 全同一个值 = **零方差，不是信度证据** |

⇒ 不能拿「它是派生量」直接断言。最终按 **未单独判定** 扣发（缺判定 ≠ 判定通过），
而不是按「同样不可靠」—— 理由与实测一致。
`quadrant` 那个 1.000 是**退化**，与 §19.5.37 踩过的退化估计量同一个坑。

### 三、路由

K1 判定本身是分层的：top-1 一致 8/8 达标 · 逐对容差 A(0.1) 不达标。

```text
usable  : s2.distribution.top1 · s2.playbook_primary(由 top1_stable 守)
withheld: s2.distribution.intensity · .knot_weight · s2.families · s2.drive_brake
```

单一真相源 `scripts/cce_k1_status.py`，出站闸与 usable 路由**读同一份判定**（有断言钉住）。

### 四、顺带补的两个 Core 闸缺口

抽 `derived_layers()` 纯函数（让探针与生产**共用一份实现**）动了被钉的 Core 文件，
Core 边界闸如实变红 —— 它在干正事。为此给闸加了两样：

1. **`instrument_expected`：现算仪器哈希与清单比对。**
   旧闸只钉文件字节，抓不到「换 `MEASUREMENT_MODEL` **环境变量**换仪器却一个文件都不动」。
2. **`refactor_log`：** 纯重构可不换代，但必须写明 from/to sha、理由、**行为证据（具体测试）**。
   「仪器哈希没变」**不足以**证明行为没变 —— 反例：改 `_has_support` 的代码逻辑而不动 `SUPPORT_RULE` 常量。

★ 既有反向测试当场抓到我第一版的洞：只匹配 `to_sha` 时，把 pin 改成任意垃圾值也被豁免。
收紧成必须匹配完整的 `(file, from_sha, to_sha)` 转移。

### 五、[LESSON] 新增两条

1. **默认参数在 `def` 时绑定，会让「换一份判定验证闸跟着变」这类反向测试根本跑不了。**
   凡是「从文件读判定」的模块，路径必须**调用时**解析。
2. **改一个「恒为真」的断言时，先问它的意图还成不成立。**
   `test_cce_measurement_system` 的「全过时 withheld 必须为空」如实红了 ——
   它的意图（不许永久红，本文档铁律「永久绿与永久红是同一种失效」）仍然对，
   所以改成**在 K1 全过的前提下**断言，意图原样保住；
   并补一条「K1 全过时 intensity 必须回到 usable」—— 否则这个路由是恒拦，没有信息量。

### 六、证据

54/54 测试绿；本体 / Core 边界 / Archive / 链路符合性 四闸 PASS。
7 条反向突变全部见红，还原后绿：
缺判定就放行 · 不看判定一律放行 · 判据改名静默放行 · intensity 无条件进 usable ·
families 不跟着扣 · weight 不跟着扣 · 两个消费者读不同文件。


---

## 19.5.42 [MEASURED 2026-09-02] K1 路由补仪器匹配 —— 我自己引入的跨仪器套用 bug

提交 `be1bf31`。**0 次 API 调用。**

### 一、bug

§19.5.41 那版 usable 路由**无条件**套用 K1 判定，**一处仪器检查都没有**。
K1 判定是在 gen4 `565470cf26c16d01` 上做的；一个 gen5 的 run 会被套用同一份判定。
这正是 gen2→gen3 已确立并禁止的事：「prompt 变了 ⇒ 标定不可搬，必须重标定」。

### 二、修法

`layer_status(path, instrument_hash)` —— `instrument_hash` 是**本次运行**的仪器：

| 情形 | 处置 |
|---|---|
| 与判定所属仪器相同 | 按判定分层放行 / 扣发 |
| 不同 | 两层都扣发 —— 这台仪器**没有** K1 判定，不是「判定通过」 |
| 缺失 | 同样扣发 —— **缺仪器标识 ≠ 仪器相同** |

最后一条与 K1 闸自己那条教训同源（§19.5.36）：
8 份 manifest 全缺 `text_sha256` 时 `{None}` 长度也是 1，
曾打印「输入指纹唯一 ✅」而它一个指纹都没看到。

实测三态：gen4 相符 → top1 放行 · gen5 → 全扣 · 缺标识 → 全扣。

### 三、顺带查清但**不改**的两处

1. `scripts/reply_batch.py` 直接读 `stage2.knots` 的 weight 出「推荐钩子」——
   只在 `replybatch.yml`，**不在生产入口** `cce-submit.yml` 上。不占预算。
2. `scripts/reply_loop.py` 在生产路径上，也直接读 weight 算 `knot_ok`。
   但它**已被正确降级**：workflow 只 `jq` 不作门（注释明写「只记录诊断，不作二值门」），
   `cce_workflow_manifest` 不把它计入 `errors`，且降级写在**契约**里
   （`cce_submission_contract_v1.json` 的 `success_gate`：「不参与通过判定」），
   由 `test_cce_submission` 钉住。**是契约条款不是散文 caveat ⇒ 不动。**

### 四、关于「这个路由会不会是永久红」

铁律原文是「永久绿与永久红是同一种失效：**读数与被测对象无关**」。
关键在「与被测对象无关」。这条路由**与被测对象有关** ——
换仪器、换判定，输出就变；端到端断言钉住了
「同一份 s2 读数在 gen4 与 gen5 下 usable 必须不同」。
真正让它不是 caveat 的，是它**把数据从 usable 里移走**，而不是打印一句理由。

同理，`test_cce_measurement_system` 那条「全过时 withheld 必须为空」改成
**在 K1 全过的前提下**断言之后，两个方向都被钉住：
K1 不达标 → intensity 扣发；K1 全过 → intensity 回到 usable。
两条一起才排除了「恒拦」这种退化。

### 五、[LESSON] 新增一条

> **「加一层由判定驱动的路由」时，判定本身的适用范围也是判定的一部分。**

我只搬了判定的结论（pass/fail），没搬它的适用条件（哪台仪器上做的），
于是造出一个「用别人的标定管自己的 run」的 bug ——
与 gen2→gen3 那次「标定不可搬」是同一个错误的另一种形状。

### 六、证据

54/54 测试绿；四闸 PASS。3 条反向突变全部见红，还原后绿：
跨仪器也套用同一判定 · 缺仪器标识就当仪器相同 · 不把本次运行的仪器传给路由。


---

## 19.5.43 [MEASURED 2026-09-02] 文档↔代码核对，与 §42 的补法：建准入闸不建四张空表

提交 `d05b9b6`（核对）· `463933d`（§42）。**0 次 API 调用。**
先扫全文目录（49 章）再核，不凭印象挑章节 —— 上次的教训正是「只读 §19.5 尾部，把它当全集」。

### 一、★ §43 核心铁律 25 条，三档实测

| 档 | 条数 | 含义 |
|---|---|---|
| **GATE** | **14** | 有可执行检查，违反会让某个测试/闸变红 |
| **FIELD_ONLY** | **6** | 概念有 schema 槽位，但**没有任何东西会因误用它而失败** |
| **PROSE_ONLY** | **5** | 只有文档里的一句话 |

⇒ **11/25 条无闸。** 本项目已确立「散文式 caveat 已被证伪」，
所以后两档都**不构成保护**，只是记录。

两条最值得注意的 FIELD_ONLY：

- **铁律 21**「研究工作流不得产出 production complete=true」——
  `workflow_registry` 有 `class:research` 字段，但**没有任何测试**钉住这条。
- **铁律 23**「九结是 candidate ontology」——
  `cce_knot_classify` 产出「G-K1/2/3 验收未跑，引用须带未验」这句 caveat，
  但**没有测试钉住它**，删掉不会红。

### 二、四处文档↔代码分歧

| 判定 | 章节 | 事实 |
|---|---|---|
| 文档过时 | §39 契约列表 | 声称 `/contracts/` 下 19 个 schema；实际无该目录。原文是「建议」⇒ 文档没跟上 |
| **符合**（本轮补） | §42 四条 Ledger | 见下 |
| 代码欠账 | §36 Capability Registry | 声称 8 字段，真缺 4 个（input_contract / output_contract / evidence_required / fallback_policy）|
| 位置不同+欠账 | §37 Workflow Registry | `stages` 与 `completion_gate` **确实存在**，但在 submission contract 的 profiles 里；真缺 4 个 |

### 三、★ 让「有闸」这句话本身可验证

`config/cce_doc_reconciliation.json` + `scripts/cce_doc_reconcile.py`，已接入 CI。
每条 GATE 声明必须指向**真实存在的文件 + 一个真的出现在里面的证据串 + 会跑过的测试**；
判「符合」的必须给出真实存在的 `gate.file` 与 `gate.test`。
声明不到就不许标 GATE。**这条闸存在的意义就是让对照表不能撒谎。**

### 四、§42 的补法：建准入闸，不建四张空表

先测数据实况：

```text
content       3 个归档 run + manifest + 7 条机制 + tests/data   ⇒ POPULATED
population    磁盘上 0 个持久化 population 产物                 ⇒ DECLARED_EMPTY
distribution  无数据源                                          ⇒ DECLARED_EMPTY
outcome       无数据源                                          ⇒ DECLARED_EMPTY
```

给不存在的数据建三张空表是脚手架。**§42 要防的不是「四张表没建好」，是把它们合并。**

两条硬约束**来自库内既有铁律，不是本模块新拍**：

- `distribution` 只收 `provenance.method=manual_backend_read` + `backend_ref` ——
  **平台侧指标查阅走人工后台，不做自动化抓取**；第三方平台 API 是平台可随时关闭的水管。
  且平台曝光总数不得用于创建 identified reached subjects（缺抽样框）。
- `outcome` 只收自有资产链结果 —— 真值链：自有站 → UTM → 落地页 → 独立分析 → 自有潜客库 → 成交。
  平台互动指标一律拒收；LLM 模拟的行为一律拒收。

**DECLARED_EMPTY 不是欠账**：没有数据源就不该有表，但**准入规则现在就生效** ——
等数据真来的那天，合并已经被闸挡住了。

### 五、[LESSON] 新增三条

1. **「文档说必须做 X」≠「应该现在把 X 建出来」。**
   先问 X 要防的是什么，再问那个风险今天是否已经存在。
   §42 防的合并风险今天就在（有人可能把 upvote 当商业结果）；四张表的风险要等有数据。
   **闸现在建，表等数据。**
2. **「概念出现在代码里」≠「有闸」。**
   第一轮用英文原文 grep 得到 13 条 0 命中，换概念词后发现概念都在（`version` 命中 45 次）——
   但词频不是断言。必须看**错误消息与 raise/assert**。
3. **grep 同行匹配会漏掉真强制点。**
   「never an individual persona」与 `errors.append("...marginal is not a person")`
   不在同一行，按同行匹配会判成「无闸」，实际那正是铁律 6/18 的真闸。

### 六、本次未覆盖（写死在产物里且有断言强制）

只核了 §36 §37 §39 §42 §43。**§45 矩阵与 §1–§35 的本体定义未逐条核。**


---

## 19.5.44 [MEASURED 2026-09-02] §36/§37 补齐，铁律 21 由散文升为闸

提交 `8783df2`。**0 次 API 调用。**

### 一、为什么这两个注册表值得补

库内已确立的权威链：**capability registry → workflow registry → 实际 workflow/contract → GitHub artifact**；
记忆只作背景。它们是头两环，自己必须被守住 —— 否则「退役组件当活标准」那类事故会原样复发。

### 二、§36 补四字段，各防一件今天就存在的事

| 字段 | 防什么 |
|---|---|
| `input_contract` / `output_contract` | 能力与契约脱钩（契约改了而能力不知道）|
| **`evidence_required`** | **无证据声称能力可用** —— 本项目反复栽的那件事 |
| **`fallback_policy`** | **静默兜底**。取值强制三分：`WITHHOLD` / `SKIP_EXPLICIT` / `NOT_IN_PRODUCTION_PATH` |

★ §36 还列了 `version`，**跳过并写明理由**：那是注册表的版本不是逐能力的，逐能力再挂会出现两个真值源。

### 三、§37 补三个、跳过一个

- `capabilities` —— 与 §36 互链，两个注册表不许各说各话
- `artifact_contract` —— 生产类指向 submission contract；非生产类显式 `null` +「其产物不得当生产读数引用」
- **`production_complete_allowed`** —— 见下
- ★ `profile` **跳过并写明理由**：一条工作流服务多个 profile
  （`cce-submit.yml` 同时跑 outbound_post / outbound_reply / subject_chain），挂单个字段是错的。
  `stages` 与 `completion_gate` 仍在 submission contract 里 —— 位置不同，非缺失。

### 四、★ 铁律 21 由 FIELD_ONLY 升为 GATE

此前 `workflow_registry.rule` 里写着「research workflows cannot issue production complete=true」
—— **一句散文，零强制**。现在闸**实查 yml 是否真的调用了 `cce_full_run` / `cce_workflow_manifest`**：

```text
research 类真能产出 complete         -> 硬红
非 production 非 research 能产出     -> 必须登记 known_divergence, 未登记即红
登记值与实查不符                     -> 红
```

给一个 research 工作流加上 `cce_full_run` 会当场被抓。
实查现状：15 个工作流里只有 `cce-submit.yml` 与 `cce.yml` 能产 complete，**10 个 research 全都不能**。

### 五、★ 查出一处真分歧（登记而非藏起来）

`cce.yml` 是 compatibility 类、声明不许产 complete，**但它今天真的能产**（调用 `cce_full_run`）。

铁律 21 点名的是 research ⇒ 不算违反字面；但**铁律 22**「Legacy 不得成为新生产依赖」
＋已确立的「生产测量只运行 `cce-submit.yml`」⇒ **这是第二条通往 complete 的路，不该有**。

登记为 `DECLARED_PENDING_OWNER`，两个选项写在册（摘掉那条路径／或显式承认两个生产入口），**等 owner 决定**。

另有反向测试钉住：**登记了但其实已不需要豁免的条目必须清掉** —— 与本体闸的
`stale_registry_entry` 同一条原则，免得登记表变垃圾场。

### 六、核对表更新

| | 之前 | 现在 |
|---|---|---|
| §36 Capability Registry | 代码欠账 | **符合**（带真实 gate）|
| §37 Workflow Registry | 位置不同+代码欠账 | **符合**（带真实 gate）|
| §43 铁律 GATE | 14 | **15** |
| §43 铁律 FIELD_ONLY | 6 | **5** |
| **无闸的铁律** | **11** | **10** |

升级留痕：铁律 21 记了 `upgraded_from`，且有断言强制它写明此前是什么档、为什么不算闸。

### 七、[LESSON] 新增一条

> **补一个「文档说该有」的字段之前，先问它防的是什么。**

防不到东西的字段就该**跳过并写明理由** —— §36 的 `version` 与 §37 的 `profile` 都是这样跳过的
（一个会造两个真值源，一个在语义上就是错的）。
盲目补齐字段表看起来「符合了」，实际只是把散文搬进了 JSON。

### 八、证据

57/57 测试绿；七闸 PASS（本体迁移 / Core 边界 / Archive / **注册表一致性** / Ledger 分离 /
文档核对 / 链路符合性）。10 条反向突变全部见红。


---

## 19.5.45 [MEASURED 2026-09-02] 核对 §45 矩阵与 §1–§35

提交 `70a76ec`。**0 次 API 调用。**

### 一、★ 方法：三次踩同一个坑才做对

1. 第一轮匹配到 `__pycache__/*.pyc`
2. 第二轮「production media ingest」命中的是**能力注册表里声明它 missing 的那一行**
3. 第三轮 `diariz` / `prosody` / `mix_metrics` 命中的是 `cce_video_parse.py` 里
   `status='missing_no_capability'` 的**缺失声明**

> **命中 ≠ 实现。可靠办法只有一个：看代码本身。**

这个过程写进产物且有断言强制留着 —— 否则下次还会拿 grep 命中当证据。
（代码比检查更诚实：`_audio_capabilities()` 就是一份「我没有这个能力」的台账。）

### 二、§45 矩阵 37 项

| 组 | 声称 | 判定 | 实际 |
|---|---|---|---|
| ① 已具备或接近具备 | 11 | **文档属实** | 11/11 逐条给出实现文件与关键符号 |
| ② 部分具备 | 6 | **文档属实** | 「部分」这个定性准确 |
| ③ 当前缺失或未生产化 | 13 | **文档过时** | 仍缺 7 · 部分 1 · **已实现 5** |
| ④ 研究未定 | 7 | **文档过时** | 仍未定 5 · **已定 2** |

**③ 已实现的 5 项正是本轮建的**：population repeated-window learning（P2）·
persistent archive（P5）· mechanism registry（P6）· experiment workflow（P6）· strategy loop（P7）。

**③ 仍缺的 7 项全部集中在 P3 多模态** —— 与 §44 P3 标 `GATE_ONLY_CONTENT_NOT_BUILT` 一致。

**③ 部分**：`full cross-modal event semantics` —— 有 `cross_modal_synchronization`，
但代码自标 `confidence_basis='definitional'`（两区间重叠由时间戳算出，构造上必然为真，
不是同步强度的度量）⇒ 达不到「**full**」。

**④ 已定的 2 项**：

- `9-simplex 是否合理` → **已定「不合理且已改」**（`cce_knot_classify.py:851`，已换 §22 四层）
- `causal attribution` → **已定「当前剖面下做不了」**
  （`causal_ceiling_descriptive` = ESTABLISHED，`max_grade = DESCRIPTIVE`）

### 三、§1–§35：只核做存在性声明的节

约 560 个结构性条目里**大多是本体定义不是存在性声明** —— 定义没有「实现了没有」这个问法。
（★ 这个数**口径依赖**：三种解析算法分别给 562 / 564 / 569，差别来自 §1 算不算、
`# 19.5` 的 text 块归到哪一节、围栏语言标记怎么认。**引用一个自己复现不出来的精确数是错的**，
所以这里只给量级。）
所以只核 §2（生产基线）与 §27（provenance 字段），其余显式标**不可机器核**并说明理由。

**这不是偷懒**：由定义派生的**约束**已经在 §43 铁律里逐条核过（15 GATE / 10 无闸）。

#### ★ §2 六条声明里一条当前不成立

| 声明 | 判定 |
|---|---|
| 生产入口唯一 = `cce-submit.yml` | 属实 |
| 提交协议 = `cce.submission.v1` | 属实（指 registry 的 `accepts`，非契约自身 `kind`）|
| 三个生产 profile | 属实（逐字一致）|
| **兼容/历史工作流不应继续承担新生产功能** | **当前不成立** |
| §2.2 subject_chain 五段 | 异名等价（自然语言 vs 标识符）|
| §2.4 数据进入链路的五个文件 | 属实 |

`cce.yml:72,147` 调用 `cce_full_run.py`，兼容层仍能产 complete。
**这是同一处分歧的第二次独立浮现**（第一次是 §37 的 `production_complete_allowed`）。
两个章节汇到同一个洞 ⇒ 它是真的。已登记 `DECLARED_PENDING_OWNER`。

#### §27 Evidence / Provenance Plane

8 个 provenance 概念里 **7 个在仓内有对应物**，但**没有统一的 provenance 块**、名字也不同：

```text
source_ref     → raw_sha256 / evidence_refs
parser_version → preparation_id
schema_version → kind
cce_version    → instrument_hash / measurement_procedure_id
timestamp      → started / finished / measured_at
confidence     → within_js
generated_by   → 无对应物
```

判「**异名分散**」而非「缺失」—— provenance 的**功能**在（可追溯性有闸），
缺的是字段名与块结构，那是互操作性问题，不是可追溯性问题。

### 四、又被本体闸抓一次

我在核对产物里写了旧本体名（`config/` 是契约面，key 与 value 都扫）。
**改写而不是登记豁免** —— 能不写就不写，豁免表不该为「我图省事」而增长。

### 五、证据

57/57 测试绿；七闸 PASS。新增 5 条反向突变：
判「过时」不给 actual · 判「属实」但数对不上 · 抹掉核对方法 ·
不可机器核不写理由 · 判定既无 evidence 也无 note。


---

## 19.5.46 [MEASURED 2026-09-02] 摘掉 cce.yml 通往 complete 的路（owner 裁定）

提交 `2355eef`。**0 次 API 调用。**

### 一、先证明影响面，再动生产文件

`cce.yml` 的两个 mode 早已在 `prepare.py` 前置就被拒：

```text
prepare.py:37  只收 reply|response|outbound_post  ⇒ 本文件的 post 被拒
prepare.py:62  出站模式必填 guard_profile          ⇒ 本文件无该输入, reply 被拒
```

2026-08-13 实测连挂两次（runs `31691417474` / `31691414219`）。
所以被摘的两处 `cce_full_run` 调用**本来就走不到** —— **影响面 = 零**。

### 二、摘法：换成显式退役提示，不删工作流

旧调用方拿到一句明确的话并 `exit 1`，而不是「workflow not found」。
工作流保留 = 可发现性；能力摘除 = 唯一生产入口。

### 三、结果

| | 之前 | 之后 |
|---|---|---|
| 能产 `complete` 的工作流 | 2 个 | **`cce-submit.yml` 一个** |
| `known_divergences` | 1 条 `DECLARED_PENDING_OWNER` | **空** |
| §2.1「兼容工作流不应继续承担新生产功能」 | **当前不成立** | **属实（2026-09-02 起）** |

判定**带日期**，不假装它一直成立。

### 四、★ 摘除时闸自己暴露一个 bug

摘掉两处真调用后，闸**仍报** cce.yml 能产 complete —— 命中的是**我写的那句退役注释**
「本工作流不再调用 `cce_full_run.py`」。

> **「命中 ≠ 实现」这条教训，这次出现在闸自己身上。**

已修 `can_emit_complete`：**剔掉注释行再匹配**，并加反向断言
（退役注释里确实提到它，这正是要剔注释的理由）。

### 五、三条闸各抓到一件事，互不重叠

- **registry 闸** —— 摘除后「把分歧藏起来」那条反向测试**失去触发源**，说明分歧真的没了。
  改为构造「把唯一生产入口降级又不登记」来验证闸仍会红。
- **archive 闸** —— 我在退役注释里写了两个 run_id，当场报「被引用但未入归档索引」。
  已补登记为 IRRECOVERABLE。
- **doc 核对闸** —— §2.1 的判定必须跟着改，且判「属实」时会**实查** `can_emit_complete`。

### 六、[LESSON] 新增两条

1. **改一处，三条闸各自从不同角度验它。** 这不是冗余 ——
   archive 闸抓的是顺手写进注释的 run_id，registry 闸抓的是分歧登记的生命周期，
   doc 闸抓的是判定与实况的一致性。三件事互不重叠。
2. **「过期豁免必须清掉」这条设计当天就兑现了**：分歧解决后条目留着会红，逼着删。
   豁免表因此不会变垃圾场。

### 七、证据

57/57 测试绿；七闸 PASS。
断言钉住：摘除后**只剩唯一生产入口**能产 complete；`known_divergences` 必须为空。


---

### §19.5.47 铁律分档复核：分类比闸建得早，10 条无闸里有 4 条其实已经有闸了

**起因**：§43 的三档分类（GATE / FIELD_ONLY / PROSE_ONLY）是在建 §42 Ledger 准入闸**之前**做的。
之后建的闸没有回头改分类 —— 「结论写进记录 ≠ 记录跟着结论走」，这次是反向：**闸建好了，账没记上**。

**复核方法：不 grep，跑反向用例，并断言是哪条规则抛的。**
第一轮四个用例全「✓」，其中两个是假通过：

| 用例 | 抛了 | 但理由是 |
|---|---|---|
| population 混入 revenue | ✅ | `DECLARED_EMPTY`，不是铁律 9 |
| outcome 收 LLM 模拟行为 | ✅ | 缺 owned key（`revenue` 不在 OWNED_OUTCOMES 内），不是「不可 LLM 模拟」 |

改成断言异常文本必须含指定规则串后重测，四条全真。**今天第六次撞上「命中 ≠ 实现」，这次在我自己的验证脚本里。**

**四条升 GATE**（全部带 `upgraded_from` 留痕，闸强制要求）：

| 铁律 | 原档 | 现证据 |
|---|---|---|
| 5 Behavior ≠ Outcome | PROSE_ONLY | `cce_ledger.py` outcome 拒平台互动指标 + 必须含自有资产链结果 |
| 9 Activation ≠ Distribution | FIELD_ONLY | content/population 硬拒分发量与商业量 |
| 11 Responded ≠ Acted | PROSE_ONLY | `comment/comments` 在 PLATFORM_METRICS 内，进 outcome 即红 |
| 23 九结是 candidate ontology | FIELD_ONLY | 新建 `caveats(taxo)` + `tests/test_cce_knot_caveat.py` 双向断言 |

**GATE 19 ≠ 19 套保护。** 5/9/11 是**同一条 Ledger 准入闸的三个面**。若只报条数，会把一套机制读成三套。
故新增 `shares_mechanism_with` 字段，并**给它配了校验**（声明共用就必须指向同一个 `file`，否则闸红）——
不配校验它就又是一句散文，而本项目已确立散文式声明无保护力。汇总行现在同时报：

```
§43 铁律 25 条: GATE 19 · FIELD_ONLY 3 · PROSE_ONLY 3
⇒ **6/25 条铁律没有任何东西会因违反它而变红**
   (GATE 19 条里有 2 条与别条共用同一机制 ⇒ **独立机制 17 套**, 别把条数当保护套数)
```

**铁律 23 的闸为什么必须双向**：只断言「未验 caveat 在」会腐烂成**永久谎言** ——
G-K1/2/3 真跑过之后 caveat 还在，就成了对已验收结论的错误降级。
所以第二方向同为硬断言：`status` 不再说未验 → caveat 必须消失。
这是「可注入的失败在上一层」的实例：无法给 G-K1 注入一次真失败，但可以给**状态字段**注入，断言探测器确实响。

**改 Core 的代价与登记**：`cce_knot_classify.py` 是 pin 住的 Core 文件，改动**立刻被铁律 20 闸拦下**并指名道姓
（`pinned cc7c1f8c != live 7f9a1feb，而 instrument_generation 仍是 4 且无 refactor_log 记录 —— 静默换仪器`）。
走 `how_to_change_core` 第四条（纯重构）登记。**`instrument_hash` 由 taxonomy+参数现算、与源码字节无关，
所以它「没变」对本次改动不足以当证据，连相关都算不上** —— 真证据是测试里冻结的 `PRE_REFACTOR` 三行原文
（出自 `from_sha=cc7c1f8c8dcd67b5`，即 git `2355eef`，已逐字核对）。

★ 中途我在测试注释里写了「复制自 git 8e3b7c0」—— **那个 sha 是编的**。已改成可核出处并实测通过。

**结果**：无闸铁律 **10 → 6**；测试 57 → **58**；七闸全绿；CI 测试数下限同步 57 → 58。
剩余 6 条（1/2/3 FIELD_ONLY，4/8/25 PROSE_ONLY）均属本体层区分（Raw/Observation/Event/State、
个体≠广播对象、群体优化以 Coverage 为中心），当前链路里**没有可注入的违例**，硬造一个闸只会是恒绿装饰。

**发现的仓外风险**：本架构文档位于 `~/Downloads/`，**不在任何版本控制内**，5529 行的唯一副本。
本次追加前已另存备份。建议纳入 `cce-engine/docs/` 或 vault。

---

### §19.5.48 K1-v2 多文本判定 · P3 媒体存在闸 · 25/25 铁律全覆盖

本节四件事都由**先注入一次违例、看有没有东西拦**驱动，不是补装饰。

#### 一、K1-v2：INSTRUMENT_WIDE_FAIL（5 文本 × n=8，320 次真实调用）

预注册 `ea5b907` 冻结于**测量前**，中途一次修订（`275a5b4`）也在**零调用之前**：
原写「文本 1 复用 v1 的 8 rep」，发现 v1 只记了 intensity 没记 weight ⇒ weight 只剩 4 个文本，
撑不起「≥4/5」，故改为一并重测（预算 256→320），顺带得到 v1 的同仪器复现检查。

| 层 | 过 | 非退化 | 结论 |
|---|---|---|---|
| intensity | **0/5** | **过**（3/3 结可分文本） | 5 个文本失败项**完全相同** |
| weight | **0/5** | **过**（4/3） | 换层无依据 |

三个结论：

1. **强度层不可复现是仪器属性，不是选文运气。** 5/5 全败且失败项一字不差（出现率一致 <7/8、
   逐对容差 A(0.1) <0.95）。v1 的 FAIL 在同一文本上复现。
2. **`weight` 救不了它。** 上一轮派生层探针在**单个文本**上看到 weight(0.9111–1.0) 稳于
   intensity(0.7333–1.0) —— 那是单文本观察，过不了预注册判据。已接进
   `cce_k1_status.weight_usable` 硬拦，不然下一个人还会照那句观察去换层。
3. **失败不是退化。** 两层都**过**非退化检验（跨文本极差 > 2× 文本内极差）⇒
   仪器**测到了**东西，只是复现不了。「什么都没测」与「测到了但复现不了」修法完全不同，不合并成一句「不稳」。

#### 二、归档面：「32 个 run 全不可追回」是**查错了仓**

把架构文档收进 `docs/` 时归档闸抓到未入册的 run，顺手复查，推翻了归档面的核心结论：
原 `total_count=0` 是对**私仓** `cce-engine` 查的，而生产入口 2026-08-17 起在**公开仓** `cce-engine-oss`。

**根因不是「查错了」，是「这个查询根本没有代码」** —— 人工跑一次把结论写死，没有可重跑的检查。
23 个 run 已取回落档（391 文件，逐件 sha256，**源与落档件数逐一核对相等**）。
中途第一版拷贝假设了目录层级，13 个 run 落档 0 文件 —— 空壳归档是本模块明令禁止的，已重做为递归全量。

闸加第④条：标 `IRRECOVERABLE` 必须带 `checked_against`（覆盖**全部 push 远端**，现读 git 不写死）与 `checked_at`。
仍标不可恢复的 19 条已**实测**两仓复核，不沿用被推翻的旧记录。
本地可重建 3 → **26**，不可恢复 34 → **19**，P5 转 DONE。

#### 三、P3：先让媒体的**存在**不能静默消失

实测 `.github/prepare.py` **零媒体感知**——只收 `text`。带图的帖子里那张图从不进系统，
manifest 却照样 `complete=true`。这是「静默缺席」，不是「能力不足」。

`scripts/cce_media_declaration.py`：检出可定位引用（markdown 图片语法／带媒体扩展名的 URL／已知媒体 host／
envelope 字段），排除代码块与行内代码里的链接，强制显式声明，并把
`modalities_present` 与 `modalities_measured` **分开** —— `complete=true` 从此只能读成「声明过的模态都测了」。

**假阳性是硬约束**：6 个负例零误报（「文中提到 image 这个词」「普通链接」「代码块里的链接」等）。
一个乱响的检测器比没有更坏，它会训练所有人忽略它。

媒体**内容**仍未测，也尚未接入生产入口 —— 接入需 owner 定存量出站的补登策略。状态记为
`PARTIAL_PRESENCE_DECLARED_CONTENT_NOT_MEASURED`，不冒充 DONE。

#### 四、25/25 铁律全部有闸（此前 6 条无闸）

逐条注入，结果分三类：

| 铁律 | 注入结果 | 处置 |
|---|---|---|
| 1 Raw≠Observation | 空 evidence_ref + 空 provenance 照样产出 `assertion="observed"` | **有洞**，已补 |
| 3 Event≠State | `assemble` 原样透传调用方自带的 events | **有洞**，已补 |
| 4 State≠Behavior | 带一个 owned key 就能把 knots 夹带进 outcome 账 | **有洞**，已补 |
| 25 Coverage | `coverage_scope=""` 被放行，覆盖率没有框 | **有洞**，已补 |
| 2 Observation≠Event | 行为本来就对（单 observation → `events:[]`） | 没测试钉住 ⇒ 钉 |
| 8 Individual≠Broadcast | 已被 `creates_identified_subjects` 指名拦下 | 分类过时 ⇒ 改 GATE |

★ **铁律 3 的闸我造窄了两次**：① 拿 `assertion=="derived"` 当判别器 → 当场拦红真实的
`evt:shot-cut`（直接可观测事件，`observed` 合法）；② 补 `event_type` 后又拦红 `evt:reinforcement`
（`inferred` 也是合同里的合法值）。事件**形状**本来就由 `cce_contract.validate_case` 管，不该重造。
合同没管的只有「事件带状态层字段」，铁律 3 只补这一条。**闸开太宽和开太窄一样是缺陷。**

**GATE 25 条 ≠ 25 套保护**：5/9/11 与 4/8 共用 Ledger 准入闸、2/3 共用组装器 ⇒ **独立机制 20 套**。
`shares_mechanism_with` 带校验（声明共用必须指向同一 file）。

#### 五、内容 A/B：§44.10 的「24,500」不可复算，故不继承

文档原话「分辨 R=0.34 与 R=0.75 需约 24,500 浏览/帖」，但**全文没有定义 R**。
按 0.34%/0.75% 现算是每臂 5,058，对不上；缺 R 定义则无法判断是文档错还是我的解读错。
本项目已栽过「引用一个自己复算不出来的数」，所以 `cce_ab_power.py` **不写死它**，由调用方声明的率现算。
闸的核心：功效不足时**硬抛**，永远不给「无差异」——「没测出差异」与「没有差异」在数据上长得一模一样。
且无 `force=`/`lenient` 逃生口（宽容模式就是这条闸不存在）。

语义 SESOI 已有三处测试钉住（`SESOI is None` + `global_resolution()` 永不给数），不是缺口；
它卡在外部锚点（需 ≥3 名人类评分者），不是我能补的。

**结果**：62/62 测试绿 · 七闸 PASS · Phase gate 8/8 · 铁律 25/25 有闸 · CI 下限 58→62。

---

### §19.5.49 三项决策的调研与裁定（owner 授权自裁，2026-09-03）

#### 决策一：K1 —— 采纳「强度层永久不可用」，且边界比原表述更紧

原本摆在桌上的是两条路：换仪器，或接受强度层不可用只用 top-1 + 分布类读数。
调研后**两条都不完全对**：换仪器不可行，而「只用 top-1」这个边界比我原来说的还要紧。

**① 换仪器求确定性推理 —— 不可行，且即便可行也不该做。**

外部文献（Thinking Machines，2025-09）已定位 `temperature=0` 非确定性的根因：
不是浮点随机，是**归约核的批大小依赖**（batch invariance）。修法是批不变内核，已进 SGLang / vLLM。
但那需要**自托管**推理栈 —— CCE 用的是 MiniMax-M3 托管 API，批组成不由我们控制。

即便做得到位级确定，也**不该**当成解：那是构造上零方差，不是测量可靠性。
本项目已两次判此类为退化（C2 判据可被常数估计器满足；quadrant 一致率 1.000 但零方差）。

**② 换读数形式 —— 实测堵死（零调用，用已采的 5 文本 × 28 对）。**

| 读数形式 | 均值 | 最差文本 | 全文本 ≥0.95 |
|---|---|---|---|
| cardinal（现行强度） | 0.712 | 0.619 | ❌ |
| **band3（粗档 3 挡）** | **0.726** | 0.661 | ❌ |
| rank_rho（秩相关） | 0.856 | 0.732 | ❌ |
| top2_set | 0.814 | 0.536 | ❌ |
| **top1** | **1.000** | **1.000** | ✅ |

★ **粗档只提升 +0.013** —— 这是最显然的一条逃生路，已实测堵死，别再花钱试。
★ 连 top-2 集合都只有 0.814（最差文本 0.536）：**一出 top-1 就崩**。
可复现的信号**恰好只有 top-1**，不是「top-1 加一点别的」。

这与 LLM-as-judge 文献同向：比较式/序数框架比逐点打分更可复现；
且 test-retest 只测稳定性、不测正确性——所以 top-1 稳**不等于** top-1 对，那是 G-K2/G-K3 的事。

**落地**：`cce_k1_status.knot_readout_usable(form)` 改为**白名单默认拒发**，白名单只有 `top1`。
每个排除项都带实测值 —— 「不行」必须带数，否则下一个人会重试。

★ **探索性数据只能关门，不能开门。** 这份对比是**看完 v2 结果之后**才做的，
产物标 `EXPLORATORY_NOT_PREREGISTERED`。用它排除某形式（负结论、关门）是低风险的；
要**采纳**任何形式，必须另立预注册并在资格池剩余 25 个文本上确认 —— 不得同批既调参又验收。

P4 状态转为 `DECIDED_KNOT_READOUT_TOP1_ONLY`。**「决定了」不等于「过了」**，状态名里留住这个区别，
且测试断言它不许以 `DONE` 开头。

#### 决策二：存量媒体补登 = 有原文实测 / 无原文 UNKNOWN，不猜

归档里 10 个 run 存有 `cce-submission-source` ⇒ 逐条实跑检测器：
**31 个 item 各扫到 2 段文本（draft + reader），检出媒体 0 个。**

★ 先核了 `texts_scanned != 0` —— 「零命中」可能是「零扫描」，是同一个陷阱的反面。
结论：历史出站确实是纯文本，静默缺席的风险**尚未实际发生**。

没有原文的一律 `UNKNOWN_NOT_ASSESSED`，**不补造声明** ——
编一个「无媒体」比诚实的 unknown 坏得多（与 Archive Plane 同一纪律：不假装能重建）。
新提交走入口硬拒，形状同 `guard_profile`：**入口拒绝才让复发结构上不可能**。

#### 决策三：不推远端

`git rev-list` 实测：**origin 领先 4，本地领先 143** —— 已分叉。
推送不是备份，是**合并操作**。

那 4 个远端提交（2026-08-17/18）的三处关键修复 —— `reader_baseline` 实现、`manifest.chain` 断言、
`context.declaration` 校验 —— **本地都已具备** ⇒ 分叉是「同样的活、不同的历史」，
未来 reconcile 可行，但那是独立任务，不该塞进「把文档收进 docs/」里做。

公开仓 `oss` 更不推：**边界闸只查身份泄露，不查商业内容**。
文档 5674 行里含以品牌命名的 run（`CCE daerdo:*`）与全部测量失败记录 ——
那是**对外发布决定**，不是备份决定，两者不能混为一谈。
而防丢失的目标已由「进 git」达成，不需要推送来兑现。

**结果**：63/63 测试绿 · 七闸 PASS · Phase gate 8/8 · CI 下限 62→63。

---

### §19.5.50 追 K1 裁定的下游后果：两个缺陷，结论完全不同

裁定「结层只发 top-1」之后追下游，扫全仓「在噪声连续量上焊布尔门」，抓到两处。
**两处的结论完全不同，不许合并成一句「阈值都不可靠」。**

#### 缺陷一：对齐分 —— 实测坏，已修

`cce-submit.yml:185`（唯一能产 `complete=true` 的入口）调 `reply_loop`，
而它用 `x["weight"]` 算对齐分 —— weight 前一天刚判 0/5 扣发。

**但不能从「分量不可靠」直接推「合成量不可靠」**：文献（Spearman-Brown / ICC(k)）明确
聚合会**提升**信度。所以必须实测。

零调用实测（5 文本 × 8 rep，固定 hit 向量以隔离 weight 的贡献）：

| 量 | 值 |
|---|---|
| 同一输入下分数极差 | 中位 **0.135** · p90 0.288 · max 0.488 |
| **θ=0.35 判决被 weight 抖动翻转** | **18.4%** |

★ 这是**下界** —— `dissolve_hit` 自身是每结 3 次 LLM 表决，噪声还要再加。
与 2026-08-10 的独立实测（同稿重跑 3/8 翻转、|Δ| 均值 0.213）同量级。

★ **聚合定理在这里结构上不适用**：它要求分量**独立**，而 9 个权重来自**同一次抽样**
且被全占比约束到和为 1（探针里已断言 Σw=1）。前提不成立，实测确认。

**修在哪**：★ 我先只改了 `reply_loop`，**漏掉 `reply_batch`** —— 同一份不可靠读数
在一条路上被扣住、另一条路上照发判决。**爆炸半径不一致本身就是缺陷**，
而这正是 2026-08-18 那条注释里已经写过的教训，我又犯了一次。
守卫已下沉到共用函数 `cce_align_v2.score`，所有调用方自动继承；不可用时 `pass=None`（不可判）。

旧守卫的问题也一并记下：它守的是 `top1_stable` —— 但 top-1 恰恰是**稳的**那层（实测 1.000），
真正的输入 `weight` 才是 0/5。**守错了对象**，于是它几乎从不触发。

顺带：补了只用可用层（top-1）的出口，把 9 结 × 3 票 = 27 次调用降到 **3 次**。

#### 缺陷二：`need_ok` —— 未被测量，**不是**坏

`need_ok = 触达率 >= 0.5` 是**三层叠加阈值**：`pa < SALIENT` 筛维 →
`pb >= pa*REACH` 二值化 → 率 `>= 0.5` 再二值化。

归档实测（run 32114744002，同一文本对 8 rep）：**触达率恒为 1.000，极差 0**。

但那是**顶到天花板** —— 3 个显著维全部触达；而显著维个数自己在 **2–4** 之间跳。
**天花板上的稳定，说明不了它在 0.5 判决线附近的行为。**
本项目已两次栽在「高一致率 + 零方差 = 退化」上（C2 常数估计器 / quadrant 1.000）。

⇒ 登记为「判决线附近**未被测量**」：既不能说它稳，也不能说它坏。
`layer_reach` 现在输出 `饱和` 标记与说明，防止有人拿饱和的 1.000 当「已充分触达」。

#### 媒体闸接入生产入口

`.github/prepare.py` 出站两档必填 `media_declaration`，形状同 `guard_profile` ——
**入口拒绝才让复发结构上不可能**（旧 `post` 档复发三次才根治）。
缺 / 声明不符 / 漏项 / 非法 JSON 各自 `rc=1`；**闸不可用也判红，不降级放行**。

注册表扩域 `+FAIL_CLOSED`：入口闸的语义是**不往下走**，而既有三值都预设「继续走」。
硬塞近似值等于把语义抹平。★ 闸自己拦下了我三次：自造取值域外的值 ·
`production_github` 缺 `entrypoint` · `entrypoint` 必须是注册过的 workflow。

**结果**：66/66 测试绿 · 七闸 PASS · CI 下限 65→66。

---

### §19.5.51 我把 PII 提交进了会推公开仓的树 —— 边界闸抓到的

问「origin 那条分叉要不要 reconcile」，查库时把这个问题的前提翻掉了，
顺手重跑边界闸，抓到一件更严重的事。

#### 事故

2026-09-03 我从公开仓取回 23 个历史 run（391 文件）提交进仓，**取回之后没有重跑边界闸**。
我只在加架构文档**之前**跑过。闸就是为这个存在的，我跳过了。

```
❌ 公开仓出现 3 个真实身份 —— 全部来自 archive/31993570335/
FAIL
```

其中一个 run 的 `reader.actor_ref` 是**未化名的真实论坛 handle**，
违反手册「actor_ref 里只能写化名」；读者正文里另有一个真实 handle。
**本仓可 fast-forward 到公开仓 `cce-engine-oss`（oss 领先 0、本地领先 87），差一步就推出去了。**

#### 我在修的过程中又犯了同一个错

第一版处置：把真名写进归档索引的 reason 和新测试的反向用例里，用来说明这次泄露。
重跑边界闸 —— **再次 FAIL，泄露源变成了我自己写的那两个文件**。

★ **记录泄露不等于复述泄露。** 两天前写 `cce.yml` 退役注释时把 run_id 抄进去被归档闸抓过一次，
同一个错，这次抄的是真名，更严重。

#### 处置

两个 run 转 `RESTRICTED_OFFTREE`：整目录移出仓库树到识别层保险库，逐件 sha256 核对相符，
**数据未删，只是不在会推公开仓的树里**。

★ **不就地改成化名**：归档的全部意义是**字节保真**，改了就与 `_listing.json` 的 sha256 不符，
等于把一份可核的产物变成不可核的。**宁可它不在树里，不可它在树里却是假的。**

第二个 run 是一份原始 LLM 失败日志里出现身份位置的通用 handle，**很可能**只是模型吐的占位符，
但识别层里查不到对应的人 —— **「查不出是谁」不等于「确认不是人」**。
★ 备选是放宽保险库那道共用闸的通用 handle 规则，**否决**：为了让自己过闸去调松一道共用安全控制，方向是反的。

#### 补的闸：`tests/test_cce_no_real_identities.py`

`check_boundary` 很有效（这次就是它抓的），但它**只能抓识别层认识的人**，
而且扫两棵树要两分钟，不适合进每次都跑的测试集。

新闸问的是另一个问题 —— 手册规定 actor_ref 只能是化名，那是**仓库这一侧自己就能验的不变量**：
任何 `actor_ref`，要么匹配化名前缀，要么违规，**不需要知道那个人是谁**。扫 525 个 JSON，秒级。

★ 化名表与放行表**运行时从边界闸读**，不在测试里再抄一份 ——
我第一版抄了一份，当场就漏了 `auto-sticky`。两份表必然漂移，这是实证不是担心。

#### 顺带更正一个我说错的推断

我先断言「那几个 handle 里有一个只出现在识别层的 markdown 里，闸从结构化身份字段收不到它，所以抓不到」。
**闸抓到了。** 它没有那个洞，是我推断错了。

★ 而写这一段时我**第三次**把真名抄了进来（前两次：归档索引的 reason、新测试的反向用例）。
一轮之内三犯同一个错，说明「靠自己记得不要抄」这个办法是无效的 —— 已改成推送前由闸把关，
并把 `git grep` 预检写进推送前清单。

**结果**：边界闸 **PASS**（识别层 590 身份零命中）· 67/67 测试绿 · 七闸 PASS。

---

### §19.5.52 §39 更正 · 四档 profile 全部 CI 验证

#### §39 基础 Contract 列表 —— 文档没跟上，现更正

§39 写「`/contracts/` 下 19 个 `*.schema.json`」，原文是**建议**仓库最终统一到那个布局。
仓库走了另一种：契约在 `config/cce_*_contract_v*.json`（5 个）+ 四张注册表。

**不是欠账，是文档没跟上。** 现行真相源以代码与注册表为准，见 `docs/README.md` 的权威顺序。
此项在 `config/cce_doc_reconciliation.json` 里由「文档过时」改为「文档过时·已在文中更正」。

#### 四档 profile 全部在当前代码上 CI 验证

| profile | run | 结果 |
|---|---|---|
| `media_ingest` | `33743931309` | complete=true |
| `outbound_post` | `33745544418` | complete=true（结层**零可用读数**，k=5 非 K1 仪器） |
| `outbound_reply` | `33746399209` | complete=true（**top-1 可用**，k=3 = K1 仪器） |
| `subject_chain` | `33748217410` | 8 路 + 聚合全 success，审计 `overall_status=NOT_VERIFIED` |

★ `subject_chain` 用的是**仓内现成的真实夹具**（`examples/cce_submission_subject_chain_v1.json`，
两个 sha256 实算相符），**没有硬造** —— 造一个夹具跑通只能证明我造得出夹具。

★ 审计判 `NOT_VERIFIED` 是**正确结果**：无商业／归因证据时就该保持未验证。
**链路跑通 ≠ 业务已验证**，两件事不许合并。

#### 仍未完成的，见 `scripts/cce_open_items.py`

它从各真相源现算，分三类（OPEN_WORK / BLOCKED_EXTERNAL / DECIDED_NOT_DOING）——
**把 BLOCKED 混进 OPEN 会让人以为「再努力一下就能做」**。
