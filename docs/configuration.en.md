<a id="configuration"></a>
# Configuration Reference

[简体中文](configuration.md) | [日本語](configuration.ja.md) | **English**

Every option can be edited visually on the plugin settings page. This page is the field-by-field reference; field
names are the keys used in configuration. See [Plugin page](#plugin-page) for access and save behavior.

<a id="servers"></a>
## servers (multiple servers)

You may add multiple Palworld servers. `name` must be unique and contain no spaces, colons, or `@`; `base_url` looks
like `http://127.0.0.1:8212`. `enabled` controls whether the entry is active, `username` is normally `admin`,
`timeout` is the request timeout in seconds, and `verify_tls` controls HTTPS certificate verification. Supply either
`password_env` (the recommended environment-variable name) or `password` (plain text stored on disk). Each server
may set `timezone` to override the global timezone.

<a id="routing"></a>
## routing (access control)

- **world_mode:** defaults to `single`. In single-server mode, every operation targets the first ready server; the
  `link` group is hidden and rejected at runtime, while `@server` overrides and group bindings are ignored. `multi`
  monitors several servers and authorizes or switches them per group. Initial setup is guided by the plugin page.
  Later, use the Connections section switcher, which previews the change, migrates grants, and cleans residual data.
  Directly editing the raw field in AstrBot's gear configuration is only an emergency path and skips migration and
  confirmation.
- **setup_confirmed:** bool, default `false`. This is the initial-setup gate. Until it is `true`, every `/pal` command
  except `/pal help`, `/pal whoami`, and `/pal whereami` returns setup guidance; see
  [Command reference · First use](commands.en.md#first-setup). You normally do not edit it manually. Confirming the
  selected mode on the initial setup screen writes `setup_confirmed=true` together with `world_mode`. AstrBot fills
  the schema default for a new installation, so every new installation must confirm the settings page once.
- **access_mode:** defaults to `restricted`; `open` allows queries from any session. Restricted authorization depends
  on the mode: single-server mode uses `single_allowed_groups`, while multi-server mode uses `/pal link` group grants
  stored in the database.
- **default_server:** the default server `name` used in multi-server mode when a group supplies neither an explicit
  target nor an active binding. Single-server mode always uses its only ready server and ignores this value.
- **single_allowed_groups:** described below. It applies only when `world_mode=single` and
  `access_mode=restricted`; multi-server mode ignores it.
- **group_bindings:** optional seed grants meaningful only in multi-server mode. They are equivalent to an
  administrator running `/pal link add`, seed initial state only, and never overwrite runtime changes. Single-server
  mode ignores them.
- **privacy.mode:** `strict`, `balanced` (default), or `advanced` (currently behaves as balanced).

<a id="single-allowed-groups"></a>
### single_allowed_groups (single-server allowlist)

This top-level list controls read access in restricted single-server mode and uses the same `template_list` pattern
as `group_bindings`. Only listed sessions, including groups and direct messages, may query the server. Open access
ignores the list.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `single_allowed_groups` | Per-entry list | Empty | Each row contains a session `umo` (unified_msg_origin, for example `aiocqhttp:GroupMessage:123456`) and optional `note`. Run `/pal whereami` in the group to obtain its UMO, then ask an administrator to add it under Connections |

- **Get a UMO:** run `/pal whereami` in the target group. Direct messages have their own UMO and are checked against
  the same list.
- **Empty list means no group can read:** `single` + `restricted` + an empty list is the fail-closed default. Nobody
  can query until an administrator follows the `/pal whereami` guidance and adds the group. Startup logs warn about
  this state.
- **Write commands do not use this list:** the seven `server` write commands are protected only by the hard
  administrator gate (`permission_admins`). An authorized administrator may manage the single server from any group
  or direct message.
- **Stored in plain text; do not enter PII:** `umo` and `note` are stored in plain text under `data/config/`. Do not
  put real names, contact details, or other personal information in `note`.

> **Multi-server mode does not read this list:** it uses `/pal link` group bindings. The settings-page mode switcher
> can migrate selected entries to multi-server bindings. Editing `world_mode` directly does not migrate anything.

<a id="mode-transfer"></a>
### Converting modes in the settings page

Apart from initial setup and emergency direct edits, change `world_mode` from the Connections section switcher. It
can migrate grants with move semantics, so switching back does not resurrect old grants:

- Single → multi: write selected `single_allowed_groups` entries to multi-server `group_bindings`, then clear the
  single-server list.
- Multi → single: merge selected group bindings into `single_allowed_groups`, then clear multi-server bindings. If
  several servers are ready, choose one to retain and optionally delete every historical record belonging to the
  others. Deletion cannot be undone.

After removing servers from configuration, or choosing deletion during a mode switch, remove their residual history
from Residual data cleanup in the final step of the switcher. The server recomputes the orphan set and deletes data
only for servers no longer present in configuration. The cleanup entry is not currently permanent on the settings
page; if you only removed a server, open the switcher later and use its final step.

<a id="permissions"></a>
## permissions (permission management)

Plugin administrator identity is independent of AstrBot's global `admins_id`. Only the list below is checked;
`admins_id` and `event.role` are ignored. A player can run `/pal whoami` to obtain their `platform:account`
identifier, then give it to the owner for allowlisting.

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `permission_admins` | Per-entry list | Empty | Plugin administrators. Each row has `id` (`platform:account`, for example `aiocqhttp:12345`) and optional `note`. Only listed accounts may run `link add`, `link remove`, `server` write commands, or commands configured as admin-only |
| `command_permissions` | Per-entry tri-state rows | Empty | Persistent source of truth for the command-tree control plane. A row targets a full command path such as `world status` or `player info`, or a group such as `guild` or `player`, and overrides `enabled` and `admin_only` with `inherit`, `on`, or `off`. Edit it visually in the Permissions section |

<a id="command-tree-permissions"></a>
### Command-tree permission model

Every command node has two independent controls:

- **`enabled`:** an `off` command returns "not enabled" and disappears from `/pal help`; its derived data collection
  is also disabled. Commands in `core` are always on.
- **`admin_only`:** when `on`, callers outside the plugin administrator list receive "This command requires
  administrator permission."

Each axis accepts `inherit`, `on`, or `off`. With sparse overrides and three-level inheritance, the effective value
comes first from the command row, then its group row, then the feature-group default under [features](#features).
Only add rows for commands or groups you need to change. Dangerous write commands (`server ban/shutdown/stop`) never
inherit `enabled` from a group key and must be enabled individually.

The **non-lockable set** is every `server` write command, every `link` command, plus `help`, `whoami`, `whereami`, and
`confirm`. An `admin_only` override has no effect on them because they are guarded by built-in feature and
administrator gates or intentionally open to everyone. `enabled` still controls `server` writes, all of which
default to off.

<a id="legacy-permission-migration"></a>
### Migrating from features / admin_only_commands

Version 0.9.5 and earlier used boolean `features` plus an `admin_only_commands` list. Since 0.9.6,
`command_permissions` is the single model. On first load, the plugin automatically converts legacy keys into
equivalent tri-state rows, persists the result, and clears the old keys.

| Legacy setting | Legacy value (migrated only when not default) | Resulting `command_permissions` row |
| --- | --- | --- |
| `features.report` | `off` | `world today` → `enabled=off` |
| `features.events` | `off` | `world events` → `enabled=off` |
| `features.guilds_bases` | `on` | `guild` (group) → `enabled=on` |
| `features.players` | `on` | `player` (group) + `rank` + `me` → `enabled=on` |
| `features.server_admin_basic` | `on` | `server announce/save/kick/unban` → `enabled=on` |
| `features.server_admin_danger` | `on` | `server ban/shutdown/stop` → `enabled=on` |
| Each `admin_only_commands` entry | Full path such as `player info` | That command → `admin_only=on` |

> Entries in `admin_only_commands` must be full command paths. Old flat values such as `player` cannot be recognized;
> migration reports them as invalid locks in startup logs instead of silently applying them. Commands in the
> non-lockable set are also reported as invalid. After upgrading, review the result in the Permissions section and
> stop maintaining the legacy keys.

**Important security notes:**

- **Global blast radius:** the administrator list is global. A listed account has administrator privileges in every
  group it participates in, including `link add`, `link remove`, and `server` write commands for any group. Trust an
  account for this full scope before adding it.
- **Shared namespace across adapters and groups:** adapter instances and groups using the same bot share one
  administrator list and account namespace. Grant access carefully when a bot serves multiple groups.
- **Stored in plain text; do not enter PII:** `id` and `note` are stored in plain text under `data/config/`. Do not
  put real names or contact details in `note`.

<a id="polling"></a>
## polling (global intervals applied per server)

| Option | Default | Meaning |
| --- | --- | --- |
| `metrics_seconds` | 30 | `/metrics` interval in seconds; drives FPS, online count, and other world metrics |
| `players_seconds` | 30 | `/players` interval in seconds; drives the online list and login sessions |
| `info_seconds` | 600 | `/info` interval in seconds for version, name, and other basic data; fetched immediately at startup |
| `settings_seconds` | 1800 | `/settings` interval in seconds; world rules change slowly and need no frequent polling |
| `game_data_seconds` | 120 | `/game-data` interval in seconds for guilds, bases, and other PalGameDataBridge world data; polled only while at least one `guilds_bases` command is effectively enabled |
| `jitter_ratio` | 0.10 | Random interval jitter to prevent every endpoint from being requested at once |
| `max_concurrency` | 6 | Global limit on in-flight HTTP requests, protecting the game server from excess concurrency |

Adaptive backpressure lengthens an endpoint's effective interval exponentially when its response takes longer than
the current interval, up to eight times the baseline. After several healthy responses, it gradually returns to the
configured value. No manual tuning is required.

<a id="world"></a>
## world (timezone and display)

| Option | Default | Meaning |
| --- | --- | --- |
| `timezone` | `Asia/Tokyo` | Global IANA timezone used by `/pal world today` and every time display; a server entry may override it with its own `timezone` |
| `locale` | `zh-CN` | Runtime message language: `zh-CN` (Simplified Chinese), `ja` (Japanese), or `en` (English) |
| `fps_smooth` | 50 | FPS at or above this value is shown as smooth |
| `fps_moderate` | 35 | FPS at or above this value but below `fps_smooth` is shown as moderate |
| `fps_laggy` | 20 | FPS at or above this value but below `fps_moderate` is shown as laggy; lower FPS is shown as severely laggy |

<a id="presentation"></a>
## presentation (display and card appearance)

| Option | Default | Meaning |
| --- | --- | --- |
| `me_card_theme` | `light` | Color theme for the image profile card (`/pal me 卡`): `light`, `dark`, or `auto`. Auto follows the **server's local clock**, using light from 06:00 to 18:00 and dark otherwise. It uses real time rather than the accelerated in-game day/night cycle. Text cards are unaffected |

<a id="bases"></a>
## bases (base inference, entirely disabled in strict privacy mode)

Bases are not returned directly by the API; they are inferred from sampled player positions. A grid location must be
observed consistently enough times before it is confirmed as a base.

| Option | Default | Meaning |
| --- | --- | --- |
| `enabled` | true | Enable base and PalBox inference; forced off in strict privacy mode |
| `assignment_radius` | 5000 | Maximum distance for assigning a sampled player position to a base, in world-coordinate units |
| `ambiguity_ratio` | 0.20 | Nearest/second-nearest distance-difference threshold; lower ratios are treated as ambiguous and ignored |
| `confirmation_samples` | 3 | Number of consistent observations required to confirm a base |
| `position_grid_size` | 2000 | Grid size used to quantize coordinates before persistence, implementing the no-precise-location boundary |
| `z_weight` | 0.5 | Weight of the Z axis in distance calculations, reducing false matches on vertical terrain |

<a id="history"></a>
## history (retention targets, not yet cleaned automatically)

| Option | Default | Meaning |
| --- | --- | --- |
| `raw_metrics_days` | 7 | Retention days for raw metrics from each poll |
| `aggregate_days` | 90 | Retention days for pre-aggregated statistics |
| `session_days` | 365 | Retention days for player login sessions |
| `observation_days` | 180 | Retention days for world observations |

> The current version reads and stores these targets, but the scheduler does not yet delete expired records. Manage
> the AstrBot data directory according to your operational and compliance needs; these settings are not an
> automatic-deletion guarantee.

<a id="custom-headers"></a>
## custom_headers (custom HTTP request headers)

These headers accompany every matching REST API poll. They are useful when the API is behind a reverse proxy or
gateway that requires additional authentication, such as Cloudflare Access
`CF-Access-Client-Id` / `CF-Access-Client-Secret`. Add or remove entries on the settings page.

| Field | Default | Meaning |
|------|------|------|
| `name` | Empty | Header name, for example `CF-Access-Client-Id` |
| `value` | Empty | Plain-text Header value, mutually exclusive with `value_env`; stored under `data/config/` |
| `value_env` | Empty | Environment-variable name containing the value; recommended for sensitive gateway tokens |
| `servers` | Empty | Comma-separated server names limiting the header. **Empty means every server**, including future additions, so credential headers should always have an explicit scope |

Notes:

- Reserved headers `Authorization`, `Host`, `Expect`, `Content-Length`, `Transfer-Encoding`, and `Connection` are
  ignored. Basic Auth comes from each server entry's username and password.
- Restart the entire AstrBot process after changing an environment variable referenced by `value_env` or
  `password_env`. Saving the page hot-reloads only the plugin, while environment variables belong to the process.
- Invalid skipped entries produce a startup warning containing only the name and reason, never the value.

<a id="plugin-page"></a>
## Plugin page (WebUI settings and status)

The plugin officially supports **AstrBot ≥ 4.24.1 and < 5**. Open PalWorldTerminal Settings from the plugin details
page on 4.24.1 and later, or from the Plugin pages group in the sidebar on 4.25.3 and later. It edits every server and
access-control option and shows read-only runtime status per server. Versions below 4.24.1 cannot provide the required
settings page or initial-setup flow and are unsupported.

- **Saving reloads immediately:** after validating and saving configuration, the plugin restarts its internal
  container. Polling pauses briefly, creating at most a tiny gap in online-time statistics, and chat commands
  temporarily report that a reload is in progress.
- **Sensitive fields:** passwords and custom Header values are never echoed. The page shows a configured marker and
  treats an empty submission as unchanged, represented internally by `__unchanged__`. For safety, changing a
  server's `base_url` requires re-entering its password so an old credential cannot be sent to a new address.
- **Authentication:** page requests are forwarded through the AstrBot Dashboard login session. Logged-out users
  cannot access it.

<a id="features"></a>
## features (feature groups)

> **Since v0.9.6, the command-tree permission model is authoritative:** the old boolean `features` settings were
> removed. Enablement is stored in tri-state `command_permissions` rows; see [Permission management](#permissions).
> Commands remain categorized by the feature groups below. A group supplies default enablement and drives derived
> collection. To change it, add an `enabled=on/off` row for a command or whole group in Permissions.

Feature groups provide defaults; effective values may be overridden by `command_permissions`.

| Feature group | Default | Commands | Meaning |
|------|------|------|------|
| `core` | Always on | `world status/rules` `online` `whoami` `whereami` `help` `confirm` bare `link` bare `server` | Fundamental commands that cannot be disabled |
| `report` | On | `/pal world today` | Daily report and online statistics |
| `events` | On | `/pal world events` | World event history; no events are generated while disabled |
| `players` | **Off** | `/pal player info` `/pal player bind` `/pal player unbind` `/pal rank` `/pal me` | Per-player queries, disabled by default for privacy |
| `guilds_bases` | **On** | `/pal world overview` `/pal guild list` `/pal guild info` `/pal guild bases` `/pal guild base` `/pal dex` | Guilds, bases, world overview, and Paldeck derived from `game-data` (PalGameDataBridge); enabled by default with stable game-data support |
| `server_admin_basic` | **Off** | `/pal server announce` `/pal server save` `/pal server kick` `/pal server unban` | Basic controlled writes, restricted to authorized administrators; see [server_admin](#server-admin) |
| `server_admin_danger` | **Off** | `/pal server ban` `/pal server shutdown` `/pal server stop` | Dangerous controlled writes such as bans and stops; confirmation is recommended; see [server_admin](#server-admin) |

A disabled command returns "not enabled" and disappears from `/pal help`. **Collection follows effective
enablement:** read-only observation endpoints (`/info`, `/metrics`, `/players`, and `/settings`) are always polled,
regardless of commands. `/game-data` is polled only while a `guilds_bases` command is effectively enabled; `bases.*`
and `game_data_seconds` follow the same condition.

**About `guilds_bases`, which defaults to on:** guild, base, and PalBox commands plus `world overview` use data derived
from `/v1/api/game-data` (PalGameDataBridge). Unlike the default-off `players` group, they became default-on with the
stable game-data API. While any command in the group is enabled, the plugin polls `/game-data` and applies `bases.*`
inference settings. Disable the relevant command-tree entries if you do not need them.

<a id="server-admin"></a>
## server_admin (server administration)

These options configure controlled writes. Every write command is disabled by default. Enable the corresponding
`server` command explicitly in `command_permissions`; their feature groups are `server_admin_basic` and
`server_admin_danger`, both default-off. Once enabled, only members of `permission_admins` may use them, and actions
that reach execution are recorded in the audit database. See
[Command reference · Server administration](commands.en.md#server-admin).

| Option | Type | Default | Meaning |
| --- | --- | --- | --- |
| `require_confirmation` | bool | `false` | When enabled, `server_admin_danger` commands (`ban`, `shutdown`, `stop`) first return a preview and execute only after `/pal confirm` within the timeout. Basic commands never require confirmation |
| `confirmation_timeout` | int (seconds) | `30` | Confirmation window; the pending action expires afterward. Range 5–600 |
| `audit_retention_days` | int (days) | `180` | Audit retention target, range 1–3650. The current version does not yet delete expired rows automatically |

**Important security notes:**

- **Open-access blast radius:** with `routing.access_mode=open`, write commands are no longer constrained by group
  authorization. Any authorized administrator can run `stop` or `ban` through the current route from any group or
  direct message. Avoid combining open access with `server_admin_danger`, especially on a bot shared by several
  groups. Under restricted access, single-server writes ignore the `single_allowed_groups` read list, while
  multi-server writes use the group's current active binding. Administration commands do not accept a temporary
  `@server` override.
- **`server stop` can lose progress:** `/pal server stop` forces a stop without saving. Run `/pal server save` first
  or use `/pal server shutdown`, which saves during its countdown. The danger group is therefore off by default and
  `require_confirmation` is recommended.
- **Audit retention and PII:** `admin_audit` stores plaintext `admin_id`, `target_name`, and timestamps as controlled
  personal information. Target user IDs are stored only as hashes in the same world-scoped namespace used by
  observations. The 180-day default target is not enforced automatically, so manage the data directory yourself.
- **Name lookup bypasses privacy filters for administrators:** resolving a character name for `kick` or `ban` reads
  the raw user ID from `/players`, bypassing `/pal me hide` and `exclude_names`. A real ID is required for the write
  and operators can already see all online players in-game; this does not reveal a hidden player's existence to
  peers.
