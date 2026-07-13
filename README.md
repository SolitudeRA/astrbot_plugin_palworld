<div align="center">

<img src="docs/images/banner.png" alt="PalWorldTerminal · 帕鲁世界终端" width="640">

# PalWorldTerminal · 帕鲁世界终端

[![version](https://img.shields.io/badge/version-v0.1.0-007ec6)](https://github.com/SolitudeRA/astrbot_plugin_palworld/releases)
[![python](https://img.shields.io/badge/python-3.11%2B-007ec6)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A5%204.24.1-fe7d37)](https://github.com/AstrBotDevs/AstrBot)
[![license](https://img.shields.io/badge/license-GPL--3.0-97ca00)](LICENSE)
[![Palworld](https://img.shields.io/badge/Palworld-1.0%2B-3f6ec6)](https://www.pocketpair.jp/palworld)

监测 Palworld 专用服务器,在群里提供状态查询、日报与玩家档案。<br>只读,基于官方 REST API。

只读 · 不存储 IP · 不公开精确位置 —— 详见[安全与隐私](#安全与隐私)

[功能特性](#功能特性) · [快速开始](#快速开始) · [指令](#指令) · [配置](#配置) · [安全与隐私](#安全与隐私) · [详细文档](#详细文档)

</div>

---

## 功能特性

- **世界状态一览** —— 在线人数、FPS 流畅度、世界天数(`/pal status`)
- **在线名单与今日日报** —— 谁在线、今日在线统计(`/pal online`、`/pal today`)
- **世界事件记录** —— 上下线、服务器重启等大事记(`/pal events`)
- **玩家排行与档案** —— 时长榜 / 等级榜、逐人查询、自助绑定与隐藏(`/pal rank`、`/pal me`)
- **多服务器 + 群授权** —— 一个插件监测多台服务器,按群授权、按群切换
- **WebUI 设置页** —— 可视化配置全部选项,亮暗双主题
- **隐私优先** —— 只读、不存 IP、玩家标识 HMAC 哈希落库、坐标量化为粗网格
- **公会与据点** —— 依赖上游开放 `game-data`,默认关闭,开放后一键启用

## 效果预览

`/pal status` 的回复长这样:

```text
世界：光之丘 · 第 60 天
在线：3/32 人 · 今日最高 5
据点：12（官方指标）
性能：FPS 59（流畅） · 帧时间 16.8ms
在线玩家：
  · 旅人A Lv42
  · 旅人B Lv38
  · 旅人C Lv17
```

## 快速开始

1. **服务器开启 REST API** —— `PalWorldSettings.ini` 设 `RESTAPIEnabled=True` 并设置管理员密码。**REST 端口勿暴露公网**,走 localhost / 内网 / VPN / 反向代理。
2. **安装插件** —— AstrBot 插件市场安装,或放入 `plugins/` 目录;依赖:`pip install -r requirements.txt`(运行时仅需 aiohttp、aiosqlite、tzdata;开发者改装 `requirements-dev.txt`)。
3. **填服务器** —— 打开插件设置页,「连接」章添加服务器:地址如 `http://127.0.0.1:8212`,密码推荐用环境变量(`password_env`)。
4. **授权本群** —— 群里由管理员执行 `/pal use <服务器名>`。
5. **开始查询** —— `/pal status`,看到世界状态就通了。

环境要求:AstrBot ≥ 4.24.1(插件设置页需此版本,建议最新 4.26.x)· Python ≥ 3.11 · SQLite 3。

## 指令

全部指令以 `/pal` 开头,只读、纯文本回复。常用:

| 指令 | 说明 |
|------|------|
| `/pal status` | 世界状态(在线数、FPS 流畅度等) |
| `/pal online` | 当前在线玩家名单 |
| `/pal today` | 今日日报 / 在线统计 |
| `/pal rank` | 排行榜(今日时长榜 + 等级榜) |
| `/pal me` | 我的档案;`hide`/`show` 自助隐藏 |
| `/pal servers` | 服务器列表与本群授权状态 |
| `/pal use <名称>` | **管理员** · 授权本群使用某服务器 |
| `/pal help` | 帮助(按启用的功能过滤) |

任意查询指令末尾加 `@<服务器名>` 可单次指定目标服务器,如 `/pal status @alpha`(多服务器场景)。
完整指令表、功能开关矩阵与群授权用法 → [docs/commands.md](docs/commands.md)

## 配置

全部配置可在 WebUI 设置页可视化完成,要点:

- **多服务器**:可添加多台;名称唯一,密码推荐 `password_env` 环境变量。
- **访问控制**:默认 `restricted`(群需管理员授权);`open` 为全开放。
- **功能开关**:按组启停,关闭的组不采集数据、指令提示未开放:

| 功能组 | 默认 | 指令 |
|--------|------|------|
| `report` 日报 | 开 | `today` |
| `events` 世界事件 | 开 | `events` |
| `players` 玩家查询 | **关** | `rank` `player` `me` `bind` |
| `guilds_bases` 公会与据点 | **关** | `guilds` `bases` 等 |

轮询间隔、FPS 阈值、隐私脱敏、数据保留、自定义请求头等全部配置项详解 → [docs/configuration.md](docs/configuration.md)

## 安全与隐私

- **只读**:仅调用官方只读端点 `/info`、`/metrics`、`/players`、`/settings`、`/game-data`,**不控制服务器**、不执行任何写/管理操作。
- **不存储 IP**:入口即删除 IP、Basic Auth 凭证、原始平台账号与原始内部 ID;玩家标识仅以 `HMAC-SHA256(salt, world_id + ":" + raw_user_id)` 落库。
- **不公开精确位置**:坐标默认量化为粗网格;`strict` 隐私模式下坐标完全不落库、据点模块停用。Ping 仅以「优秀/正常/偏高」分桶展示,不存原始数值。
- **需在服务器端启用 REST**:Palworld 服务器须开启 REST API(`RESTAPIEnabled=True` 并设置管理员密码)。
- **勿暴露公网**:REST API 请勿直接暴露到公网,走 localhost / 内网 / VPN / 反向代理;密码建议用环境变量(`password_env`)而非明文。

## 详细文档

- [配置项详解](docs/configuration.md) —— 轮询 / 世界与展示 / 据点推导 / 数据保留 / 自定义请求头 / 插件页面 / 功能开关
- [完整指令与功能开关](docs/commands.md) —— 18 条指令详表、功能开关矩阵、多服务器与群授权、降级行为

## 开源协议

GPL-3.0,见 [LICENSE](LICENSE)。
