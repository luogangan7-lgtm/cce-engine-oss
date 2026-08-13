# CCE 全链架构 v3.1：Individual → Segment → Population Subject

状态：Draft PR 规范基线。v3.1 修正 v3 的矫枉过正：**禁止“均值冒充人群”，不等于禁止合成人群。**
Population 必须合成，但合成结果是带定义、范围、权重、异质性和不确定性的混合分布主体，不是一个虚构的平均个人。

## 1. 两条正交轴

### 主体尺度轴

```text
Individual Subject
        ↓
Dynamic Segment
        ↓
Population Subject
```

### 链路阶段轴

```text
Target → Delivered → Reached → Activated → Action → Conversion
```

它们不能并列成六种人格。每个阶段都可以有 Individual / Segment / Population 三种尺度的投影。
`Delivered` 是平台交付形成的匿名/分层人群投影；无法识别成员时只保留 cohort/cell，不制造 subject_id。

## 2. 完整主链

```text
Real World
   ├── Subject Space
   │      ├── Individual: core + append-only identity + current state
   │      ├── Dynamic Segment: explicit basis + membership probability
   │      └── Population: definition + frame + mixture + uncertainty
   ├── Universal Context
   └── Input World
           ↓
Signal Decomposition / Multimodal Parsing
           ↓
Observation → Atomic/Composite Event → Event Stream
           ↓
Active Subject State = Subject × Context × evidence-bound baseline
           ↓
CCE Measurement
   ├── stimulus
   ├── observed_response
   └── transition: Before → After → exact ΔState
           ↓
Individual response distributions
           ↓
Weighted Population Synthesis
   ├── member/cell components
   ├── weights
   ├── population marginal + quantiles
   ├── composition + coverage
   ├── heterogeneity
   ├── stable segments + unassigned mass
   └── uncertainty
           ↓
Target / Delivered / Reached / Activated / Action / Conversion comparison
           ↓
Experiment / Attribution / Calibration / Feedback
```

## 3. Individual Subject

Individual 采用三时间尺度：

| 部分 | 规则 |
|---|---|
| Core | 欲望基线、价值观等稳定或慢变量；充分证据才能修正 |
| Identity | 角色和关系身份只追加；保留 first/last seen、频率和近因激活 |
| State | 注意、情绪、信任、意向等瞬时量；绑定 Context、时间、证据、置信、持续和衰减 |

完整 56 参数域已机器化为 `config/cce_subject_system_contract_v1.json`。字段允许 `unknown`；不能为了填满 Schema 强推断。

13 张 v3 主体卡是 13 个稳定 Individual Subject 的证据投影，包含欲望基线、需求配置、身份账本、行为频率、
情境激活、关系阶段和置信。它们可以用于构造结构主体段和目标人群假设；但它们是便利样本，不能自行提供社区人口权重，
也不能冒充当前刺激下的状态或响应。

## 4. Dynamic Segment

Segment 必须声明 basis：

| basis | 输入 | 可以回答 | 不能回答 |
|---|---|---|---|
| structural_subject | core / identity / need / behavior / sensitivity | 哪些长期主体结构相似 | 对本条内容会如何响应 |
| shared_stimulus_response | 同一 Event/Context 下的 response/ΔState | 哪些人对此刺激响应相似 | 稳定人格或因果效应 |
| state | 同一窗口状态 | 此刻哪些人状态相似 | 长期主体类型 |
| action | 曝光后真实行为轨迹 | 哪些人行为路径相似 | 未观察行为或心理动机 |

稳定 Segment 至少需要两个成员支持。单个成员是 mixture component 或 `unassigned` 证据，不是一人 Segment。

## 5. Population Subject 的合成

对成员或 cell 的分布 `P_i(z)` 和权重 `w_i`：

```text
P_population(z | stage, context, time) = Σ_i w_i · P_i(z)
Σ_i w_i = 1
```

这个边际分布可以计算，也可以报告均值、中位数和分位数；但必须与以下内容一起存在：

```text
population_id / definition / unit / stage / time_window
coverage_scope / estimand / sampling_frame / sampling_method
member_or_cell_weights / mixture_components
marginal_distribution / component_quantiles
composition / heterogeneity
segment_structure / unassigned_mass
uncertainty / evidence_refs / provenance
```

边际统计的语义固定为：`weighted population marginal; never an individual persona`。

## 6. 从互动样本到目标人群的推断等级

