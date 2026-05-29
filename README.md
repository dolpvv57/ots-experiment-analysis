# analyze-experiment

A/B 实验分析框架：从 CSV 数据生成单个自包含 HTML 报告。

每个实验有自己的数据目录，共享分析框架（engagement / redirect / 统计检验），并可选地挂载一个"插件"来扩展实验专属分析。

---

## 目录结构

```
analyze-experiment/
├── analysis/                    # 共享分析框架（不需要改动）
│   ├── plugin.py                # 插件接口定义（PluginSection）
│   ├── main.py                  # CLI 入口，自动发现并运行实验插件
│   ├── load.py                  # 加载 CSV，检测 variant 冲突
│   ├── engagement.py            # 参与度指标（8 个比率 + rounds）
│   ├── redirects.py             # 跳转率指标（4 个维度 + funnel）
│   ├── stats.py                 # z 检验、Welch t 检验、置信区间
│   ├── render.py                # Plotly 图表 + Jinja2 渲染
│   ├── types.py                 # 共享 dataclass 类型
│   └── templates/
│       └── report.html.j2       # 主报告模板（engagement + redirect）
│
├── chat-box-auto-open/          # 实验目录示例（有插件）
│   ├── data/                    # ots_chat.csv, redirects.csv, actions.csv
│   ├── output/                  # report.html（运行后生成）
│   ├── plugin.py                # 实验专属分析（地图使用率）
│   └── templates/
│       └── section.html.j2      # 实验专属报告 section
│
├── ai-filter-entrance/          # 实验目录示例（有插件）
│   ├── data/
│   ├── output/
│   ├── plugin.py                # 实验专属分析（入口位置分析）
│   └── templates/
│       └── section.html.j2
│
├── tests/                       # 单元测试（覆盖共享框架）
└── requirements.txt
```

---

## 快速上手（生成报告）

**1. 创建虚拟环境并安装依赖**（在项目根目录执行）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

**2. 运行分析**

```bash
# 分析 ai-filter-entrance 实验（默认）
python -m analysis.main --verbose

# 切换实验只需改 --experiment 参数
python -m analysis.main --experiment chat-box-auto-open --verbose
```

**3. 查看报告**

```bash
open ai-filter-entrance/output/report.html   # macOS
```

报告输出到 `<experiment>/output/report.html`，目录不存在时自动创建。

**可选参数**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--experiment` | `ai-filter-entrance` | 实验目录名，data/output 路径据此派生 |
| `--data-dir` | `<experiment>/data` | 覆盖输入 CSV 目录 |
| `--output` | `<experiment>/output/report.html` | 覆盖报告输出路径 |
| `--flat-threshold` | `2.0` | 相对提升绝对值低于该百分比视为"持平" |
| `--alpha` | `0.05` | 统计显著性阈值 |
| `--verbose` | 关 | 输出各阶段耗时到 stderr |

**4. 运行测试**

```bash
pytest tests/ -v
```

---

## 报告内容

每份报告固定包含：

- **执行摘要**：SHIP / DO NOT SHIP / INCONCLUSIVE 结论
- **数据概览**：行数、variant 人数、排除的 utid 数
- **参与度分析**：8 个 engagement 指标（`SUGGESTIONS × {utid,session,request,correlation}` + `INTENT_RECOGNITION × 同上`）+ rounds 均值 + 每日趋势
- **跳转分析**：all-chat 跳转率、INTENT-only 跳转率、funnel 跳转率 + 每日趋势
- **实验专属 section**（若实验目录有 `plugin.py`，自动追加）
- **附录**：方法论说明、多重比较注释

---

## 添加新实验（面向开发者）

新实验只需在自己目录里创建文件，**不改任何 `analysis/` 框架代码**。

### 最小结构

```
<your-experiment>/
├── data/
│   ├── ots_chat.csv
│   └── redirects.csv
└── output/           # 自动创建
```

没有 `plugin.py` 时，报告只包含通用的 engagement + redirect 分析，直接跑即可：

```bash
python -m analysis.main --experiment <your-experiment>
```

### 添加实验专属 section（plugin）

如果需要在报告里追加自定义分析，在实验目录创建 `plugin.py` 和 `templates/section.html.j2`。

**`plugin.py` 接口约定（duck typing，无需继承）：**

```python
from __future__ import annotations
from dataclasses import dataclass
from analysis.load import DataBundle

