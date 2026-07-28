<a id="commands"></a>
# Complete Command and Feature Reference

[简体中文](commands.md) | [日本語](commands.ja.md) | **English**

Since v0.9.5, commands use the hierarchical form `/pal <group> <action> [arguments]`. There are five command groups
(`world`, `guild`, `player`, `server`, and `link`) plus eight flat commands (`rank`, `online`, `me`, `dex`, `help`,
`whoami`, `whereami`, and `confirm`). Every command begins with `/pal` and returns plain text. Query commands are
read-only. **Server administration uses controlled writes:** everything defaults to off, only authorized
administrators may use it, and requests that reach execution leave an audit record. See
[Server administration](#server-admin). Commands assigned to a feature group are available only when effectively
enabled in the matrix below; `core` commands are always available.

> **A bare group is mini-help:** sending only a group name, such as `/pal world` or `/pal server`, returns available
> subcommands filtered by current feature settings and your role. Visitors never see write subcommands.

<a id="first-setup"></a>
## First use and the initial-setup gate

**After a new installation, choose and confirm single-server or multi-server mode once on the plugin settings page**
before commands become fully available. Until `routing.setup_confirmed` is `true`, every `/pal` command except the
following returns initial-setup guidance:

- `/pal help` — role-aware help
- `/pal whoami` — show my account identifier
- `/pal whereami` — show the current session identifier

> Before confirmation, the settings page shows the initial wizard instead of normal sections. Choosing a mode and
> confirming writes `world_mode` plus `routing.setup_confirmed=true`, saves, unlocks the commands, and opens the normal
> settings page. Later, switch safely from Connections. Directly editing the raw AstrBot gear field remains an
> emergency path and performs neither grant migration nor confirmation. See [Operating modes](#world-modes) and
> [Configuration reference · routing](configuration.en.md#routing).

<a id="command-reference"></a>
## Command reference

<a id="world-commands"></a>
### `world` group — world observation (query)

| Command | Arguments | Feature group | Description |
|------|------|--------|------|
| `/pal world status` | — | `core` | World status including online count, FPS health, and world day |
| `/pal world overview` | — | `guilds_bases` | World snapshot of guilds and bases; belongs to the default-on `guilds_bases` group |
| `/pal world rules` | — | `core` | World rules such as multipliers |
| `/pal world today` | — | `report` | Today's report and online statistics |
| `/pal world events` | — | `events` | World event history |

<a id="guild-commands"></a>
### `guild` group — guilds and bases (query)

> This group depends on guild and base data derived from `game-data` (PalGameDataBridge). It is **on by default** now
> that game-data is stable. Enabling it polls `/game-data`; `world overview` also belongs here. Disable the
> corresponding commands in Features if you do not need them.

| Command | Arguments | Feature group | Description |
|------|------|--------|------|
| `/pal guild list` | — | `guilds_bases` | Guild list |
| `/pal guild info` | `<name>` | `guilds_bases` | Guild details |
| `/pal guild bases` | — | `guilds_bases` | Base list |
| `/pal guild base` | `<name\|#number>` | `guilds_bases` | Live base details: activity mix, idle rate, and atmosphere badge |

<a id="player-commands"></a>
### `player` group — player profiles (query)

| Command | Arguments | Feature group | Description |
|------|------|--------|------|
| `/pal player info` | `<player>` | `players` | Look up one player's level, time, base, and other details |
| `/pal player bind` | `<player>` | `players` | Link a platform account to a player so `/pal me` can identify the caller |
| `/pal player unbind` | — | `players` | Remove my player link, the inverse of `bind` |

<a id="flat-commands"></a>
### Flat commands — common queries and meta commands

| Command | Arguments | Feature group | Permission / context | Description |
|------|------|--------|-------------|------|
| `/pal rank` | `[today\|total\|level\|climb]` | `players` | Everyone | Ranking variants: `today` online time today (default), `total` online time with a data-retention-scope note, `level` level ranking, and `climb` level gains over the last seven days |
| `/pal online` | — | `core` | Everyone | Current online players |
| `/pal me` | `[hide\|show\|card\|卡\|图]` | `players` | Everyone | Personal profile with level, guild, recorded-player percentile, and companion highlight; `card`/`卡`/`图` renders an image (**the companion highlight requires `guilds_bases`**); `hide`/`show` removes or restores yourself in rankings and queries |
| `/pal dex` | — | `guilds_bases` | Everyone | Server Paldeck progress for observed species, grouped by element and accumulated globally by the plugin |
| `/pal whoami` | — | `core` | Everyone (**prefer direct message**) | Show my `platform:account` identifier, such as `aiocqhttp:12345`, for an owner to add to plugin administrators |
| `/pal whereami` | — | `core` | Everyone | Show only the current session UMO, such as `aiocqhttp:GroupMessage:123456`, for a single-server restricted allowlist. It is always available in both modes and accepts no target arguments |
| `/pal help` | — | `core` | Everyone | Role-aware help filtered by effective groups and the caller |
| `/pal confirm` | — | `core` | **Authorized administrators only** | Confirm the previous pending dangerous operation; reports that there is no pending operation when absent or expired |

> **`rank` variants and privacy:** `today` and `total` are online-time rankings, and strict privacy disables both.
> `total` covers only the retention period rather than all time, and respects both the administrator exclusion list
> and `/pal me hide`. A hidden player's entire name group disappears without revealing their presence. `level` ranks
> levels. `climb` ranks level gains over the last seven days, or labels the range honestly as "since the bot began
> recording" when less history exists.

<a id="server-commands"></a>
### `server` group — server administration (controlled writes)

See [Server administration](#server-admin). Commands are `/pal server announce`, `/pal server save`,
`/pal server kick`, `/pal server unban`, `/pal server ban`, `/pal server shutdown`, and `/pal server stop`. Every one
requires an authorized administrator.

<a id="link-commands"></a>
### `link` group — server selection and group grants (multi-server mode only)

See [Multi-server routing and group authorization](#multi-world-routing). Commands are `/pal link list`,
`/pal link add <name>`, and `/pal link remove <name>`. In single-server mode, the `link` group is hidden and rejected
at runtime because no server selection is needed.

Any query command can append **`@<server-name>`** to select one server for that request. Details are below.

> **Administration commands do not support temporary `@server` overrides:** single-server mode always uses its only
> ready server; multi-server mode uses the group's current active server. Run `/pal link add <server-name>` first to
> switch the target. Appending an `@word` to an administration command does not change its target. Consecutive spaces
> and line breaks in broadcasts and reasons are collapsed to one space, so exact text preservation is not guaranteed.

<a id="feature-matrix"></a>
## Feature switches → available commands

Feature groups are modular. Since v0.9.6, the command tree under Permissions controls them and persists
`command_permissions`; see
[Configuration reference · Command-tree permission model](configuration.en.md#command-tree-permissions).
**Disabling a command or group makes it return "not enabled" and removes it from `/pal help`.** The code remains and
works again when enabled. The `guild` group and `world overview` belong to default-on `guilds_bases`. Enabling any
command in that group starts `/game-data` polling; read-only observation endpoints are always polled.

| Feature group | Default | Commands (full paths) | When enabled | When disabled |
|--------|------|----------|--------|----------------|
| `core` (cannot be disabled) | Always on | `world status` `world rules` `online` bare `server` bare `link` `whoami` `whereami` `help` `confirm` | ✅ Available | — Cannot be disabled |
| `report` | On | `world today` | ✅ Available | ❌ Returns "not enabled"; hidden from help |
| `events` | On | `world events` | ✅ Available and records events | ❌ Returns "not enabled"; no events generated |
| `guilds_bases` | **On** | `world overview` `guild list` `guild info` `guild bases` `guild base` `dex` | ✅ Available and polls `/game-data` | ❌ Returns "not enabled"; hidden from help |
| `players` | **Off** | `player info` `player bind` `player unbind` `rank` `me` | ✅ Available | ❌ Returns "not enabled"; hidden from help |
| `server_admin_basic` | **Off** | `server announce` `server save` `server kick` `server unban` | ✅ Authorized administrators only | ❌ Admins get "not enabled" and help hides it; non-admins always get "administrator permission required" |
| `server_admin_danger` | **Off** | `server ban` `server shutdown` `server stop` | ✅ Authorized administrators only; optional confirmation | ❌ Admins get "not enabled" and help hides it; non-admins always get "administrator permission required" |

> `server_admin_basic` and `server_admin_danger` are controlled writes and default to off. See
> [Server administration](#server-admin). Non-administrators always receive the permission error regardless of group
> enablement, preventing the response from revealing whether dangerous operations are enabled.

> `players` defaults to off for privacy. Online-time rankings cover today or the retention period, while the level
> ranking includes offline players. Strict privacy is more conservative and disables time rankings and hides profile
> coordinates. Administrators can exclude names, and players can use `/pal me hide`; excluded or hidden players never
> appear in rankings or queries, and their presence is not disclosed.

> `guilds_bases` defaults to on. Guilds, bases, PalBox data, and `world overview` use data derived from `game-data`
> (PalGameDataBridge). `/game-data` is polled while any command in this group is effectively enabled. Disable the
> relevant commands under Features if you do not need them; see the
> [configuration reference](configuration.en.md#features).

<a id="world-modes"></a>
## Operating modes: single-server / multi-server

`routing.world_mode` selects routing and defaults to `single`. Initial setup guides the choice. Later, use the
Connections switcher to preview the impact, migrate grants, and clean residual data. Directly editing the AstrBot
gear field is an emergency option that skips migration and confirmation.

- **`single` (default):** every operation targets one server, the first ready entry. The `link` group is hidden and
  rejected; `@server` overrides and group bindings are ignored. Read authorization is described below.
- **`multi`:** one plugin monitors several servers, grants them per group, and switches each group's active server.
  The `link` group selects and authorizes servers, and query commands accept a one-shot `@<server-name>` override.
  Read authorization uses `/pal link` group bindings stored in the database.

<a id="single-world-access"></a>
### Read authorization and writes in single-server mode

- **Read commands:** with `access_mode=restricted`, only sessions listed in the top-level
  `single_allowed_groups` may query the server. Every other group or direct message is rejected with guidance to use
  `/pal whereami` and the settings-page list. `access_mode=open` allows every session and ignores the list.
- **Configure the list:** run `/pal whereami` in a group to obtain its UMO, then ask an administrator to add a row
  containing `umo` and optional `note` under Connections. Direct messages are checked against the same list.
- **Empty list means no group can read:** `single` + `restricted` + an empty list is the fail-closed default. Startup
  logs warn about it. A new installation therefore requires the `/pal whereami` authorization walkthrough.
- **Write commands ignore the read list:** the seven `server` write commands do not consult the allowed-groups list.
  Only the hard `permission_admins` administrator gate applies, so an authorized administrator can manage the single
  server from any group or direct message in either mode.

<a id="mode-transfer"></a>
### Switching modes in the settings page

After initial setup, use the Connections switcher at any time. Direct gear edits remain tolerated but offer no
guidance or migration.

- The switch button adapts to the current mode and number of ready servers:
  - Single → multi opens a confirmation dialog listing the single-server allowed groups. All are selected for
    migration by default and become bound to the only ready server.
  - Multi → single with one ready server lists each group's bindings. Groups already allowed for the retained server
    are selected by default; groups that would gain new access are not. You may adjust the selection.
  - Multi → single with several ready servers opens a transfer wizard: choose the server to retain, select groups to
    migrate, choose whether to keep or permanently delete the others and all their history, then review a summary and
    strongly confirm. Deletion requires checking "I understand this cannot be recovered."
- Grants use **move semantics:** migration clears the source store, so switching back does not revive old grants.
  Unselected groups must be reauthorized after the switch, through the single-server allowlist or `/pal link`.
- Unsaved changes disable the switcher. Save first; transfer reads only the last saved configuration.
- A failure such as too many groups, prebinding failure, or reload rollback does not change the mode. A successful
  switch with incomplete cleanup changes the mode but asks for manual review.

<a id="orphan-cleanup"></a>
### Residual data cleanup for orphan servers

Removing a server from configuration, or selecting deletion while collapsing several servers into one, can leave
historical database records. Residual data cleanup appears in the mode switcher's final step. It lists orphan
servers, requires confirming that the action cannot be recovered, and then removes them. The backend recomputes the
orphan set at execution time instead of trusting the browser list, so configured servers are never deleted. This
entry is not permanently shown yet; after a simple server removal, reopen the switcher later and use its final step.

<a id="multi-world-routing"></a>
## Multi-server routing and group authorization

> The following `link` commands are available only when `world_mode=multi`.

- `/pal link list`: list every server and this group's authorization and active status.
- `/pal link add <name>` (administrator, group chats only): authorize this group for the server and make it active.
- `/pal link remove <name>` (administrator, group chats only): revoke this group's access to the server.
- **`@server` suffix:** append `@<server-name>` to any query for a one-shot target, such as
  `/pal world status @alpha` or `/pal guild info Dawn Alliance @beta`. Server names contain no spaces; guild and base
  names may contain spaces.

<a id="permissions"></a>
## Permission management

The plugin has a **two-layer permission model** independent of AstrBot's global `admins_id`. `_is_admin` checks only
the plugin administrator list and ignores AstrBot's `admins_id` and `event.role`.

- **Administrator list (`permission_admins`):** the owner maintains rows under Permissions. Each has an `id` in
  `platform:account` form and optional `note`. Only listed accounts are plugin administrators. A player should
  preferably run `/pal whoami` in a direct message and give the returned identifier to the owner.
- **Built-in administrator gate:** every `server` write, `/pal link add`, `/pal link remove`, and `/pal confirm`
  always requires a plugin administrator. Other accounts are rejected.
- **Command permission tree (`command_permissions`):** control `enabled` and `admin_only` independently for a full
  command path or group, with inheritance on both axes. Command rows use full paths such as `player info`,
  `world status`, or `rank`; group rows use the group name. Non-administrators receive "This command requires
  administrator permission." for an admin-only command. The non-lockable set is every `server` write and `link`
  command plus `help`, `whoami`, `whereami`, and `confirm`; built-in gates protect them or they intentionally remain
  open.

<a id="legacy-permission-migration"></a>
### Automatic migration from legacy permissions

Version 0.9.5 and earlier used `features` and `admin_only_commands`. Since v0.9.6, `command_permissions` is
authoritative. On first load, the plugin converts old configuration into tri-state rows and deletes the legacy keys.
Recognized full paths preserve their permissions. Old flat values and non-lockable commands appear as invalid-lock
startup warnings instead of being applied silently. Review the result under Permissions after upgrading. The full
mapping is in
[Configuration reference · Legacy migration](configuration.en.md#legacy-permission-migration).

> **Security notice:** the administrator list is global. A listed account has administrator privileges in every
> group it participates in, including `link add`, `link remove`, and `server` writes for any group. Adapter instances
> and groups sharing one bot also share this namespace. Grant access carefully. `id` and `note` are stored in plain
> text under `data/config/`; never put real names, contact details, or other PII in `note`. See
> [Configuration reference · Permissions](configuration.en.md#permissions).

<a id="server-admin"></a>
## Server administration (controlled writes)

The plugin crosses from read-only monitoring into controlled writes. The `server` group has seven commands for
official REST write endpoints (`announce`, `save`, `kick`, `unban`, `ban`, `shutdown`, and `stop`), plus
`/pal confirm`. The contract is: all writes are off by default, authorized administrators only, and audited once
actual execution begins.

| Command | Arguments | Feature group | Permission / context | Description |
|------|------|--------|-------------|------|
| `/pal server announce` | `<message>` | `server_admin_basic` | **Authorized administrators only** | Broadcast to the whole server; message is the complete remaining input |
| `/pal server save` | — | `server_admin_basic` | **Authorized administrators only** | Save the world |
| `/pal server kick` | `<player\|userid> [reason]` | `server_admin_basic` | **Authorized administrators only** | Kick a player who may reconnect; accept a character name resolved live or a direct user ID |
| `/pal server unban` | `<userid>` | `server_admin_basic` | **Authorized administrators only** | Unban a player |
| `/pal server ban` | `<player\|userid> [reason]` | `server_admin_danger` | **Authorized administrators only** · Dangerous | Ban a player; optional confirmation |
| `/pal server shutdown` | `<seconds> [message]` | `server_admin_danger` | **Authorized administrators only** · Dangerous | Scheduled shutdown; seconds must be an integer from 1 to 86400, and the remaining text is the optional announcement; optional confirmation |
| `/pal server stop` | — | `server_admin_danger` | **Authorized administrators only** · Dangerous | Stop immediately **without saving, risking progress loss**; optional confirmation |

<a id="three-layer-safety"></a>
### Three-layer safety model

One central gate checks every write in this order and stops on any failure:

1. **Hard administrator gate first:** callers outside `permission_admins` always receive the permission error,
   regardless of feature enablement, so they cannot infer whether dangerous commands are on. An empty list is
   fail-closed and permits nobody.
2. **Feature-group gate:** `server_admin_basic` contains announce, save, kick, and unban;
   `server_admin_danger` contains ban, shutdown, and stop. Both default to off. An operator can enable only basic
   writes without exposing dangerous ones.
3. **Server authorization gate:** single-server writes always target the only ready server and ignore the
   `single_allowed_groups` read list. Multi-server writes follow group bindings, reject direct messages under
   restricted access, and do not accept a temporary `@server` override. Consider the open-access blast radius below.

<a id="confirmation"></a>
### Confirmation for the danger group

`require_confirmation` defaults to off. When enabled, the first `ban`, `shutdown`, or `stop` does not execute. It
returns a preview with the character name, user-ID suffix, and summary, then requires `/pal confirm` within
`confirmation_timeout`, which defaults to 30 seconds. Confirmation rechecks permission, group enablement, and server
authorization; any change discards the pending operation. Each administrator has at most one pending operation, and
a new one replaces the old one. Hot reload clears every pending operation. Basic commands never require confirmation.

<a id="target-player-resolution"></a>
### Target player resolution for kick and ban

The target may be a user ID such as `steam_<17-digits>`, used directly, or a character name. At execution time, a
name is matched exactly against live `GET /players` results. One match is used, duplicates return candidates and ask
for an exact user ID, and no match reports that the online player was not found. This live lookup bypasses privacy
filters to read the true user ID required for a write. That is reasonable for an operator and does not weaken
`/pal me hide` against peer players. The plaintext ID is discarded immediately and is never stored or logged.

<a id="audit"></a>
### Audit storage and read-only frontend view

A write that reaches actual execution records one row in `admin_audit` while audit storage is healthy: time,
administrator identifier, action, server, target character name and **hashed** user ID, and result or error category.
The Audit section of the settings page shows the latest N rows in reverse order. `audit_retention_days`, default 180,
is currently only a target; scheduled deletion is not implemented. Plaintext `admin_id` and `target_name` are
controlled personal information.

<a id="security-notice"></a>
### ⚠️ Important security notice

- **Open-access blast radius:** with `access_mode=open`, `_authorized` always succeeds and writes are no longer
  constrained by group grants. Any authorized administrator can run `server stop` or `server ban` on any ready server
  from any group or direct message. Avoid combining open access with `server_admin_danger`, especially on shared bots.
- **`server stop` can lose progress:** `/pal server stop` forces a stop without saving. Run `/pal server save` first,
  or use `/pal server shutdown`, whose countdown permits a normal save.
- **Attribution:** Palworld REST does not authenticate an in-game operator identity. Audit records identify the
  authorized administrator who initiated the action through the bot, not an in-game identity.
- **Name lookup depends on `/players`:** when the target server is unreachable, name resolution returns a clear
  error. A direct user ID remains available as a fallback.

<a id="degraded-behavior"></a>
## Degraded behavior

When the API is unreachable, the plugin reports that world data is currently unavailable and gives the time of the
last successful update. It never guesses that the server is offline. If only some endpoints fail, only their modules
degrade; the rest continue normally.
