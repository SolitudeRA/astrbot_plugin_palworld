# 自定义 HTTP 请求头 — 设计规格

日期：2026-07-11
状态：已对抗式复核（3 视角：正确性/一致性、安全/隐私、AstrBot 兼容性），本版为修订版
关联：`docs/superpowers/specs/2026-07-10-palchronicle-v0.1-design.md`（主规格）

## 1. 目标

允许用户在 AstrBot WebUI 中以按钮添加/删除的方式配置自定义 HTTP 请求头，
随插件向 Palworld REST API 发出的所有轮询请求一并发送。典型场景：REST API
经反向代理/网关暴露，需要额外鉴权头（如 Cloudflare Access 的
`CF-Access-Client-Id` / `CF-Access-Client-Secret`）。

**非目标：**

- 不支持在单个服务器条目内嵌套请求头列表（AstrBot WebUI 的
  `template_list` 对 items 无嵌套列表支持，已核实
  `TemplateListEditor.vue`）；作用域限定通过条目上的 `servers` 字段实现
- 不提供删除 aiohttp 默认头（`skip_auto_headers`）的入口；同名自定义头
  覆盖 `Accept` / `User-Agent` 等默认头是 aiohttp 固有行为（默认头仅在
  缺席时补充），允许但不做额外承诺
- 不改变现有 Basic Auth 机制

## 2. 配置界面（`_conf_schema.json`）

新增插件级键 `custom_headers`，类型 `template_list`（AstrBot ≥ 4.10.4，
与 README 现有版本门槛一致；与现有 `servers`、`group_bindings` 同款控件，
WebUI 渲染为「添加条目」按钮 + 每条右侧删除按钮）：

```json
"custom_headers": {
  "type": "template_list",
  "description": "自定义 HTTP 请求头（随 REST 轮询请求发送）",
  "hint": "敏感值（如网关 Token）建议填环境变量名(value_env)而非明文；明文会落盘到 data/config/。含凭证的头务必用 servers 限定作用域：留空会发给所有已配置服务器（包括之后新增的）",
  "default": [],
  "templates": {
    "header": {
      "name": "请求头",
      "display_item": "name",
      "items": {
        "name":      { "type": "string", "description": "Header 名（如 CF-Access-Client-Id）", "default": "" },
        "value":     { "type": "string", "description": "Header 值（明文，与 value_env 二选一）", "default": "" },
        "value_env": { "type": "string", "description": "值的环境变量名（推荐，与 value 二选一）", "default": "" },
        "servers":   { "type": "string", "description": "限定服务器 name，逗号分隔多个；留空=所有服务器", "default": "" }
      }
    }
  }
}
```

WebUI 保存的条目会携带附加键 `__template_key`（AstrBot 平台行为），
解析时按字段读取、自然忽略；测试 fixture 必须包含该键以贴近生产数据形状。

## 3. 解析层（`palchronicle/config.py`）

### 3.1 数据结构

```python
@dataclass(slots=True)
class SkippedHeader:
    raw_name: str          # 原始 name（绝不含 value）
    reason: str            # "empty_name" / "illegal_name" / "reserved" /
                           # "empty_value" / "illegal_value"

@dataclass(slots=True)
class ServerConfig:
    ...                    # 既有字段不变
    headers: dict[str, str] = field(default_factory=dict)  # 置于末位；
    # slots=True 无默认值 dataclass，新字段必须带 default_factory 且排最后，
    # 否则既有构造点（散布于单测）全部炸掉

AppConfig 新增：skipped_headers: list[SkippedHeader]
```

请求头在 `parse_config` 期间即按作用域解析并落到每个
`ServerConfig.headers`，下游（调度器、REST 客户端）对作用域逻辑零感知。

### 3.2 单条解析规则

**规范化先行**：`name`、`value`（解析后）、`servers` 的每个分段都先
`strip()` **一次**，此后所有步骤（正则、保留头比对、去重、落盘、发送）
一律使用同一 stripped 值——严禁某步用 raw、某步用 stripped
（否则 `" authorization"` 这类条目可绕过保留头检查，与 BasicAuth 共存时
aiohttp 每次请求抛 `ValueError`）。

按此顺序判定，任一不满足即跳过该条并记录 `SkippedHeader`：

