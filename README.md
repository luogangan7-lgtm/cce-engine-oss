# CCE Engine

认知因果引擎的执行链。**每次运行都有永久 URL 和完整日志——"跑没跑完整"是可核事实,不是口头声明。**

## 链路

| 模式 | 段 |
|---|---|
| `reply` | s1_readout → s2_knots → s3_emotion_policy → s4_guard |
| `post` | 上述4段 + s5_audience → s6_alignment → s7_ruler → s8_pairwise_bet |

任一段失败即 `complete=false`,链路中止,manifest 记录 `failed_at`。

## 投料规范

| 字段 | 必填 | 说明 |
|---|---|---|
| `mode` | ✓ | `reply` 或 `post` |
| `text` | ✓ | 待评内容逐字原文 |
| `context` | ✓ | 语境(板块/平台/上下文) |
| `audience` | post必填 | **目标读者原话语料**,≥3条/≥80词。留空回退 `corpus/` 默认语料 |
| `ref_tag` | post必填 | 运行标识,用于回溯 |

⚠️ `audience` **不能传人群画像描述**(如"美国普通消费者")。s5 受众逆推吃的是真实发言;传描述等于让模型给一句话做九结分类,读数退化且方差极大(实测4轮4个不同主结)。校验在 `.github/prepare.py`,不合规直接失败。

## s6 对齐算子 v2

```
对齐分 = Σ(推动族受众结) w × 稿件该结权重        [共鸣]
       + Σ(阻挡族受众结) w × 拆除动作命中度(0-1)  [拆除]
```

v1 的裸 argmax + 集合成员判定已废弃:阻挡族(suspend/inertia/audit)按定义不可能出现在稿件结里,内容只能**拆除**它不能**携带**它,旧规则在受众主结落阻挡族时恒不可满足。

阈值 `CCE_ALIGN_THETA`(仓库变量,默认 0.35)。**标定状态:未完成**——四篇已发布帖真语料得分 0.175~0.315,跨run方差与样本间差异同量级,4样本不足以立硬阈值。

## 触发

```bash
# 单条
gh workflow run cce.yml -f mode=post -f text="..." -f context="..." -f ref_tag=xxx

# 批量(matrix 并行)
gh api repos/OWNER/REPO/dispatches -f event_type=cce-batch \
  -F 'client_payload[items][]=...'
```

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