# 必须：Jinja2 模板路径，相对于本文件所在目录
TEMPLATE_FRAGMENT = "templates/section.html.j2"

# 必须：运行分析，返回任意 dataclass
def compute(bundle: DataBundle, excluded_utids: set[str]) -> MySection:
    # bundle.ots_chat   — ots_chat.csv 的 DataFrame
    # bundle.redirects  — redirects.csv 的 DataFrame
    # bundle.data_dir   — data/ 目录路径（用于读取其他 CSV）
    # excluded_utids    — 已排除的 variant 冲突 utid 集合
    ...

# 必须：该 section 贡献多少个统计假设检验（用于 total_tests 注释）
def count_tests(section: MySection) -> int:
    return len(section.some_metrics)

# 可选：返回 chart_id -> Plotly HTML div 字符串
def build_charts(section: MySection) -> dict[str, str]:
    ...
```

**`templates/section.html.j2` 可用变量：**

| 变量 | 类型 | 说明 |
|------|------|------|
| `section` | `MySection` | `compute()` 的返回值 |
| `charts` | `dict[str, str]` | `build_charts()` 的返回值（无图表时为空 dict） |

模板内可使用主模板的所有 Jinja2 过滤器：`fmt_pct`、`fmt_pp`、`fmt_lift`、`fmt_p`、`fmt_num`。

**示例：最简单的 plugin**

```python
# my-experiment/plugin.py
from dataclasses import dataclass
from analysis.load import DataBundle

TEMPLATE_FRAGMENT = "templates/section.html.j2"

@dataclass(frozen=True)
class MySection:
    total_actions: int

def compute(bundle: DataBundle, excluded_utids: set[str]) -> MySection:
    actions = __import__("pandas").read_csv(bundle.data_dir / "actions.csv")
    return MySection(total_actions=len(actions))

def count_tests(section: MySection) -> int:
    return 0
```

```jinja2
{# my-experiment/templates/section.html.j2 #}
<section id="my-section">
<h2>My Custom Analysis</h2>
<p>Total actions: {{ section.total_actions }}</p>
</section>
```

---

## 数据说明

- **variant A**：对照组，**variant B**：实验组
- `ots_chat.csv` 是 variant 标签的唯一来源；`redirects.csv` 通过 join 继承 variant
- `actions.csv`：实验专属数据，仅在 `plugin.py` 里按需读取

### ots_chat.csv 字段

| 字段 | 说明 |
|------|------|
| `utid` | 用户标识 |
| `chat_session_id` | 聊天会话 ID（可为空） |
| `chat_type` | `CHAT_TYPE_SUGGESTIONS` 或 `CHAT_TYPE_INTENT_RECOGNITION` |
| `rounds` | 本 session 的轮次数 |
| `request_id` | 请求 ID |
| `correlation_id` | 关联 ID（用于与 redirects 连接） |
| `variant` | `A` 或 `B` |
| `dt` | 日期 |

### redirects.csv 字段

| 字段 | 说明 |
|------|------|
| `utid` | 用户标识 |
| `pre_redirect_id` | 对应 `ots_chat.correlation_id` |
| `dt` | 日期 |

---

## 各模块职责

| 文件 | 职责 |
|------|------|
| `analysis/main.py` | CLI 入口；编排分析流程；自动发现并运行 `<experiment>/plugin.py` |
| `analysis/load.py` | 读取 CSV，构建 variant lookup，排除冲突 utid |
| `analysis/engagement.py` | 8 个参与度指标 + rounds + 每日趋势 |
| `analysis/redirects.py` | 跳转率指标（4 维度 + funnel）+ 每日趋势 |
| `analysis/stats.py` | 双比例 z 检验、Welch t 检验、95% 置信区间 |
| `analysis/render.py` | Plotly 图表 + Jinja2 渲染；`build_map_rate_chart()` 可供 plugin 复用 |
| `analysis/plugin.py` | `PluginSection` dataclass（框架内部使用） |
| `analysis/types.py` | 共享类型：`EngagementMetric`、`RedirectMetric` 等 |
