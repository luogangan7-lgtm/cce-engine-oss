# CCE 全链架构 v3：主体条件化测量与异质性人群

> 已由 `cce_chain_architecture_v3_1.md` 取代。v3 正确禁止均值冒充人群，但错误地没有正式合成 Population Subject，且允许单成员 response segment；v3.1 已修正。

状态：Draft PR 的规范基线。v3 保留 v2 的平台/动态场景边界，并修复两个根本问题：

1. CCE 不再只有 `Event + Context -> distribution` 一种模式；有证据的主体前态可进入状态转移测量。
2. Population 不再由个体算术均值代表；成员分布、成分、异质性和动态响应段全部保留。

## 1. 领域主链

```text
Real World
   |
   +--> Subject Space: Individual / Dynamic Segment / Population
   |                         +
   +--> Universal Context ---+--> Active Subject State
   |
   +--> Input World -> Observation -> Atomic/Composite Event
                                      |
                                      v
                               CCE Measurement
                      +---------------+---------------+
                      |               |               |
                  stimulus     observed_response   transition
                      |               |               |
               dynamic readout  state hypothesis   Before/After/Delta
                      +---------------+---------------+
                                      |
                              Subject Update
                                      |
                 member distributions / composition / heterogeneity
                                      |
                         Dynamic Segment / Population Evolution
                                      |
                  Outcome / Experiment / Calibration / Feedback
```

产品、行业、平台和社区都是运行时变量。Reddit 是稳定平台；subreddit 是带时间的动态
`surface`；助听器是 `domain/category/need`；GitHub 是控制面，均不是 CCE 根主体。

## 2. 主体的三个时间尺度

| 部分 | 语义 | 更新规则 |
|---|---|---|
| Core | 主体稳定核心 | 只有充分证据和可追溯更正才能改变 |
| Identity | 角色、关系和身份线索 | append-only，记录 first/last seen 和证据 |
| State | 注意、情绪、信任、意向等瞬时状态 | 每条记录带时间、assertion、证据、置信和 temporal scope |

`subject_id` 稳定，不使用 `profile_version/subject_version` 复制业务主体。窗口是分析投影，
不是主体版本。主体实体可以在测量前存在；禁止进入测量的是“主体答案/永久画像”，不是有证据
且带时间的 `pre_state_snapshot`。

## 3. Universal Context

Context Snapshot 的正式维度为：

```text
time / location / environment / device / session
social / relationship / life / task / current_goal
```

每个已声明维度都必须包含：

```json
{"value": "...", "assertion": "observed|inferred|derived|unknown", "evidence_refs": []}
```

快照自身还必须有 `id/observed_at/summary/provenance`。若为平台场景，再增加
`platform/platform_adapter/surface/domain`。平台字段不是 Universal Context 的全部。

## 4. 三种 CCE Measurement Mode

### stimulus

```text
Event + Universal Context -> derived dynamic distribution
```

用于内容/刺激本身的结构化诊断，不输入主体前态，不声称平台效果或人的真实反应。

### observed_response

```text
Observed response text/behavior + Context -> derived distribution
                                         -> optional inferred state hypothesis
```

文本/行为是 `observed`；模型读数是 `derived`；作者心理状态最多是 `inferred`。三者不能混写。

### transition

```text
Event + Context + evidence-bound pre_state_snapshot
    -> post_state_snapshot
    -> exact delta = after - before
```

无前态证据时不得猜测，返回 `NOT_MEASURABLE`。transition 必须保证同一 subject、共同状态维度、
精确 delta、完整 evidence 和 confidence。发布后 outcome 不得回灌同一次 ex-ante 请求。

## 5. Population 不是平均人

每个 activated population projection 必须包含：

```text
member_distributions   # 每个成员的完整分布
composition            # 已知成员数、coverage、是否穷尽
heterogeneity          # 全成员两两 JS divergence
segment_mixture        # 响应相似性的描述性动态段
segmentation           # 方法、阈值、descriptive_not_causal
```

`aggregate_distribution` 和 `aggregate_layer_distributions` 禁止作为 Population Subject。
Segment centroid 只是段内摘要，不能替代成员分布。没有共同曝光、冻结比较协议和实验时，动态段
只能描述相似性，不能声称因果人群。

相邻窗口可描述 `create/continue/split/merge/disappear`，但必须保留共同成员数量和可比性限制。

## 6. 结果、反馈与学习

```text
Frozen prediction / measurement
             +
Observed exposure / response / action / conversion
             |
             v
Attribution protocol -> calibration error -> model/schema decision
```

`target/reached/activated/action/conversion` 各窗口仍使用独立证据。浏览量只是 distribution，
不能生成 reached member；历史行为不能冒充曝光后 action；商业结果必须有 publish join。

## 7. GitHub 控制面

- `outbound_post`: s0-s4。
- `outbound_reply`: reader evidence + draft s0-s4 + alignment。
- `subject_chain`: observed responses 最多 8 路并发 s0-s3，精确双指纹回收，再生成 Population Projection。
- `post`: s0-s8 仅 legacy research。

每个 normalized item/artifact 携带完整 `context_snapshot`。GitHub 负责提交、并发、重试、产物、
manifest 和 gate，不定义 Subject/Event/State/Population 的领域含义。

## 8. 验收 Gate

1. 同一 Event/Context 在不同有证据 pre-state 下可形成不同 transition；无证据必须失败或 `NOT_MEASURABLE`。
2. `delta` 必须逐维等于 `after-before`，错一个值即失败。
3. Context 至少声明一个 Universal Context dimension，并保留 assertion/evidence/provenance。
4. 评论文本不得被标为 observed psychological state；measurement=`derived`，state hypothesis=`inferred/derived`。
5. Population 必须逐成员保留分布，并提供 composition、heterogeneity、segment mixture。
6. 双峰 fixture 必须仍输出两个响应段；只有均值的输出必须失败。
7. Segment evolution 必须标 `descriptive_not_causal`，除非另有冻结实验协议。
8. v2 的平台、触达、行动、转化、精确指纹和端到端 gate 全部继续通过。

## 9. 已知局限与升级信号

- 当前 transition 合同和 exact-delta gate 已实现；真实 post-state 仍需观察或经验证的估计器产生。
- 当前动态分段使用小样本响应相似性连通分量，适合描述性窗口，不是稳定聚类或因果分群。
- Reddit 无 silent viewer identity，因此 Population coverage 仅限可识别入站成员。
- 当前只有 `reddit@1.0.0` adapter 和 `hearing_aid` guard；扩展平台/领域时分别增加，不复制社区 adapter。
- 向量索引仍不是必需；Event、State、Evidence、Transition、Population 和 Outcome 的事实源保持结构化、可追溯。