1. **name 校验**（reason=`empty_name`/`illegal_name`）：stripped name
   非空，且 `re.fullmatch` 命中 RFC 9110 token 字符集
   （用 `fullmatch` 而非 `$` 锚点，避免 `$` 在末尾换行前匹配的暗坑）：

   ```
   [!#$%&'*+\-.^_`|~0-9A-Za-z]+
   ```

2. **保留头跳过**（reason=`reserved`，对 stripped name 大小写不敏感比对）：
   - `authorization`：与 BasicAuth `auth=` 共存时 aiohttp 抛
     `ValueError`（已核实 aiohttp 3.14 `client.py`，比对发生在
     `CIMultiDict` 上，大小写不敏感）
   - `host`：避免与 `base_url` 解析出的 SNI/TLS 证书校验、连接复用键
     产生不一致；vhost 路由需求未来有真实场景再放开
   - `content-length`、`transfer-encoding`、`connection`：报文框架头，
     GET 客户端上只会破坏请求
   - `expect`：`Expect: 100-continue` 会让 aiohttp 发头后阻塞等待 100
     响应，网关不回则每次轮询空转到超时（自伤型 DoS）
3. **值解析**：`value_env` 非空 → 查环境变量，存在且非空则用之；
   否则回退 `value`。与现有 `_resolve_password` 逻辑一致
4. **值校验**（reason=`empty_value`/`illegal_value`）：stripped 值非空，
   且不含 `[\x00-\x08\x0a-\x1f\x7f]` 中任何字符（与 aiohttp 3.14 序列化
   期禁止集对齐——只挡 `\r\n` 不够：其余控制字符会在解析期放行、
   运行期每次请求序列化失败；TAB `\x09` 合法予以保留）。
   header 注入（CRLF）由本步在解析期无条件封死，不依赖 aiohttp 版本
5. **作用域解析**：`servers` 字段整体 `strip()` 后为**空字符串** →
   应用到所有服务器（含未来新增，见 hint 警示）；否则按逗号切分、
   逐段 `strip()`、去掉空段：
   - 切分后为空列表（如 `",,"`、`" , "`）→ 视同**零匹配**，应用到
     零个服务器——**绝不回退到全部**（fail-closed；该字段非空说明
     用户意图是限定）
   - 列出的名字与已解析服务器 name **精确匹配**（大小写敏感，与现有
     server name 语义一致），未匹配的名字忽略；全部未匹配 → 应用到
     零个服务器

### 3.3 合并与诊断

- 对每个服务器：按 `custom_headers` 列表顺序合并作用于它的条目；
  Header 名**大小写不敏感**去重，**后者覆盖前者**，落盘 dict 保留
  最后一条的原始（stripped）大小写
- **诊断（有意偏离 `group_bindings` 的纯静默模式，向 `SkippedServer`
  模式看齐）**：跳过条目记入 `AppConfig.skipped_headers`；
  `Container.start()` 启动时若非空，记一条 warning 日志，内容仅含
  name 与 reason 列表。理由：头条目承载网关凭证，解析被跳过的下游
  表现是持续 `http_status_401` 且错误已脱敏，纯静默几乎无法定位
- **脱敏红线**：value（含 env 解析后明文）只存在于内存
  `ServerConfig.headers`，绝不进入日志、错误信息、status 展示、
  `SkippedHeader`。任何 except 分支**禁止记录异常对象文本**
  （aiohttp 个别异常文本可能含头相关内容）

## 4. 请求层（`palchronicle/adapters/palworld_rest.py`）

`PalworldRestClient.fetch` 的 `session.get(...)` 增加一个参数：

```python
headers=self._server.headers or None,
```

- 空 dict 与 `None` 在 aiohttp `_prepare_headers` 中行为完全相同
  （`or None` 属显式表意，冗余无害），现有请求完全不变（零回归面）
- 应用到全部 5 个端点（info/metrics/players/settings/game-data），
  它们共用同一个 `fetch`
- 错误脱敏逻辑不变：任何异常路径仍只报类别字符串，不含头名/头值，
  不引入 `except ... as exc` 记录异常文本的写法

## 5. 文档同步

- `README.md` 配置说明段新增 `custom_headers` 小节：键名、四字段、
  value_env 推荐、**servers 留空=发给所有服务器（含未来新增）的
  安全警示**、`value_env` 指向的环境变量变更需**重启 AstrBot 进程**
  （热重载只重跑 `parse_config`，`os.environ` 是进程级的——现有
  `password_env` 同理，一并补写）
- `tests/unit/readme_test.py` 补充针对新小节的关键词断言（该测试为
  全文子串匹配，只能锁定关键词存在）
- `tests/unit/conf_schema_test.py` 补充针对 `custom_headers` 键的
  结构断言（该测试为逐键点名式，新键必须显式加断言才受锁定）

## 6. 测试计划

每条判定规则至少一条正/反用例：

| 层 | 用例 |
|---|---|
| config 值解析 | value_env 命中环境变量优先；env 缺失回退 value；两者皆空 → skip(`empty_value`)；值带前后空白 → 发送 stripped 值 |
| config name | 合法 token 通过；空名/含空格/含冒号/非 token 字符 → skip；`" authorization"`（带前导空白）与 `"AUTHORIZATION"`（大小写变体）均 → skip(`reserved`)；六个保留头逐一覆盖 |
| config 值校验 | 值含 `\r`、`\n`、`\x00`、`\x7f` → skip(`illegal_value`)；含 TAB 通过 |
| config 作用域 | 留空 → 所有服务器；限定单个/多个（逗号）只落到对应服务器；`",,"` 全空段 → 零服务器；全部未知名字 → 零服务器（不回退全部）；大小写不匹配（`Server` vs `server`）→ 不匹配 |
| config 合并 | 同名不同大小写后者覆盖且保留后者大小写；列表顺序决定覆盖方向 |
| config 兼容 | 未配置 `custom_headers` / 值为 None → 所有 `ServerConfig.headers == {}` 且 `skipped_headers == []`；fixture 条目含 `__template_key` 键被忽略 |
| config 诊断 | 跳过条目产生正确 `SkippedHeader(raw_name, reason)`；raw_name 存在而 value 绝不出现在 SkippedHeader |
| container | `skipped_headers` 非空时 start() 记 warning（仅 name+reason）；为空时不记 |
| REST 客户端 | `headers` 非空时请求实际携带（fake session 断言）；为空 dict 时传 `None` |
| schema/README | `conf_schema_test.py` 新键结构断言；`readme_test.py` 新小节关键词断言 |

## 7. 兼容性与运维

- 向后兼容：旧配置无 `custom_headers` 键，解析回退空列表，行为与
  现状完全一致
- 生效路径（已核实 AstrBot `config_service.py`）：WebUI 保存插件配置
  即**自动热重载**（terminate → 重新实例化 → initialize →
  `parse_config` 重跑），新头立即生效，无需手动操作；仅手工编辑
  `data/config/*_config.json` 时才需手动重载插件
- `value_env` / `password_env` 指向的**环境变量**变更需重启 AstrBot
  进程（`os.environ` 进程级）
- `requirements.txt`：aiohttp 下界从 `>=3.9` 提升到 `>=3.9.2`
  （3.9.2 含头部控制字符注入修复，作为解析层校验之外的纵深防御）
- 版本号：随下一次发布 bump，本规格不单独改版本

## 8. 复核记录

2026-07-11 三个独立视角对抗式复核，主要修订：

- 安全：`servers` 留空广播凭证的警示写入 hint/README（H1）；值校验
  扩展到 aiohttp 全禁止集（M1）；保留头补 `expect`（M2）；aiohttp
  下界 3.9.2、`re.fullmatch`、异常文本禁记 写入规格（L1/L2）
- 正确性：name/value 规范化一次并贯穿全部步骤（防保留头绕过）；
  `servers` 空字符串≠切分后空列表，后者 fail-closed 到零服务器；
  静默跳过改为 `SkippedHeader` + 启动 warning（向 SkippedServer 模式
  看齐并说明理由）；非目标措辞修正（skip_auto_headers）；测试计划
  按规则逐条补正/反用例
- 兼容性：确认 `template_list`/按钮增删/`display_item`/`default: []`
  可行（AstrBot ≥ 4.10.4）；补 `__template_key` 数据形状；
  `ServerConfig` slots 约束写死 `field(default_factory=dict)` 置末位；
  §7 改为保存即热重载 + env 变更需重启进程；§5 措辞降级为
  逐键补断言
