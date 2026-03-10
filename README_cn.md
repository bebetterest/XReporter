# XReporter

> 重要说明：
>
> - 使用 X 官方 API 的真实成本通常较高（价格与配额很容易成为瓶颈）。
> - 仓库中已经实现 SocialData provider 适配与测试，但尚未完成完整实网验证。

XReporter 是一个以 CLI 为核心的数据管线工具，负责：

- 在指定时间窗口采集目标 X 用户关注列表中的活动；
- 将数据归一化后写入 SQLite（支持重复运行去重）；
- 渲染为静态 HTML 报告，便于浏览和跳转原帖。

当前版本：`0.1.0`（MVI），可运行主链路为 `config -> collect -> sqlite -> render`。

## 能做什么

- 多 provider 采集：`official` / `socialdata`（配置切换）。
- 时间范围：`--last 12h|24h` 或绝对时间 `--since/--until`（ISO8601）。
- 活动归一化：`tweet`、`retweet`、`quote`、`reply`。
- 报告支持按原帖聚合 + 按时间线浏览。
- 支持将 provider 的部分失败记录为运行告警（`run_warnings`）。
- CLI 支持中英文与自动语言（`en`、`zh`、`auto`）。
- 支持 `XREPORTER_FIXTURE_FILE` 离线演示/测试模式。

## 3 分钟上手

### 1）准备环境

使用 conda 环境 `XReporter`：

```bash
conda env create -f environment.yml
conda activate XReporter
pip install -e .[dev]
```

### 2）配置凭据（仅环境变量）

```bash
# official
export X_BEARER_TOKEN="<your_token>"

# socialdata
export SOCIALDATA_API_KEY="<your_socialdata_api_key>"
```

XReporter 不会把凭据写入项目配置文件。

### 3）初始化配置

```bash
xreporter config init --username target_user --lang auto
# 新建配置默认 provider=official
```

### 4）采集并渲染

```bash
xreporter collect --last 24h
xreporter render --latest
```

### 5）健康检查

```bash
xreporter doctor
```

## CLI 命令

1. `xreporter config init --username <name> [--lang auto|en|zh] [--db-path <path>] [--report-dir <path>] [--following-cap <int>] [--include-replies/--no-include-replies] [--api-provider official|socialdata]`
2. `xreporter config show`
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`

## 典型工作流

```bash
# 1) 初始化（一次）
xreporter config init --username jack --lang auto --following-cap 200

# 2) 采集一个时间窗口
xreporter collect --last 24h

# 3) 渲染最新一次运行
xreporter render --latest

# 4) 或渲染指定运行
xreporter render --run-id 3 --output ./reports/manual_run_3.html
```

## 配置说明

默认配置路径：

- `~/.xreporter/config.toml`

字段说明：

- `username`（字符串）
- `language`（`auto|en|zh`）
- `db_path`（字符串）
- `report_dir`（字符串）
- `following_cap_default`（整数，默认 `200`）
- `include_replies_default`（布尔，默认 `true`）
- `api_provider`（`official|socialdata`；旧配置缺失该字段时默认 `official`）

## Provider 说明

- `official`：
  - 与 X 官方 API 结构最对齐；
  - 需要 `X_BEARER_TOKEN`；
  - 成本与速率限制压力可能较大（取决于权限等级与调用量）。
- `socialdata`：
  - 需要 `SOCIALDATA_API_KEY`；
  - 适配器已实现多端点回退和字段归一化；
  - 时间线 `403` 隐私限制会记录告警并跳过；
  - 本仓库内完整生产验证状态：待完成。
- `fixture`：
  - 设置 `XREPORTER_FIXTURE_FILE` 后可离线跑通演示/测试。

## 输出与数据模型

- SQLite 核心表：
  - `users`、`tweets`、`tweet_links`、`activities`
  - `runs`、`run_activities`、`run_warnings`
- HTML 报告包含：
  - 告警区（provider/用户/API 路径/原始错误）
  - 按原帖聚合的转发/引用/回复区
  - 按时间排序的活动时间线

## 架构概览

```text
CLI (Typer + Rich)
  -> Config + i18n
  -> CollectorService
       -> provider adapter (XApiClient / SocialDataApiClient / FixtureXApiClient)
       -> normalizer
       -> SQLiteStorage
  -> HTML renderer
```

代码结构：

```text
src/xreporter/
  cli.py        # 命令入口与编排
  config.py     # 配置读写与默认路径
  i18n.py       # 语言解析与文案
  models.py     # 类型化数据模型
  normalizer.py # 原始 payload -> 归一化 batch
  service.py    # 采集流程与告警处理
  storage.py    # SQLite schema/upsert/run 元数据
  render.py     # 静态 HTML 渲染
  time_range.py # 时间参数解析
  x_api.py      # official/socialdata/fixture 客户端
tests/
doc/
```

## 开发与测试

运行测试：

```bash
conda activate XReporter
pytest
```

当前测试重点：

- 单元：时间解析、i18n 回退、活动分类、SQLite 幂等
- 集成：分页、`429/5xx` 重试、缺失引用帖补拉
- 端到端：fixture `collect -> render`、重复运行幂等、中英文 CLI 行为

## 相关文档

- 仓库遵循中英文文档同步（`*_cn.md`）。
- 技术路线：`doc/tech_route.md` / `doc/tech_route_cn.md`
- 进度记录：`doc/progress.md` / `doc/progress_cn.md`
