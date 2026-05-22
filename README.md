# Chat-box-auto-open 实验分析

A/B 实验一次性分析脚本：读取两个 CSV 文件，输出单个自包含的 HTML 报告。

## 目录结构

```
analyze-experiment/
├── [experiment-name]/              # 每个实验一个目录（如 chat-box-auto-open、ai-filter-entrance）
│   ├── data/
│   │   ├── ots_chat.csv            # 聊天事件数据（包含 variant 标签）
│   │   ├── redirects.csv           # 跳转事件数据
│   │   ├── actions.csv             # 本分析不使用
│   │   └── ots_matched_hotels.csv  # 本分析不使用
│   └── output/
│       └── report.html             # 生成的报告（运行后出现）
├── analysis/
│   ├── main.py         # CLI 入口，负责编排整个分析流程
│   ├── load.py         # 加载 CSV、检测是否有 variant 冲突
│   ├── engagement.py   # 计算 8 个参与度指标 + rounds 指标 + 每日趋势
│   ├── redirects.py    # 计算 4 个跳转率指标 + funnel 指标 + 每日趋势
│   ├── stats.py        # 双比例 z 检验、Welch t 检验、95% 置信区间
│   ├── render.py       # 将结果渲染为 Jinja2 HTML 模板
│   ├── types.py        # 共享数据类定义
│   └── templates/
│       └── report.html.j2  # HTML 报告模板
├── tests/
└── requirements.txt
```

## 各模块职责

| 文件 | 职责 |
|------|------|
| `main.py` | 解析 CLI 参数，按顺序调用各模块，将报告写入 `[experiment-name]/output/report.html` |
| `load.py` | 从 `[experiment-name]/data/` 读取 `ots_chat.csv` 和 `redirects.csv`，构建 `variant_lookup`，识别并排除 variant 冲突的 utid |
| `engagement.py` | 基于 `chat_type`（SUGGESTIONS / INTENT_RECOGNITION）在 4 个聚合维度（utid / chat_session_id / request_id / correlation_id）上计算绝对量和比率指标，以及每日趋势数据 |
| `redirects.py` | 将 `ots_chat`（仅 INTENT_RECOGNITION 行）与 `redirects` 通过 `correlation_id = pre_redirect_id` 连接，计算各维度跳转率和全体用户漏斗跳转率 |
| `stats.py` | 对所有比率指标执行双比例 z 检验，对 rounds 均值执行 Welch t 检验；输出 p 值、95% CI 及方向性结论 |
| `render.py` | 用 Plotly 生成内联图表（A/B 对比柱状图 + 每日趋势折线图），通过 Jinja2 模板渲染最终 HTML |
| `types.py` | 定义 `EngagementMetric`、`RedirectMetric`、`RoundsMetric`、`DailyTrend` 等数据类 |

## 快速上手

**1. 创建虚拟环境并安装依赖**（在项目根目录执行）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

**2. 运行分析**

```bash
# 默认分析 chat-box-auto-open
python -m analysis.main --verbose

# 切换实验只需改一个参数
python -m analysis.main --experiment ai-filter-entrance --verbose
```

**3. 查看报告**

```bash
open chat-box-auto-open/output/report.html   # macOS
```

报告输出到 `<experiment>/output/report.html`（目录不存在时自动创建）。报告包含：执行摘要（SHIP / DO NOT SHIP / INCONCLUSIVE 结论）、数据概览、参与度分析、跳转分析、附录。

**可选参数**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--experiment` | `chat-box-auto-open` | 实验目录名，data/output 路径据此派生 |
| `--data-dir` | `<experiment>/data` | 覆盖输入 CSV 目录 |
| `--output` | `<experiment>/output/report.html` | 覆盖报告输出路径 |
| `--flat-threshold` | `2.0` | 相对提升绝对值低于该百分比视为"持平" |
| `--alpha` | `0.05` | 统计显著性阈值 |
| `--verbose` | 关 | 输出各阶段耗时到 stderr |

**4. 运行测试**

```bash
pytest tests/ -v
```

测试覆盖：数据加载与 variant 冲突检测、参与度指标计算、跳转连接逻辑、统计检验（已知结果对照）、每日趋势聚合。

## 数据说明

- **variant A**：对照组（手动打开聊天框）
- **variant B**：实验组（自动打开聊天框）
- `ots_chat.csv` 是 variant 标签的唯一来源；`redirects.csv` 不含 variant 列，通过 join 继承
- 空 `chat_session_id` 的行仍计入 SUGGESTIONS 总量，但在按 session 聚合时被排除

详细 spec 见 [specs/001-chat-box-auto-open-analysis/spec.md](specs/001-chat-box-auto-open-analysis/spec.md)。
