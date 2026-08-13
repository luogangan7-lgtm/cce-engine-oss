# CCE Engine

认知因果引擎的执行链。**每次运行都有永久 URL 和完整日志——"跑没跑完整"是可核事实,不是口头声明。**

## 链路

| 模式 | 段 |
|---|---|
| `reply` | s0_context → s1_readout → s2_knots → s3_emotion_policy → s4_guard |
| `post` | 上述5段 + s5_audience → s6_alignment → s7_ruler → s8_pairwise_bet |

任一段失败即 `complete=false`,链路中止,manifest 记录 `failed_at`。

内容测量之外，仓库还提供可审计的主体窗口链：

```text
内容/Event → CCE 内容测量
发布/平台交付 → reached window
逐字入站响应 → CCE s1 并行测量 → activated window
曝光后真实行为 → action window
publish_id/UTM 商业事实 → conversion window
```

主体使用稳定 `subject_id`，不做 `profile_version`。身份证据累加，状态带时间戳；
`target/reached/activated/action/conversion` 是分析窗口，不是主体版本。

## 生产投料规范

唯一生产入口是 `.github/workflows/cce-submit.yml`，只接受版本化的
`cce.submission.v1`。三种 profile：

| Profile | 用途 | 成功 Gate |
|---|---|---|
| `outbound_post` | 帖子/邮件/文章发布前 s0–s8 | 精确指纹 + `manifest.complete=true` |
| `outbound_reply` | 我方回复 s0–s4 + 对方响应对齐 | manifest 完整 + alignment PASS |
| `subject_chain` | 真实入站响应 → activated/下游审计 | 全员 s1 双指纹回收；业务结论另看窗口 gate |

共同必填：`submission_id`、`producer/trace_id`、profile、逐字文本及 SHA-256、
platform/surface/domain/language/speaker_role 与 taxonomy 合法情境。post 另需冻结目标指标、受众原话（≥30条/≥1000词）和上一篇
逐字基准；reply 另需对方原文及证据；subject 另需逐成员证据和主体链。

完整字段表、失败语义和产物契约见 `docs/cce_workflow_spec_v1.md`。

## s6 对齐算子 v2

```
对齐分 = Σ(推动族受众结) w × 稿件该结权重        [共鸣]
       + Σ(阻挡族受众结) w × 拆除动作命中度(0-1)  [拆除]
```

v1 的裸 argmax + 集合成员判定已废弃:阻挡族(suspend/inertia/audit)按定义不可能出现在稿件结里,内容只能**拆除**它不能**携带**它,旧规则在受众主结落阻挡族时恒不可满足。

阈值 `CCE_ALIGN_THETA`(仓库变量,默认 0.35)。**标定状态:未完成**——四篇已发布帖真语料得分 0.175~0.315,跨run方差与样本间差异同量级,4样本不足以立硬阈值。

## 触发

```bash
# 单条与批量都使用同一 envelope；items 最多8条并发
jq -n --slurpfile submission examples/cce_submission_outbound_post_v1.json \
  '{event_type:"cce-submit",client_payload:{submission:$submission[0]}}' \
| gh api --method POST repos/OWNER/REPO/dispatches --input -
```

`cce.yml`、`reply.yml`、`replybatch.yml` 为旧调用兼容入口；新系统不得接入它们。
其余 workflow 属 accuracy 或 research，不产生生产全链完成声明。

## Secrets / Variables

| 名 | 类型 | 用途 |
|---|---|---|
| `MINIMAX_API_KEY` | Secret | 九结分类与情绪面板的模型调用 |
| `CCE_ALIGN_THETA` | Variable | s6 阈值,默认 0.35 |

## accuracy/ — 准确度回归台

**为什么它是第一优先级**: CCE 是整条流水线的地基。地基没到基准, 下游任何优化都是白搭。
本目录把"CCE 准不准"从临时评估变成**每次改动自动产出、可对比、可回滚**的数字。

| 文件 | 作用 |
|---|---|
| `data/corpus.json` | 86 条标注语料 |
| `data/cold_b*.json` | 38 条冷启动盲标(真值) |
| `data/baseline_v5_taxo_1.1.1.json` | 冻结基线(taxonomy v1.1.1 时的验收态) |
| `run_gates.py` | 跑 G-K1(分布一致性) / G-K2(成本档预测) |
| `compare.py` | 与基线逐指标对比, 出 markdown 报告 |

触发: `config/**` `scripts/**` `accuracy/**` 任一改动自动跑, 或手动 workflow_dispatch。

**基线现状(v1.1.1, overall_pass=false)**:

| 指标 | 值 | 判读 |
|---|---|---|
| G-K1 top2 命中 | 1.0 | ✅ |
| G-K1 平均 JS | 0.15 | ✅ 分布层高度一致 |
| G-K1 top1 κ | 0.517–0.549 | ❌ 未达 0.6 |
| G-K2 成本档增益 | −0.316 | ❌ 不如恒猜多数档 |

## skills/ — 十一层漏斗(应用层)

`viral-content-recon` 是编排器, 强制走完整漏斗避免只拆表层。CCE 是它底下的引擎:
suite 负责拆解与生成(事后闭环), 引擎负责事前预测。

⚠️ **粒度纪律(硬边界)**: 可预测的是**创作者/受众级**共振与**个体级**身份结构;
**单帖级不可预测**(已三重实锤), 禁止任何"这条会爆"的宣称。
