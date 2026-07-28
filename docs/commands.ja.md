<a id="commands"></a>
# コマンドと機能の完全リファレンス

[简体中文](commands.md) | **日本語** | [English](commands.en.md)

v0.9.5 以降、コマンドは `/pal <group> <action> [arguments]` の階層形式を使います。5 個のコマンド
グループ（`world`、`guild`、`player`、`server`、`link`）と、8 個のフラットコマンド
（`rank`、`online`、`me`、`dex`、`help`、`whoami`、`whereami`、`confirm`）があります。
すべて `/pal` で始まり、plain text を返します。クエリは読み取り専用です。**サーバー操作は
制御付き書き込み**で、すべて初期状態で無効、認可済み管理者だけが利用でき、実行段階に到達した要求は
監査に記録されます。[サーバー操作](#server-admin)を参照してください。機能グループに属するコマンドは
下記の表で実効的に有効な場合だけ利用でき、`core` は常に利用できます。

> **グループ名だけなら簡易ヘルプ：** `/pal world` や `/pal server` のようにグループだけを送ると、
> 現在の機能と利用者の権限で絞り込んだサブコマンドを返します。一般利用者に書き込みコマンドは表示されません。

<a id="first-setup"></a>
## 初回利用と初回構成ゲート

**新規インストール後は、プラグインの設定画面で単一サーバーまたは複数サーバーを一度選択して確定**
すると、すべてのコマンドが利用できます。`routing.setup_confirmed` が `true` になるまで、
次のコマンド以外は初回構成の案内を返します。

- `/pal help` — 権限別ヘルプ
- `/pal whoami` — 自分のアカウント識別子
- `/pal whereami` — 現在のセッション識別子

> 確定前の設定画面は通常の構成セクションではなく初回 wizard を表示します。モードを選んで確定すると
> `world_mode` と `routing.setup_confirmed=true` を保存し、コマンドを解放して通常画面へ移ります。
> 以降は「接続」から安全に切り替えます。AstrBot の歯車画面で値を直接編集する方法は緊急用で、
> 認可の移行も再確認も行いません。[動作モード](#world-modes)と
> [構成リファレンス · routing](configuration.ja.md#routing)を参照してください。

<a id="command-reference"></a>
## コマンド一覧

<a id="world-commands"></a>
### `world` グループ — ワールド観測（クエリ）

| コマンド | 引数 | 機能グループ | 説明 |
|------|------|--------|------|
| `/pal world status` | — | `core` | オンライン人数、FPS の状態、ワールド日数など |
| `/pal world overview` | — | `guilds_bases` | ギルドと拠点のワールドスナップショット。初期状態が有効な `guilds_bases` に属します |
| `/pal world rules` | — | `core` | 倍率などのワールドルール |
| `/pal world today` | — | `report` | 本日の日報とオンライン統計 |
| `/pal world events` | — | `events` | ワールドイベント履歴 |

<a id="guild-commands"></a>
### `guild` グループ — ギルドと拠点（クエリ）

> `game-data`（PalGameDataBridge）から導出したギルドと拠点のデータに依存します。game-data の安定提供に
> 伴い**初期状態で有効**です。有効になると `/game-data` をポーリングし、`world overview` もこの
> グループに属します。不要なら「機能」で対応するコマンドを無効にしてください。

| コマンド | 引数 | 機能グループ | 説明 |
|------|------|--------|------|
| `/pal guild list` | — | `guilds_bases` | ギルド一覧 |
| `/pal guild info` | `<name>` | `guilds_bases` | ギルド詳細 |
| `/pal guild bases` | — | `guilds_bases` | 拠点一覧 |
| `/pal guild base` | `<name\|#number>` | `guilds_bases` | 拠点の行動分布、休憩率、雰囲気バッジ |

<a id="player-commands"></a>
### `player` グループ — プレイヤー情報（クエリ）

| コマンド | 引数 | 機能グループ | 説明 |
|------|------|--------|------|
| `/pal player info` | `<player>` | `players` | プレイヤー 1 人のレベル、時間、拠点などを表示 |
| `/pal player bind` | `<player>` | `players` | platform account とプレイヤーを連携し、`/pal me` が本人を識別できるようにします |
| `/pal player unbind` | — | `players` | 自分の連携を解除します。`bind` の逆操作です |

<a id="flat-commands"></a>
### フラットコマンド — よく使うクエリと meta command

| コマンド | 引数 | 機能グループ | 権限 / 場面 | 説明 |
|------|------|--------|-------------|------|
| `/pal rank` | `[today\|total\|level\|climb]` | `players` | 全員 | `today` は本日のオンライン時間（初期値）、`total` はデータ保持期間内の累計オンライン時間、`level` はレベル、`climb` は直近 7 日間のレベル上昇ランキング |
| `/pal online` | — | `core` | 全員 | 現在のオンラインプレイヤー |
| `/pal me` | `[hide\|show\|card\|卡\|图]` | `players` | 全員 | レベル、ギルド、記録済みプレイヤー内のパーセンタイル、同行パルを含むプロフィール。`card`/`卡`/`图` は画像を生成します（**同行パルには `guilds_bases` が必要**）。`hide`/`show` でランキングとクエリから自分を非表示または復帰できます |
| `/pal dex` | — | `guilds_bases` | 全員 | 観測済み種族の進行を属性別にまとめ、プラグイン全体で蓄積するサーバーのパル図鑑 |
| `/pal whoami` | — | `core` | 全員（**ダイレクトメッセージ推奨**） | `aiocqhttp:12345` のような自分の `platform:account` を表示し、所有者へ管理者登録を依頼するために使います |
| `/pal whereami` | — | `core` | 全員 | `aiocqhttp:GroupMessage:123456` のような現在のセッション UMO だけを表示し、制限付き単一サーバーの許可リスト登録に使います。両モードで常に利用でき、対象引数を受け付けません |
| `/pal help` | — | `core` | 全員 | 実効的な機能と利用者の権限で絞り込んだヘルプ |
| `/pal confirm` | — | `core` | **認可済み管理者のみ** | 直前の保留中の危険な操作を確定します。存在しないか期限切れの場合はその旨を返します |

> **`rank` の種類とプライバシー：** `today` と `total` はオンライン時間ランキングで、strict
> プライバシーでは両方停止します。`total` は全期間ではなく保持期間内だけを集計し、管理者の除外リストと
> `/pal me hide` の両方に従います。非表示プレイヤーの名前はグループ全体で消え、存在も公開しません。
> `level` はレベルランキングです。`climb` は直近 7 日間のレベル上昇で、履歴が 7 日未満なら
> 「bot が記録を開始してから」と正確に注記します。

<a id="server-commands"></a>
### `server` グループ — サーバー操作（制御付き書き込み）

[サーバー操作](#server-admin)を参照してください。コマンドは `/pal server announce`、
`/pal server save`、`/pal server kick`、`/pal server unban`、`/pal server ban`、
`/pal server shutdown`、`/pal server stop` です。すべて認可済み管理者を要求します。

<a id="link-commands"></a>
### `link` グループ — サーバー選択とグループ認可（複数サーバーのみ）

[複数サーバーのルーティングとグループ認可](#multi-world-routing)を参照してください。コマンドは
`/pal link list`、`/pal link add <name>`、`/pal link remove <name>` です。単一サーバーモードでは
選択が不要なため、`link` グループは非表示かつ実行時に拒否されます。

任意のクエリ末尾に **`@<server-name>`** を追加し、その要求だけ対象を指定できます。詳細は後述します。

> **操作コマンドは一時的な `@server` 上書きに非対応です：** 単一サーバーは唯一の準備済みサーバー、
> 複数サーバーはグループの現在のアクティブサーバーを使います。対象を変更するには先に
> `/pal link add <server-name>` を実行してください。操作コマンド末尾の `@word` は対象を変えません。
> 一斉通知と理由では連続する空白や改行を 1 個の空白にまとめるため、入力の完全な保持は保証しません。

<a id="feature-matrix"></a>
## 機能スイッチ → 利用可能コマンド

機能グループは modular です。v0.9.6 以降は「権限」のコマンドツリーが制御し、
`command_permissions` に保存します。
[構成リファレンス · コマンドツリー権限](configuration.ja.md#command-tree-permissions)を参照してください。
**コマンドまたはグループを無効にすると有効ではないと返し、`/pal help` から消えます。**
再度有効にすれば元に戻ります。`guild` と `world overview` は初期状態が有効な `guilds_bases`
に属します。このグループのいずれかを有効にすると `/game-data` のポーリングが始まり、
読み取り専用の観測 endpoint は常に収集されます。

| 機能グループ | 初期状態 | コマンド（完全なパス） | 有効時 | 無効時 |
|--------|------|----------|--------|----------------|
| `core`（無効化不可） | 常に有効 | `world status` `world rules` `online` 引数なしの `server` 引数なしの `link` `whoami` `whereami` `help` `confirm` | ✅ 利用可能 | — 無効化できません |
| `report` | 有効 | `world today` | ✅ 利用可能 | ❌ 有効ではないと返し、help から非表示 |
| `events` | 有効 | `world events` | ✅ 利用可能でイベントを記録 | ❌ 有効ではないと返し、イベントを生成しません |
| `guilds_bases` | **有効** | `world overview` `guild list` `guild info` `guild bases` `guild base` `dex` | ✅ 利用可能で `/game-data` をポーリング | ❌ 有効ではないと返し、help から非表示 |
| `players` | **無効** | `player info` `player bind` `player unbind` `rank` `me` | ✅ 利用可能 | ❌ 有効ではないと返し、help から非表示 |
| `server_admin_basic` | **無効** | `server announce` `server save` `server kick` `server unban` | ✅ 認可済み管理者だけが利用可能 | ❌ 管理者には無効と返して help から隠し、一般利用者には常に管理者権限が必要と返します |
| `server_admin_danger` | **無効** | `server ban` `server shutdown` `server stop` | ✅ 認可済み管理者だけが利用可能。再確認も選択可能 | ❌ 管理者には無効と返して help から隠し、一般利用者には常に管理者権限が必要と返します |

> `server_admin_basic` と `server_admin_danger` は制御付き書き込みで、初期状態は無効です。
> [サーバー操作](#server-admin)を参照してください。一般利用者には機能の有効状態に関係なく
> 常に権限エラーを返し、危険な操作の有効状態を応答から推測できないようにします。

> `players` はプライバシーのため初期状態で無効です。オンライン時間ランキングは本日または保持期間内、
> レベルランキングはオフラインも含みます。strict プライバシーでは時間ランキングを停止し、
> player profile の座標も隠します。管理者の除外リストと `/pal me hide` を利用でき、除外または
> 非表示のプレイヤーはランキングとクエリに現れず、存在も公開されません。

> `guilds_bases` は初期状態で有効です。ギルド、拠点、PalBox、`world overview` は
> `game-data`（PalGameDataBridge）から導出します。グループ内のいずれかが実効的に有効な間は
> `/game-data` をポーリングします。不要なら「機能」で対応項目を無効にしてください。
> [構成リファレンス](configuration.ja.md#features)も参照してください。

<a id="world-modes"></a>
## 動作モード：単一サーバー / 複数サーバー

`routing.world_mode` がルーティングを選び、初期値は `single` です。初回画面が選択を案内します。
その後は「接続」の切替機能で影響確認、認可移行、残存データの整理を行います。AstrBot の歯車画面で
直接編集する方法は、移行と確認を省略する緊急用です。

- **`single`（初期値）：** すべての操作が最初の準備済み 1 台を対象にします。`link` は非表示かつ
  実行時に拒否され、`@server` 上書きとグループバインドを無視します。読み取り認可は次節を参照してください。
- **`multi`：** 1 個のプラグインが複数台を監視し、グループごとに認可してアクティブなサーバーを
  切り替えます。`link` で選択と認可を行い、クエリは一時的な `@<server-name>` 上書きを利用できます。
  読み取り認可はデータベース上の `/pal link` グループバインドを使います。

<a id="single-world-access"></a>
### 単一サーバーの読み取り認可と書き込み

- **読み取りコマンド：** `access_mode=restricted` では最上位の `single_allowed_groups` に登録された
  グループまたはダイレクトメッセージだけが照会できます。それ以外は `/pal whereami` と設定画面の
  リストを案内して拒否します。`access_mode=open` は全セッションを許可し、リストを無視します。
- **リストの構成：** グループで `/pal whereami` を実行して UMO を取得し、管理者が「接続」に
  `umo` と任意の `note` の行を追加します。ダイレクトメッセージも同じリストで判定します。
- **空リストでは誰も読み取れない：** `single` + `restricted` + 空リストは fail-closed の初期状態です。
  起動ログも警告します。新規インストールでは `/pal whereami` の認可手順が必要です。
- **書き込みは読み取りリストを無視する：** 7 個の `server` 書き込みは許可グループを参照せず、
  `permission_admins` の強制管理者ゲートだけを使います。認可済み管理者はどのグループや
  ダイレクトメッセージからでも単一サーバーを操作できます。

<a id="mode-transfer"></a>
### 設定画面でモードを切り替える

初回構成後は「接続」の切替機能をいつでも利用できます。歯車画面での直接編集も許容されますが、
案内と移行はありません。

- 切替ボタンは現在のモードと準備済みサーバー数に応じて動作します。
  - Single → multi：確認 dialog に単一サーバーの許可グループを表示します。初期状態ではすべてを
    選択して移行し、唯一の準備済みサーバーへバインドします。
  - Multi → single、準備済み 1 台：各グループのバインドを表示します。残すサーバーへ既に認可済みの
    グループは選択済み、切替によって新しく認可されるグループは未選択です。手動で変更できます。
  - Multi → single、準備済み複数台：transfer wizard で残すサーバー、移行するグループ、
    ほかのサーバーと全履歴を保持または完全削除する選択、概要と強い確認の順に進みます。
    削除時は復元できないことへの同意が必要です。
- 認可は **move semantics** です。移行後は元の保存先を空にするため、モードを戻しても復活しません。
  未選択のグループは単一サーバーの許可リストまたは `/pal link` で再認可します。
- 保存していない変更があると切替機能は無効です。transfer は最後に保存した構成だけを読みます。
- グループ数超過、事前バインド失敗、reload rollback などの失敗ではモードを変更しません。
  切替成功後に整理だけが不完全な場合はモードを変更し、手動確認を案内します。

<a id="orphan-cleanup"></a>
### orphan server の残存データ整理

構成からサーバーを削除した場合や複数台から 1 台への切替で削除を選んだ場合、履歴がデータベースへ
残ることがあります。切替機能の最終ステップにある「残存データの整理」は orphan server を一覧表示し、
復元できないことへの確認後に削除します。実行時に backend が orphan 集合を再計算し、browser の一覧を
信用しないため、構成中のサーバーを誤って削除しません。現在は常設の入口ではありません。サーバーだけを
削除した場合は、後から切替機能を開いて最終ステップを使ってください。

<a id="multi-world-routing"></a>
## 複数サーバーのルーティングとグループ認可

> 以下の `link` コマンドは `world_mode=multi` の場合だけ利用できます。

- `/pal link list`：すべてのサーバーと、このグループの認可・アクティブ状態を表示します。
- `/pal link add <name>`（管理者、グループチャットのみ）：このグループに対象サーバーを認可し、
  アクティブにします。
- `/pal link remove <name>`（管理者、グループチャットのみ）：このグループの認可を取り消します。
- **`@server` suffix：** 任意のクエリ末尾に `@<server-name>` を追加して一時的に対象を指定できます。
  例：`/pal world status @alpha`、`/pal guild info Dawn Alliance @beta`。サーバー名には空白を含めず、
  ギルド名と拠点名には空白を使用できます。

<a id="permissions"></a>
## 権限管理

プラグインは AstrBot のグローバルな `admins_id` と独立した **2 層の権限モデル**を使います。
`_is_admin` はプラグイン管理者リストだけを参照し、`admins_id` と `event.role` を無視します。

- **管理者リスト（`permission_admins`）：** 所有者が「権限」で `platform:account` 形式の `id` と
  任意の `note` を登録します。登録済みアカウントだけがプラグイン管理者です。プレイヤーはできれば
  ダイレクトメッセージで `/pal whoami` を実行し、返された識別子を所有者へ渡します。
- **組み込み管理者ゲート：** すべての `server` 書き込み、`/pal link add`、`/pal link remove`、
  `/pal confirm` は常にプラグイン管理者を要求します。それ以外のアカウントは拒否されます。
- **コマンド権限ツリー（`command_permissions`）：** 完全なコマンドパスまたはグループについて、
  `enabled` と `admin_only` を独立して制御し、両軸で継承できます。コマンド行は `player info`、
  `world status`、`rank` など、グループ行はグループ名を使います。管理者限定コマンドを一般利用者が
  実行すると管理者権限が必要だと返します。管理者限定にできない集合は、すべての `server` 書き込みと
  `link` コマンド、および `help`、`whoami`、`whereami`、`confirm` です。組み込みゲートで保護されるか、
  意図的に全員へ公開されます。

<a id="legacy-permission-migration"></a>
### 旧権限からの自動移行

v0.9.5 以前は `features` と `admin_only_commands` を使っていました。v0.9.6 以降は
`command_permissions` が正本です。古い構成を初めて読み込むと 3 状態行へ変換して旧キーを削除します。
認識できる完全なパスは権限を保持し、旧形式のフラットな値や管理者限定にできないコマンドは、暗黙に
適用せず無効な lock として起動時に警告します。アップグレード後は「権限」で結果を確認してください。
対応表は[構成リファレンス · 旧形式からの移行](configuration.ja.md#legacy-permission-migration)にあります。

> **セキュリティ上の注意：** 管理者リストは全体で共有されます。登録アカウントは参加するすべての
> グループで管理者権限を持ち、任意のグループに対する `link add`、`link remove`、`server` 書き込みも
> 実行できます。同じ bot を共有する adapter instance とグループも同じ名前空間を使います。
> 慎重に認可してください。`id` と `note` は `data/config/` に平文で保存されるため、実名や連絡先などを
> `note` に入力しないでください。[構成リファレンス · 権限](configuration.ja.md#permissions)も参照してください。

<a id="server-admin"></a>
## サーバー操作（制御付き書き込み）

このプラグインは読み取り専用の監視から制御付き書き込みへ範囲を広げます。`server` グループは
公式 REST 書き込み endpoint に対する 7 個のコマンド（`announce`、`save`、`kick`、`unban`、`ban`、
`shutdown`、`stop`）と `/pal confirm` を提供します。すべて初期状態で無効、認可済み管理者だけが利用でき、
実際の実行段階に入ると監査へ記録するという契約です。

| コマンド | 引数 | 機能グループ | 権限 / 場面 | 説明 |
|------|------|--------|-------------|------|
| `/pal server announce` | `<message>` | `server_admin_basic` | **認可済み管理者のみ** | サーバー全体へ一斉通知。残りの入力全体を message として使います |
| `/pal server save` | — | `server_admin_basic` | **認可済み管理者のみ** | ワールドを保存します |
| `/pal server kick` | `<player\|userid> [reason]` | `server_admin_basic` | **認可済み管理者のみ** | 再接続可能な kick。実行時に解決するキャラクター名または user ID を直接指定できます |
| `/pal server unban` | `<userid>` | `server_admin_basic` | **認可済み管理者のみ** | プレイヤーの BAN を解除します |
| `/pal server ban` | `<player\|userid> [reason]` | `server_admin_danger` | **認可済み管理者のみ** · 危険 | プレイヤーを BAN。任意で再確認できます |
| `/pal server shutdown` | `<seconds> [message]` | `server_admin_danger` | **認可済み管理者のみ** · 危険 | カウントダウン停止。秒数は 1–86400 の整数で、残りの文は任意の通知です。再確認も選択できます |
| `/pal server stop` | — | `server_admin_danger` | **認可済み管理者のみ** · 危険 | **保存せず即時停止し、進行を失う危険があります**。再確認も選択できます |

<a id="three-layer-safety"></a>
### 3 層の安全モデル

単一の中央 gate がすべての書き込みを次の順で検査し、いずれかが失敗すると遮断します。

1. **強制管理者ゲートを最初に検査：** `permission_admins` 外の利用者には、機能の有効状態に関係なく
   常に権限エラーを返します。危険な操作の有効状態を推測できません。空リストは fail-closed で誰も許可しません。
2. **機能グループゲート：** `server_admin_basic` は announce、save、kick、unban、
   `server_admin_danger` は ban、shutdown、stop を含みます。どちらも初期状態は無効です。
   basic だけを有効にして danger を公開しない運用ができます。
3. **サーバー認可ゲート：** 単一サーバーの書き込みは唯一の準備済みサーバーを対象にし、
   `single_allowed_groups` の読み取りリストを無視します。複数サーバーの書き込みはグループのバインドに
   従い、restricted ではダイレクトメッセージを拒否し、一時的な `@server` 上書きも受け付けません。
   後述する open アクセスの影響範囲に注意してください。

<a id="confirmation"></a>
### danger グループの再確認

`require_confirmation` の初期値は off です。有効にすると最初の `ban`、`shutdown`、`stop` は実行せず、
キャラクター名、user ID 末尾、概要を含むプレビューを返します。その後、初期値 30 秒の
`confirmation_timeout` 内に `/pal confirm` が必要です。確定時に権限、グループの有効状態、
サーバー認可を再検査し、どれかが変わっていれば保留中の操作を破棄します。各管理者は同時に 1 件だけを
保持し、新しい操作が以前のものを置き換えます。hot reload はすべての保留操作を消去します。
basic コマンドに再確認はありません。

<a id="target-player-resolution"></a>
### kick / ban の対象プレイヤー解決

対象には `steam_<17-digits>` のような user ID を直接指定するか、キャラクター名を指定できます。
実行時に名前を `GET /players` の結果と完全一致させます。1 件なら使用し、同名が複数なら候補を返して
正確な user ID を要求し、0 件ならオンラインプレイヤーが見つからないと返します。この取得は書き込みに
必要な実 ID を得るためプライバシー filter を迂回します。運営者にとって妥当であり、
`/pal me hide` による peer からの存在保護を弱めません。平文の ID は直ちに破棄し、保存も記録もしません。

<a id="audit"></a>
### 監査保存とフロントエンドの読み取り専用表示

実際の実行段階に到達した書き込みは、監査ストレージが正常な場合に `admin_audit` へ 1 行記録します。
時刻、管理者識別子、action、server、対象キャラクター名と **hash 化した** user ID、結果または
エラー分類を含みます。設定画面の「監査」は最新 N 件を逆順で表示します。初期値 180 日の
`audit_retention_days` は現時点では目標にすぎず、自動削除は未実装です。平文の `admin_id` と
`target_name` は管理対象の個人情報です。

<a id="security-notice"></a>
### ⚠️ 重要なセキュリティ上の注意

- **open アクセスの影響範囲：** `access_mode=open` では `_authorized` が常に成功し、書き込みが
  グループ認可に制限されません。任意の認可済み管理者が、どのグループやダイレクトメッセージからでも
  任意の準備済みサーバーに `server stop` または `server ban` を実行できます。特に共有 bot では
  open と `server_admin_danger` を組み合わせないでください。
- **`server stop` は進行を失う可能性がある：** `/pal server stop` は保存せず強制停止します。
  先に `/pal server save` を実行するか、カウントダウン中に正常保存できる `/pal server shutdown` を使います。
- **帰属：** Palworld REST はゲーム内の操作者 ID を認証しません。監査は bot を通じて操作を開始した
  認可済み管理者を記録し、ゲーム内 ID を表すものではありません。
- **名前解決は `/players` に依存：** 対象サーバーへ到達できない場合、名前解決は明確なエラーを返します。
  user ID の直接指定を代替手段として利用できます。

<a id="degraded-behavior"></a>
## 縮退時の動作

API に到達できない場合は、ワールドデータを現在取得できないことと、最後に成功した更新からの時間を
表示します。サーバーが停止したとは推測しません。一部の endpoint だけが失敗した場合は関連 module
だけを縮退させ、それ以外は通常どおり動作します。
