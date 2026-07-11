# PalChronicle · 帕鲁纪事（astrbot_plugin_palword）

> 只读的 Palworld 世界纪事、玩家档案与社区观察 AstrBot 插件，基于官方 REST API。

## 安全与隐私（请先阅读）

- **只读**：本插件仅调用官方只读端点 `/info`、`/metrics`、`/players`、`/settings`、`/game-data`，**不控制服务器**、不执行任何写/管理操作。
- **不存储 IP**：入口即删除 IP、Basic Auth 凭证、原始平台账号与原始内部 ID；玩家标识仅以 `HMAC-SHA256(salt, world_id + ":" + raw_user_id)` 落库。
- **不公开精确位置**：坐标默认量化为粗网格；`strict` 隐私模式下坐标完全不落库、据点模块停用。Ping 仅以“优秀/正常/偏高”分桶展示，不存原始数值。
- **需在服务器端启用 REST**：Palworld 服务器须开启 REST API（`RESTAPIEnabled=True` 并设置管理员密码）。
- **勿暴露公网**：REST API 请勿直接暴露到公网，走 localhost / 内网 / VPN / 反向代理；密码建议用环境变量（`password_env`）而非明文。

## 环境要求

- AstrBot ≥ 4.10.4（建议最新 4.26.x）
- Python ≥ 3.11
- SQLite 3

## 安装

1. 将本插件放入 AstrBot 的 `plugins/` 目录（或通过插件市场安装）。
2. 安装依赖：`pip install -r requirements.txt`（aiohttp、aiosqlite、PyYAML、tzdata）。
3. 在 AstrBot 网页配置页填写服务器与路由（见下）。
4. 重载插件。

## 配置

在插件配置页：

- **servers（多服务器）**：可添加多台 Palworld 服务器。`name` 唯一且不含空格/冒号/`@`；`base_url` 如 `http://127.0.0.1:8212`；密码填 `password_env`（环境变量名，推荐）或 `password`（明文，会落盘）。
- **routing.access_mode**：默认 `restricted`（群需管理员授权才能查询某服务器）；`open` 为任意群可查任意服务器。
- **group_bindings（可选预设授权）**：等价于管理员执行 `/pal use`，仅作**初始种子**，不覆盖运行时改动。
- **privacy.mode**：`strict` / `balanced`（默认）/ `advanced`（v0.1 按 balanced 生效）。

## 多服务器与群授权用法

- `/pal servers`：列出所有服务器与本群授权/活动状态。
- `/pal use <名称>`（管理员，仅群聊）：授权本群使用该服务器并设为活动服务器。
- `/pal unbind <名称>`（管理员）：撤销本群对该服务器的授权。
- **@server 尾缀**：任意查询命令可在末尾加 `@<服务器名>` 单次指定目标服务器，如 `/pal status @alpha`、`/pal guild 晨曦联盟 @beta`（服务器名不含空格，公会/据点名可含空格）。

## 命令一览（全部只读、纯文本）

`/pal status`、`/pal online`、`/pal world`、`/pal rules`、`/pal guilds`、`/pal guild <名称>`、
`/pal bases`、`/pal base <名称|#序号>`、`/pal events`、`/pal today`、`/pal help`、
`/pal servers`、`/pal use <名称>`、`/pal unbind <名称>`。

## 降级说明

API 不可达时显示“当前无法获取世界数据，最后成功更新 N 分钟前”，**绝不**臆断“服务器已关机”。部分端点失败时降级相关模块，其余照常。

## 许可证

见 LICENSE。
