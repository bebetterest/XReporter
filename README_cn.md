# XReporter

[English](./README.md) | 中文

XReporter 是一个以 CLI 为核心的数据管线工具：从目标 X 用户关注列表采集活动，归一化写入 SQLite，并生成静态 HTML 报告。

当前版本：`0.1.0`（MVI）

## 开始前须知

- 使用 X 官方 API 的真实成本通常较高（价格与配额可能成为瓶颈）。
- 仓库中的 SocialData provider 已实现并覆盖测试，但完整生产环境验证仍在进行中。

## 为什么使用 XReporter

- 可复现：每次采集都有 run 记录（`runs`、`run_activities`、`run_warnings`）。
- 可重复运行：upsert/幂等策略避免核心数据重复。
- 可审查：HTML 报告提供告警区、按原帖聚合、按用户聚合和时间线视图。
- 可落地：支持 `official`/`socialdata` 切换，并支持 fixture 离线模式。

## 快速导航

- [3 分钟上手](#3-分钟上手)
- [报告结构说明](#报告结构说明)
- [技术路线速览](#技术路线速览)
- [CLI 命令速查](#cli-命令速查)
- [配置说明](#配置说明)
- [仓库结构总览](#仓库结构总览)
- [开发与测试](#开发与测试)
- [常见问题](#常见问题)
- [贡献指南](#贡献指南)

## 3 分钟上手

### 1）准备环境

```bash
conda env create -f environment.yml
conda activate XReporter
pip install -e .[dev]
```

### 2）配置凭据（仅环境变量）

```bash
# official provider
export X_BEARER_TOKEN="<your_token>"

# socialdata provider
export SOCIALDATA_API_KEY="<your_socialdata_api_key>"
```

密钥不会写入项目配置文件。

### 3）初始化配置

```bash
xreporter config init --username target_user --lang auto
# 新配置默认 provider=official
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

## 报告结构说明

生成结果为静态 HTML，包含：

- 告警区（provider/用户/API 路径/原始错误）
- 按原帖聚合区（发帖/转发/引用/回复）
- 按用户聚合区（同一用户的全部活动）
- 完整活动时间线

交互与排序规则：

- 按原帖聚合区、按用户聚合区、完整时间线都支持折叠/展开（默认折叠）
- 聚合区中的每个 item 卡片也支持折叠/展开（默认折叠），适合长内容
- 时间线按时间从近到远排序
- 按原帖聚合区先按活动数降序，再按最新活动时间降序
- 按用户聚合区先按活动数降序，再按最新活动时间降序
- 报告文案跟随配置语言（`en`/`zh`；`auto` 按 locale 回退）

## 技术路线速览

```text
CLI (Typer + Rich)
  -> Config + i18n
  -> CollectorService
       -> provider adapter (XApiClient / SocialDataApiClient / FixtureXApiClient)
       -> normalizer
       -> SQLiteStorage
  -> HTML renderer
```

详细技术路线： [doc/tech_route.md](./doc/tech_route.md) | [中文](./doc/tech_route_cn.md)

## CLI 命令速查

1. `xreporter config init --username <name> [--lang auto|en|zh] [--db-path <path>] [--report-dir <path>] [--following-cap <int>] [--include-replies/--no-include-replies] [--api-provider official|socialdata]`
2. `xreporter config show`
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`

### 典型工作流

```bash
# 1) 初始化（一次）
xreporter config init --username jack --lang auto --following-cap 200

# 2) 采集一个时间窗口
xreporter collect --last 24h

# 3) 渲染最新 run
xreporter render --latest

# 4) 或渲染指定 run
xreporter render --run-id 3 --output ./reports/manual_run_3.html
```

## 配置说明

默认配置路径：

- `~/.xreporter/config.toml`

配置字段：

- `username`（字符串）
- `language`（`auto|en|zh`）
- `db_path`（字符串）
- `report_dir`（字符串）
- `following_cap_default`（整数，默认 `200`）
- `include_replies_default`（布尔，默认 `true`）
- `api_provider`（`official|socialdata`；旧配置缺失字段时默认 `official`）

## Provider 说明

- `official`
  - 与 X 官方 API 结构最一致
  - 需要 `X_BEARER_TOKEN`
  - 在某些权限等级下，成本与限流压力可能较大
- `socialdata`
  - 需要 `SOCIALDATA_API_KEY`
  - 适配器包含端点回退与字段归一化
  - 时间线 `403` 隐私响应会记录告警并跳过
  - 本仓库内完整生产验证仍在进行中
- `fixture`
  - 设置 `XREPORTER_FIXTURE_FILE` 后可离线演示/测试（无需真实 API）

## 数据模型

SQLite 核心表：

- `users`、`tweets`、`tweet_links`、`activities`
- `runs`、`run_activities`、`run_warnings`

## 仓库结构总览

```text
src/xreporter/
  cli.py        # 命令入口与编排
  config.py     # 配置读写与默认路径
  i18n.py       # 语言解析与文案
  models.py     # 类型化数据契约
  normalizer.py # payload -> 归一化 batch
  service.py    # 采集流程与告警处理
  storage.py    # SQLite schema/upsert/run 元数据
  render.py     # 静态 HTML 渲染
  time_range.py # last/since/until 解析
  x_api.py      # official/socialdata/fixture clients
tests/
doc/
```

## 开发与测试

```bash
conda activate XReporter
pytest
```

当前测试重点：

- 单元：时间解析、i18n 回退、活动分类、SQLite 幂等
- 集成：分页、`429/5xx` 重试、缺失引用帖补拉
- 端到端：fixture `collect -> render`、重复运行幂等、中英文 CLI 行为

## 常见问题

### `xreporter doctor` 提示凭据异常

- 先确认当前 provider：`xreporter config show`
- `official` 检查 `X_BEARER_TOKEN`
- `socialdata` 检查 `SOCIALDATA_API_KEY`

### 渲染出来是空报告

- `--latest` 可能指向失败 run（活动数为 0）
- 可改用指定 run 渲染：

```bash
xreporter render --run-id <id> --output ./reports/run_<id>.html
```

### 报告语言不符合预期

- 将配置语言设为显式 `en` 或 `zh`，不要使用 `auto`

## 贡献指南

欢迎提 Issue / PR。建议流程：

1. 在 Issue 中明确目标行为与范围
2. 按仓库模块边界组织改动（`x_api.py`、`normalizer.py`、`storage.py`、`render.py`、`cli.py`）
3. 新行为补充测试
4. 保持中英文文档同步（`*_cn.md`）

## 相关文档

- 技术路线： [doc/tech_route.md](./doc/tech_route.md) / [doc/tech_route_cn.md](./doc/tech_route_cn.md)
- 进度日志： [doc/progress.md](./doc/progress.md) / [doc/progress_cn.md](./doc/progress_cn.md)
- Agent 规范： [AGENTS.md](./AGENTS.md) / [AGENTS_cn.md](./AGENTS_cn.md)
