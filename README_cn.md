# XReporter

[English](./README.md) | 中文

你有没有遇到过这种情况：刷 X 时，明明是同一条原帖，却因为多个关注用户转发/引用而在时间线里反复出现？又或是不能一眼看出哪些帖子是我关注的用户中活跃度最高的。
XReporter 就是为这个场景做的。它是一个以 CLI 为核心的数据管线工具：从目标 X 用户关注列表采集活动，归一化写入 SQLite，并生成静态 HTML 报告。
核心思路很简单：先合并去重，再原帖聚合并按活动数排序。你可以先看到关注圈里的热点帖子，再展开查看每位关注用户的具体相关动作（转发、引用、回复）🔍

当前版本：`0.1.0`（MVI）

> 说明：本项目主要由 Codex 操作并实现。

## 开始前须知

- 使用 X 官方 API 的真实成本通常较高（价格与配额可能成为瓶颈）。

## 为什么使用 XReporter

- 可复现：每次采集都有 run 记录（`runs`、`run_activities`、`run_warnings`）。
- 可重复运行：upsert/幂等策略避免核心数据重复。
- 可审查：HTML 报告提供告警区、按原帖聚合、按用户聚合和时间线视图。
- 可落地：支持 `official`/`socialdata` 切换，并支持 fixture 离线模式。

## 快速导航

- [3 分钟上手](#3-分钟上手)
- [示例报告](#示例报告)
- [报告结构说明](#报告结构说明)
- [技术路线速览](#技术路线速览)
- [CLI 命令速查](#cli-命令速查)
- [配置说明](#配置说明)
- [日志说明](#日志说明)
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

## 示例报告

- 英文示例：[example/run_1_en.html](./example/run_1_en.html)
- 中文示例：[example/run_1_zh.html](./example/run_1_zh.html)
- 来源 run：`betterestli`，`--last 12h`，`run_id=1`

英文预览：
![English report preview](./example/run_1_en.png)

中文预览：
![Chinese report preview](./example/run_1_zh.png)

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
  -> Config + i18n + logging bootstrap
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
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies] [--api-concurrency <int>] [--resume-run-id <id>]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`

### 典型工作流

```bash
# 1) 初始化（一次）
xreporter config init --username jack --lang auto --following-cap 200

# 2) 采集一个时间窗口
xreporter collect --last 24h --api-concurrency 4

# 3) 渲染最新 run
xreporter render --latest

# 4) 或渲染指定 run
xreporter render --run-id 3 --output ./reports/manual_run_3.html

# 5) 继续中断/失败 run
xreporter collect --resume-run-id 3 --api-concurrency 4
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

## 日志说明

- 默认日志文件：`~/.xreporter/logs/xreporter.log`
- 若设置 `XREPORTER_HOME`，日志路径变为 `$XREPORTER_HOME/logs/xreporter.log`
- 日志覆盖：命令生命周期、run 级采集进度、API 请求/重试/回退状态、存储落盘节点
- API 发生重试时，会同时写日志并在终端打印简要信息（不含敏感数据）
- 可选环境变量：
  - `XREPORTER_LOG_LEVEL`（`DEBUG|INFO|WARNING|ERROR`，默认 `INFO`）
  - `XREPORTER_LOG_STDERR`（`1|true|yes|on`）将日志同时输出到 stderr

## Provider 说明

- `official`
  - 与 X 官方 API 结构最一致
  - 需要 `X_BEARER_TOKEN`
  - 在某些权限等级下，成本与限流压力可能较大
- `socialdata`
  - 需要 `SOCIALDATA_API_KEY`
  - 适配器对齐文档端点与参数，避免发送不支持的过滤参数
  - 引用推文回补使用批量接口（`tweets-by-ids`）减少请求次数
  - 时间线 `403` 隐私响应会记录告警并跳过
- 时间线分页上限（防止浪费调用）
  - 默认每个 following 的时间线最多拉取 **5 页**（`official` 与 `socialdata` 都生效）
  - 当前是代码级参数（不是 CLI 参数）
  - 修改位置：
    - `src/xreporter/x_api.py` -> `XApiClient.__init__(..., max_timeline_pages=5)`
    - `src/xreporter/x_api.py` -> `SocialDataApiClient.__init__(..., max_timeline_pages=5)`
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
  logging_utils.py # 运行时日志初始化（滚动文件 + 级别控制）
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

### 需要排查请求与运行过程

- 查看 `~/.xreporter/logs/xreporter.log`（或 `$XREPORTER_HOME/logs/xreporter.log`）
- 设置 `XREPORTER_LOG_LEVEL=DEBUG` 可看到请求级重试与回退细节

### 采集耗时过长

- 新增分页保护会在 cursor/token 重复时自动中断循环并写告警日志。
- 另外默认每个 following 的 timeline 最多拉取 `5` 页（参数名 `max_timeline_pages`，位置 `src/xreporter/x_api.py`）。
- 若配额允许，可提高 API 并发：
  - `xreporter collect --last 24h --api-concurrency 8`
- 若仍耗时较长，可先缩小采集范围：
  - `xreporter collect --last 12h --following-cap 100 --no-include-replies`

### 采集中途被打断

- 可继续同一个 run，已完成 following 不会重复拉取：
  - `xreporter collect --resume-run-id <id> --api-concurrency 4`

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