| 等级 | 数据 | 可输出 |
|---|---|---|
| L0 observed sample | 评论、回复、可识别互动者 | 已观察互动 Population Subject |
| L1 calibrated sample | L0 + 外部人群边际/选择变量 | 校准权重后的样本人群 |
| L2 poststratified population | 明确 target frame + cell totals + 分层模型 | 目标 Population Subject 估计与区间 |
| L3 causal population | 冻结 A/B 或准实验 + 一致结果口径 | Population ΔState / heterogeneous effect |

Reddit 评论是自选择的非概率样本。没有平台受众边际或已知抽样概率时，只能停在 L0；不能从评论者外推沉默浏览者、
整个 subreddit 或市场总体。

## 7. 当前 post6 的正确解释

当前 8 条响应应合成为一个：

```text
Activated Population Subject
scope = identified_inbound_only
n = 8
mixture_components = 8
weights = observed-sample equal weights
representative_of_broader_population = false
```

当前每两人 JS 距离均高于阈值，且 n 很小，因此没有得到受支持的稳定响应段。正确输出是：

```text
stable_segments = 0
unassigned_components = 8
segmentation_status = insufficient_support
```

这仍然是一个合成的人群主体，只是它的内部结构暂时由 8 个经验成分表达，而不是伪造 8 个一人 Segment。

## 8. 还要补哪些数据

| 缺口 | 最小补充 | 解锁能力 |
|---|---|---|
| Target | 发布前冻结的人群定义、五问、目标九结/CCE 分布 | target Population Subject |
| Delivered | 平台 audience insights、曝光 cohort/cell、时间窗 | 平台交付人群投影；无成员身份时保留 aggregate/cohort/cell |
| Selection/coverage | 目标总体或可靠外部来源的 cell totals | 校准权重/MRP 外推 |
| Repeated response | 同一主体跨多内容、共同刺激和 Context 的矩阵 | 稳定 response segment、激活函数 |
| State transition | before/after 或可验证代理指标 | 真实 ΔState 与 persistence/decay |
| Action | 曝光后 click/save/profile visit/inquiry 等同人或 cohort 证据 | activated → action |
| Conversion | publish_id/UTM/CRM join | action → conversion |
| Causal calibration | 冻结随机/准实验、对照与预注册指标 | 人群因果效应与异质效应 |

## 9. Gate

1. Population 必须输出 mixture components、权重、coverage、estimand、异质性和 uncertainty。
2. marginal/mean/median/quantile 可以存在，但不得脱离 mixture 单独输出为主体。
3. 没有 target frame/cell totals 时，`representative_of_broader_population` 必须为 false。
4. 单成员不得命名为 Segment；必须进入 `unassigned_member_refs`。
5. 结构段和共同刺激响应段不得混用。
6. 13 张主体卡不得被当作社区抽样框或人口权重。
7. observed/inferred/derived 必须分离。
8. target、delivered、reached、activated、action、conversion 每阶段必须使用自己的证据；分发记录不能直接冒充 reached member。
9. 无实验时 segment/evolution 必须是 descriptive，不得声称 causal。
10. 任一相邻阶段缺少可比证据，delta 必须 `NOT_TESTABLE`。

## 10. 方法依据

- AAPOR 的非概率抽样报告要求明确抽样方法、推断假设与偏差风险；辅助变量、倾向调整等只能在透明假设下使用。
- MRP 通过分层模型估计 cell，再按目标总体 cell size 做 poststratification；没有目标 cell totals 就不能执行该步骤。
- 有限混合/潜类模型用于表达异质人群中的潜在成分；不能只保留总均值。
- 稳定聚类方法允许把证据不足的点标为 noise/unassigned；不应强制每个点进入一个 Segment。
- Latent Transition Analysis/HMM 适合多时间窗的 segment transition；只有横截面成员变化不能证明人群演化。
- 异质因果效应需要随机/准实验和目标总体迁移假设；评论相似性只能描述响应结构。

参考：

- [AAPOR Task Force on Non-Probability Sampling](https://aapor.org/wp-content/uploads/2022/11/NPS_TF_Report_Final_7_revised_FNL_6_22_13.pdf)
- [AAPOR Social Media in Public Opinion Research](https://aapor.org/wp-content/uploads/2022/11/AAPOR_Social_Media_Report_FNL.pdf)
- [Gelman: Survey Weighting and Regression Modeling](https://stat.columbia.edu/~gelman/research/published/STS226.pdf)
- [McInnes et al.: HDBSCAN](https://joss.theoj.org/papers/10.21105/joss.00205)
- [Best Practice Recommendations for Longitudinal Latent Transition Analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC11909493/)
