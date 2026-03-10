# XReporter

XReporter 是一个以 CLI 为核心的工具：在设定时间窗口内采集目标 X.com 用户关注列表中的活动数据，归一化存入 SQLite，并渲染为静态 HTML 报告，便于查看和跳转原帖。

## 当前版本

- 版本：`0.1.0`（MVI）
- 已实现主链路：`config -> collect -> sqlite -> render`
- API 模式：通过配置切换多来源（`official`、`twscrape`、`socialdata`）
- 离线演示/测试模式：通过 `XREPORTER_FIXTURE_FILE` 使用固定数据

## 功能（v0.1）

- CLI 命令：
1. `xreporter config init --username <name> [--lang auto|en|zh] [--db-path <path>] [--report-dir <path>] [--following-cap <int>]`
   - provider 选项：`[--api-provider official|twscrape|socialdata] [--twscrape-accounts-db-path <path>]`
2. `xreporter config show`
3. `xreporter collect [--username <name>] [--last 12h|24h | --since <ISO8601> --until <ISO8601>] [--following-cap <int>] [--include-replies/--no-include-replies]`
4. `xreporter render [--run-id <id> | --latest] [--output <html_path>]`
5. `xreporter doctor`
- 时间范围支持：`12h`、`24h`、自定义绝对时间范围。
- 活动类型：`tweet`、`retweet`、`quote`、`reply`。
- 聚合能力：按原帖对转发/引用/回复进行聚合。
- SocialData 私密内容处理：时间线遇到 `403` 隐私限制时会记录为运行告警并跳过，采集继续执行。
- i18n：中英文界面，支持自动语言识别；若本地语言不是中/英文则回退英文。
- 使用 Rich 任务条显示进度。

## 环境搭建（Conda）

使用名为 `XReporter` 的 conda 环境。

```bash
conda env create -f environment.yml
conda activate XReporter
```

如果环境已存在：

```bash
conda activate XReporter
pip install -e .[dev]
```

## 凭据

各 provider 凭据（仅环境变量）：

```bash
# official
export X_BEARER_TOKEN="<your_token>"

# socialdata
export SOCIALDATA_API_KEY="<your_socialdata_api_key>"

# twscrape 首次引导（账号池为空时必填）
export XREPORTER_TWS_USERNAME="<x_username>"
export XREPORTER_TWS_PASSWORD="<x_password>"
export XREPORTER_TWS_EMAIL="<email_for_verification>"
export XREPORTER_TWS_EMAIL_PASSWORD="<email_password>"
```

XReporter 不会将凭据写入配置文件。

对于 `twscrape`，凭据要求取决于账号池状态：

- 若 `twscrape_accounts_db_path` 中还没有账号，必须提供 4 个 `XREPORTER_TWS_*` 变量。
- 若账号池已存在至少一个账号，XReporter 会复用账号池，此时邮箱相关凭据可不强制提供。

## 快速开始

1. 初始化配置：

```bash
xreporter config init --username target_user --lang auto
# 新建配置默认 api_provider=twscrape
```

2. 采集数据：

```bash
xreporter collect --last 24h
# 或
xreporter collect --since 2026-03-09T00:00:00+08:00 --until 2026-03-10T00:00:00+08:00
```

3. 渲染报告：

```bash
xreporter render --latest
```

4. 健康检查：

```bash
xreporter doctor
```

## twscrape 使用说明

### 首次引导（账号池为空）

1. 设置完整 twscrape 凭据：

```bash
export XREPORTER_TWS_USERNAME="<x_username>"
export XREPORTER_TWS_PASSWORD="<x_password>"
export XREPORTER_TWS_EMAIL="<email_for_verification>"
export XREPORTER_TWS_EMAIL_PASSWORD="<email_password>"
```

2. 初始化 provider 与账号池路径：

```bash
xreporter config init \
  --username target_user \
  --api-provider twscrape \
  --twscrape-accounts-db-path ~/.xreporter/twscrape_accounts.db
```

3. 校验并执行：

```bash
xreporter doctor
xreporter collect --last 24h
xreporter render --latest
```

### 复用已有账号池

当 `~/.xreporter/twscrape_accounts.db`（或你配置的路径）中已存在账号记录时：

- 可在不强制提供邮箱凭据的情况下执行 `doctor` 和 `collect`。
- XReporter 会跳过新增账号步骤，直接对已有账号执行 `login_all`。
- 若账号池实际为空，采集仍会报缺少凭据错误，此时需要先做一次首次引导。

## 配置项

默认配置路径：

- `~/.xreporter/config.toml`

配置结构：

- `username`（字符串）
- `language`（`auto|en|zh`）
- `db_path`（字符串）
- `report_dir`（字符串）
- `following_cap_default`（整数，默认 `200`）
- `include_replies_default`（布尔，默认 `true`）
- `api_provider`（`official|twscrape|socialdata`；旧配置缺失该字段时默认 `official`）
- `twscrape_accounts_db_path`（字符串，默认 `~/.xreporter/twscrape_accounts.db`）

## 项目结构

```text
src/xreporter/
  cli.py
  config.py
  i18n.py
  models.py
  normalizer.py
  render.py
  service.py
  storage.py
  time_range.py
  x_api.py
tests/
doc/
```

## 测试

```bash
pytest
```

测试覆盖：

- 单元测试：时间解析、i18n 回退、活动分类、SQLite 幂等性
- 集成测试：分页、429 重试、缺失引用帖回补
- 端到端测试：fixture `collect -> render`、重复采集幂等、中英文切换

## 说明

- X API 权限等级会影响可采集范围和速率限制。
- 可在配置中切换 provider，归一化/存储/渲染链路无需改动。
- 报告新增红色告警区，展示原始 provider 错误信息（用户名/链接/API 路径/错误体）。
- 关注列表较大时，应结合 API 配额调整 `--following-cap`。
- 仓库遵循中英文文档同步（`*_cn.md`）。
