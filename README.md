<div align="center">

<img src="https://raw.githubusercontent.com/SolitudeRA/astrbot_plugin_palworld/main/docs/images/banner.png" alt="PalWorldTerminal · 帕鲁世界终端" width="640">

# PalWorldTerminal · 帕鲁世界终端

[![version](https://img.shields.io/badge/version-v0.9.7-007ec6)](https://github.com/SolitudeRA/astrbot_plugin_palworld/releases)
[![python](https://img.shields.io/badge/python-3.11%2B-007ec6)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A5%204.24.1-fe7d37)](https://github.com/AstrBotDevs/AstrBot)
[![license](https://img.shields.io/badge/license-GPL--3.0-97ca00)](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/LICENSE)
[![Palworld](https://img.shields.io/badge/Palworld-1.0%2B-3f6ec6)](https://www.pocketpair.jp/palworld)

监测 Palworld 专用服务器,在群里提供状态查询、日报与玩家档案,并支持受控的服务器管控。<br>基于官方 REST API。

受控写(默认全关 · 仅授权管理员 · 全程审计) · 不存储 IP · 不公开精确位置 —— 详见[安全与隐私](#安全与隐私)

[功能特性](#功能特性) · [快速开始](#快速开始) · [指令](#指令) · [配置](#配置) · [安全与隐私](#安全与隐私) · [详细文档](#详细文档)

</div>

---

## 功能特性

- **分级指令** —— `/pal <组> <动作>`:5 组(`world`/`guild`/`player`/`server`/`link`)+ 7 扁平命令(`rank`/`online`/`me`/`help`/`whoami`/`whereami`/`confirm`);裸组即迷你帮助
- **世界状态** —— 在线人数、FPS 流畅度、世界天数(`/pal world status`)
- **玩家档案与排行** —— 在线名单、时长/等级榜、逐人查询、自助绑定与隐藏(`/pal online`、`/pal rank`、`/pal me`)
- **日报与事件** —— 今日在线统计、上下线与服务器重启大事记(`/pal world today`、`/pal world events`)
- **服务器管控(受控写)** —— 广播、存档、踢人、封禁、倒计时关服共 7 条写命令:**默认全关、仅授权管理员、可二次确认、全程审计**(`/pal server announce`、`/pal server shutdown` 等)
- **单 / 多世界两模式** —— **默认单世界**(一台服务器、免 `link` 授权,restricted 下按授权群名单放行);多世界一个插件监测多台、按群授权、`/pal link` 按群切换
- **细粒度授权** —— 独立管理员名单,敏感命令可锁为仅管理员(`/pal whoami` 自查标识)
- **零信任接入** —— 自定义请求头携带网关凭证(如 Cloudflare Access),REST API 无需暴露公网
- **隐私优先** —— 观测只读、不存 IP、标识 HMAC 哈希落库、坐标量化为粗网格;写操作目标 userid 仅存哈希
- **WebUI 设置页** —— 可视化配置全部选项,亮暗双主题
- **公会与据点** —— 依赖上游 `game-data`,默认关闭,开放后一键启用

## 效果预览

`/pal world status` 的回复长这样:

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
4. **授权本群** —— **单世界模式(默认)**:`restricted` 访问下,群里发 `/pal whereami` 取本群标识,交管理员在设置页「连接」章的**授权群名单**里添加(`open` 则免授权);**多世界模式**:管理员执行 `/pal link add <服务器名>` 授权本群。
5. **开始查询** —— `/pal world status`,看到世界状态就通了。

环境要求:AstrBot ≥ 4.24.1(插件设置页需此版本,建议最新 4.26.x)· Python ≥ 3.11 · SQLite 3。

## 指令

v0.9.5 起指令为**分级结构**:`/pal <组> <动作>`(裸组即迷你帮助)。查询指令只读;服务器管控为受控写(默认关、仅授权管理员)。常用:

| 指令 | 说明 |
|------|------|
| `/pal world status` | 世界状态(在线数、FPS 流畅度等) |
| `/pal online` | 当前在线玩家名单 |
| `/pal world today` | 今日日报 / 在线统计 |
| `/pal rank [today\|total\|level]` | 排行榜(今日/累计时长榜 + 等级榜) |
| `/pal me` | 我的档案;`hide`/`show` 自助隐藏 |
| `/pal player info <玩家名>` | 逐人查询 |
| `/pal link list` | 服务器列表与本群授权状态(多世界) |
| `/pal link add <名称>` | **管理员** · 授权本群使用某服务器(多世界) |
| `/pal help` | 分级帮助(按启用的功能 + 角色过滤) |

**服务器管控(受控写 · 默认全关 · 仅授权管理员)** —— `server` 组:

| 指令 | 组 | 说明 |
|------|------|------|
| `/pal server announce <消息>` | `server_admin_basic` | 全服广播 |
| `/pal server save` | `server_admin_basic` | 保存世界存档 |
| `/pal server kick <玩家名\|userid> [理由]` | `server_admin_basic` | 踢出玩家 |
| `/pal server unban <userid>` | `server_admin_basic` | 解封玩家 |
| `/pal server ban <玩家名\|userid> [理由]` | `server_admin_danger` | 封禁玩家(高危,可选二次确认) |
| `/pal server shutdown <秒> [公告]` | `server_admin_danger` | 倒计时关服(高危,可选二次确认) |
| `/pal server stop` | `server_admin_danger` | 立即停服(**不存档、丢档**,高危,可选二次确认) |
| `/pal confirm` | `core` | 确认执行上一条待确认的高危操作 |

任意查询指令末尾加 `@<服务器名>` 可单次指定目标服务器,如 `/pal world status @alpha`(多世界场景)。**单世界模式**(`world_mode=single`,默认)下所有操作对应唯一服务器、`link` 组隐藏;`restricted` 访问按**授权群名单**(`single_allowed_groups`)放行(群里发 `/pal whereami` 取本群标识后在设置页添加),`open` 则全放;写命令仅受管理员硬门约束、**不受读名单限制**。
完整分级指令表、功能开关矩阵、锁迁移映射表、服务器管控与群授权用法 → [docs/commands.md](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/commands.md)

## 配置

全部配置可在 WebUI 设置页可视化完成,要点:

- **运行模式**:`world_mode` **默认 `single` 单世界**(一台服务器);多台服务器请改 `multi`。切换入口是插件齿轮配置里的模式主开关(无存量用户,改默认直接生效、无迁移)。
- **多服务器**:`multi` 模式下可添加多台;名称唯一,密码推荐 `password_env` 环境变量。
- **访问控制**:默认 `restricted`(单世界按**授权群名单** `single_allowed_groups` 放行,多世界需管理员 `/pal link` 授权);`open` 为全开放。
- **命令树控制面**:每条命令(或整组)有两个开关——**是否启用**(`enabled`)与**是否仅管理员**(`admin_only`),各取 `inherit`(继承默认)/ `on` / `off` 三态。未覆盖的命令按其**功能组默认**(下表);稀疏覆盖沿「命令 → 组 → 默认」三级继承。数据采集派生自启用状态:观测只读端点恒采集,`game-data` 仅当 `guild` 组有命令生效才采集。在设置页「权限」章可视化编辑,落盘为 `command_permissions` 三态行。

| 功能组(决定命令默认) | 默认 | 命令 |
|--------|------|------|
| `report` 日报 | 开 | `world today` |
| `events` 世界事件 | 开 | `world events` |
| `players` 玩家查询 | **默认关** | `player info` `player bind` `rank` `me` |
| `guilds_bases` 公会与据点 | **默认关** | `guild list` `guild bases` 等 |

> **从旧版升级**:旧的 `features` 功能开关与 `admin_only_commands` 名单已并入命令树,插件**首次装载时自动迁移**为等价的 `command_permissions` 三态行,无需手动改配置。对照表见 [docs/configuration.md · 命令树权限模型](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/configuration.md#permissions权限管理)。

轮询间隔、FPS 阈值、隐私脱敏、数据保留、自定义请求头、命令树权限等全部配置项详解 → [docs/configuration.md](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/configuration.md)

## 安全与隐私

- **观测只读**:周期采集仅调用官方只读端点 `/info`、`/metrics`、`/players`、`/settings`、`/game-data`,不参与任何写操作。
- **受控写(服务器管控)**:广播/存档/踢人/封禁/关服等写命令**默认全部关闭**,须在设置页显式开启功能组;开启后**仅授权管理员**(管理员名单成员)可用,每次操作**无论成败全程落库审计**(仅哈希目标 userid,不存明文)。承诺从「绝不写」转为「受控写」。
- **⚠️ OPEN 访问模式爆炸半径**:`access_mode=open` 下写命令**不再受群授权名单约束**,任一授权管理员可从任意群/私聊对任意就绪服务器执行 `server stop`/`server ban`。强烈劝阻「OPEN + danger 组同开」;多群共享同一 bot 时尤须谨慎。
- **⚠️ `server stop` 不存档**:`/pal server stop` 强制停服**不保存存档**,可能丢失未存进度;需要保存请先 `/pal server save` 或改用 `/pal server shutdown`(倒计时期间游戏会正常保存)。
- **单世界 × restricted 授权**:`world_mode=single`(默认)下 `access_mode=restricted` 时,读命令按**授权群名单**(`single_allowed_groups`)放行——仅名单内会话(群/私聊)可查询唯一服务器;**空名单 = 当前全群不可读**(fail-closed,启动日志会告警,提示用 `/pal whereami` 取标识后在设置页「连接」章添加)。写命令仍受管理员硬门约束、**不受读名单限制**。`open` 则对所有会话开放。
- **不存储 IP**:入口即删除 IP、Basic Auth 凭证、原始平台账号与原始内部 ID;玩家标识仅以 `HMAC-SHA256(salt, world_id + ":" + raw_user_id)` 落库。
- **不公开精确位置**:坐标默认量化为粗网格;`strict` 隐私模式下坐标完全不落库、据点模块停用。Ping 仅以「优秀/正常/偏高」分桶展示,不存原始数值。
- **需在服务器端启用 REST**:Palworld 服务器须开启 REST API(`RESTAPIEnabled=True` 并设置管理员密码)。
- **勿暴露公网**:REST API 请勿直接暴露到公网,走 localhost / 内网 / VPN / 反向代理;密码建议用环境变量(`password_env`)而非明文。
- **支持网关鉴权接入**:自定义请求头可为所有轮询请求携带零信任网关凭证(如 Cloudflare Access 的 `CF-Access-Client-Id` / `CF-Access-Client-Secret`),让 REST API 藏在反向代理 / 网关之后而非直连;凭证推荐存环境变量(`value_env`),设置页不回显明文,并可用「限定服务器」把凭证头只发给指定服务器。
- **管理员名单全局生效**:插件管理员由独立的管理员名单判定(不复用 AstrBot `admins_id`)。名单**全局**——加入者在其所在的每个群都有管理员权,多群共用一个 bot 时请谨慎授权;`note` 明文落盘,勿填 PII。详见 [docs/configuration.md](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/configuration.md#permissions权限管理)。

## 详细文档

- [配置项详解](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/configuration.md) —— 轮询 / 世界与展示 / 据点推导 / 数据保留 / 自定义请求头 / 插件页面 / 命令树权限模型(含旧版迁移对照)
- [完整指令与功能开关](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/docs/commands.md) —— 分级指令详表(5 组 + 6 扁平)、功能开关矩阵、锁迁移映射表、服务器管控、多世界与群授权、权限管理、降级行为

## 开源协议

GPL-3.0,见 [LICENSE](https://github.com/SolitudeRA/astrbot_plugin_palworld/blob/main/LICENSE)。
