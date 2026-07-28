<a id="configuration"></a>
# 構成リファレンス

[简体中文](configuration.md) | **日本語** | [English](configuration.en.md)

すべての項目はプラグインの設定画面から編集できます。このページは項目別のリファレンスで、
各フィールド名は構成ファイルのキーと一致します。画面へのアクセスと保存時の動作は
[プラグイン画面](#plugin-page)を参照してください。

<a id="servers"></a>
## servers（複数サーバー）

複数の Palworld サーバーを登録できます。`name` は一意で、空白、コロン、`@` を含めません。
`base_url` は `http://127.0.0.1:8212` のように指定します。`enabled` はエントリの有効状態、
`username` は通常 `admin`、`timeout` は要求のタイムアウト秒数、`verify_tls` は HTTPS 証明書の
検証を制御します。パスワードは `password_env`（推奨する環境変数名）または `password`
（ディスクへ保存される平文）のどちらかで渡します。サーバーごとの `timezone` で全体設定を上書きできます。

<a id="routing"></a>
## routing（アクセス制御）

- **world_mode：** 初期値は `single` です。単一サーバーモードではすべての操作が最初の準備済み
  サーバーを使い、`link` グループは非表示かつ実行時に拒否されます。`@server` による上書きと
  グループのバインドは無視されます。`multi` は複数台を監視し、グループごとに認可と切り替えを行います。
  初回はプラグイン画面が選択を案内します。その後は「接続」の切替機能で影響確認、認可の移行、
  残存データの整理を行います。AstrBot の歯車画面で値を直接編集する方法は緊急用で、移行と確認を省略します。
- **setup_confirmed：** bool、初期値 `false`。初回構成ゲートの状態です。`true` になるまで
  `/pal help`、`/pal whoami`、`/pal whereami` 以外の `/pal` コマンドは案内を返します。
  [コマンド一覧 · 初回利用](commands.ja.md#first-setup)も参照してください。通常は手動で変更しません。
  初回画面でモードを確定すると `world_mode` と一緒に `setup_confirmed=true` が保存されます。
  新規インストールでは AstrBot が schema の初期値を補完するため、必ず一度確定が必要です。
- **access_mode：** 初期値は `restricted` です。`open` はどのセッションからのクエリも許可します。
  制限付き認可はモードで異なり、単一サーバーでは `single_allowed_groups`、複数サーバーでは
  データベース上の `/pal link` グループ認可を使います。
- **default_server：** 複数サーバーモードで明示的な対象もアクティブなバインドもない場合に使う
  サーバーの `name` です。単一サーバーモードは唯一の準備済みサーバーを使い、この値を無視します。
- **single_allowed_groups：** 次節で説明します。`world_mode=single` かつ
  `access_mode=restricted` のときだけ適用され、複数サーバーモードでは無視されます。
- **group_bindings：** 複数サーバーモードだけで意味を持つ任意の初期認可です。管理者による
  `/pal link add` と同等ですが、初期状態の seed に限られ、実行中の変更を上書きしません。
- **privacy.mode：** `strict`、`balanced`（初期値）、`advanced`（現行版では balanced と同じ動作）。

<a id="single-allowed-groups"></a>
### single_allowed_groups（単一サーバーの許可リスト）

制限付き単一サーバーモードの読み取り認可を制御する最上位リストです。`group_bindings` と同じ
`template_list` 形式を使います。登録されたグループまたはダイレクトメッセージだけがサーバーを
照会できます。open アクセスでは無視されます。

| フィールド | 型 | 初期値 | 意味 |
| --- | --- | --- | --- |
| `single_allowed_groups` | エントリ単位のリスト | 空 | 各行にセッションの `umo`（unified_msg_origin、例：`aiocqhttp:GroupMessage:123456`）と任意の `note` を指定します。対象グループで `/pal whereami` を実行して UMO を取得し、管理者が「接続」に追加します |

- **UMO の取得：** 対象グループで `/pal whereami` を実行します。ダイレクトメッセージにも固有の
  UMO があり、同じリストで判定されます。
- **空リストでは誰も読み取れない：** `single` + `restricted` + 空リストは fail-closed の初期状態です。
  管理者が案内に従ってグループを追加するまで照会できません。起動ログにも警告が出ます。
- **書き込みコマンドはこのリストを使わない：** 7 個の `server` 書き込みコマンドは
  `permission_admins` の強制管理者ゲートだけで保護されます。認可済み管理者は任意のグループまたは
  ダイレクトメッセージから単一サーバーを操作できます。
- **平文保存のため個人情報を入力しない：** `umo` と `note` は `data/config/` に平文で保存されます。
  実名や連絡先などを `note` に記入しないでください。

> **複数サーバーモードはこのリストを読みません：** `/pal link` のグループバインドを使います。
> 設定画面の切替機能は選択した項目を複数サーバー認可へ移行できます。`world_mode` の直接編集では移行しません。

<a id="mode-transfer"></a>
### 設定画面でのモード変換

初回構成と緊急の直接編集を除き、「接続」の切替機能から `world_mode` を変更します。認可は
move semantics で移行されるため、元のモードへ戻しても以前の認可は復活しません。

- Single → multi：選択した `single_allowed_groups` を複数サーバーの `group_bindings` へ書き込み、
  単一サーバーのリストを空にします。
- Multi → single：選択したグループバインドを `single_allowed_groups` へ統合し、複数サーバーの
  バインドを空にします。複数台が準備済みなら残す 1 台を選び、ほかのサーバーの履歴を完全に
  削除するか選べます。削除は復元できません。

構成からサーバーを削除した場合やモード変更で削除を選んだ場合は、切替機能の最終ステップにある
「残存データの整理」を使います。バックエンドが orphan の集合を再計算し、構成にないサーバーの
データだけを削除します。この入口は現在、設定画面に常設されていません。サーバーだけを削除した場合は、
後から切替機能を開き、最終ステップで整理できます。

<a id="permissions"></a>
## permissions（権限管理）

プラグイン管理者は AstrBot のグローバルな `admins_id` と独立しています。以下のリストだけを参照し、
`admins_id` と `event.role` は使いません。プレイヤーは `/pal whoami` で `platform:account` 形式の
識別子を取得し、所有者へ登録を依頼できます。

| 項目 | 型 | 初期値 | 意味 |
| --- | --- | --- | --- |
| `permission_admins` | エントリ単位のリスト | 空 | プラグイン管理者。各行に `id`（`platform:account`、例：`aiocqhttp:12345`）と任意の `note` を指定します。登録されたアカウントだけが `link add`、`link remove`、`server` 書き込み、管理者限定コマンドを実行できます |
| `command_permissions` | エントリ単位の 3 状態行 | 空 | コマンドツリー制御の永続的な正本です。`world status` や `player info` の完全なコマンドパス、または `guild` や `player` のグループを対象に、`enabled` と `admin_only` を `inherit`、`on`、`off` で上書きします。「権限」から視覚的に編集できます |

<a id="command-tree-permissions"></a>
### コマンドツリーの権限モデル

各コマンドノードには独立した 2 つの制御があります。

- **`enabled`：** `off` のコマンドは「有効ではありません」と返して `/pal help` から消え、
  そのコマンドから導出されるデータ収集も停止します。`core` は常に有効です。
- **`admin_only`：** `on` の場合、プラグイン管理者リスト外の利用者へ管理者権限が必要だと返します。

各軸は `inherit`、`on`、`off` を取ります。疎な上書きと 3 段階の継承により、実効値はコマンド行、
グループ行、[features](#features) の機能グループ初期値の順に決まります。変更したいコマンドまたは
グループだけを登録してください。危険な書き込みコマンド（`server ban/shutdown/stop`）は
グループの `enabled` を継承せず、個別に有効化する必要があります。

**管理者限定にできない集合**は、すべての `server` 書き込み、すべての `link` コマンド、および
`help`、`whoami`、`whereami`、`confirm` です。組み込みの機能ゲートと管理者ゲートで保護されるか、
設計上すべての利用者に公開されます。`server` 書き込みの `enabled` は引き続き有効で、初期状態はすべて off です。

<a id="legacy-permission-migration"></a>
### features / admin_only_commands からの移行

v0.9.5 以前は boolean の `features` と `admin_only_commands` リストを使っていました。v0.9.6 以降は
`command_permissions` に統一されています。古い構成を初めて読み込むと、同等の 3 状態行へ自動変換し、
保存した後に旧キーを削除します。

| 旧項目 | 旧値（初期値と異なる場合だけ移行） | 生成される `command_permissions` 行 |
| --- | --- | --- |
| `features.report` | `off` | `world today` → `enabled=off` |
| `features.events` | `off` | `world events` → `enabled=off` |
| `features.guilds_bases` | `on` | `guild`（グループ）→ `enabled=on` |
| `features.players` | `on` | `player`（グループ）+ `rank` + `me` → `enabled=on` |
| `features.server_admin_basic` | `on` | `server announce/save/kick/unban` → `enabled=on` |
| `features.server_admin_danger` | `on` | `server ban/shutdown/stop` → `enabled=on` |
| `admin_only_commands` の各項目 | `player info` などの完全なパス | 対応コマンド → `admin_only=on` |

> `admin_only_commands` には完全なコマンドパスが必要です。`player` のような旧形式の値は認識できず、
> 移行時に無効な lock として起動ログへ報告され、暗黙には適用されません。管理者限定にできないコマンドも
> 同様です。アップグレード後は「権限」で結果を確認し、旧キーの管理を終了してください。

**重要なセキュリティ上の注意：**

- **グローバルな影響範囲：** 管理者リストは全体で共有されます。登録されたアカウントは参加する
  すべてのグループで管理者権限を持ち、任意のグループに対する `link add`、`link remove`、
  `server` 書き込みも実行できます。この範囲を信頼できる場合だけ追加してください。
- **adapter とグループ間で共有される名前空間：** 同じ bot を利用する adapter instance と
  グループは、管理者リストとアカウント名前空間を共有します。
- **平文保存のため個人情報を入力しない：** `id` と `note` は `data/config/` に平文で保存されます。
  実名や連絡先を `note` に記入しないでください。

<a id="polling"></a>
## polling（サーバーごとに適用される全体間隔）

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `metrics_seconds` | 30 | `/metrics` の間隔（秒）。FPS、オンライン人数などのワールド指標を更新します |
| `players_seconds` | 30 | `/players` の間隔（秒）。オンライン一覧とログインセッションを更新します |
| `info_seconds` | 600 | `/info` の間隔（秒）。バージョン、名前などを取得し、起動時には直ちに 1 回実行します |
| `settings_seconds` | 1800 | `/settings` の間隔（秒）。ワールドルールは変化が遅いため頻繁な取得は不要です |
| `game_data_seconds` | 120 | `/game-data` の間隔（秒）。ギルド、拠点など PalGameDataBridge のワールドデータを取得し、少なくとも 1 個の `guilds_bases` コマンドが実効的に有効な場合だけ実行します |
| `jitter_ratio` | 0.10 | 各 endpoint の要求が同時に揃わないよう加えるランダムな揺らぎ |
| `max_concurrency` | 6 | 実行中 HTTP 要求の全体上限。ゲームサーバーを過剰な並列処理から保護します |

適応型 backpressure により、応答時間が現在の間隔を超えた endpoint は実効間隔を指数的に延長し、
最大で基準値の 8 倍にします。正常な応答が続くと段階的に構成値へ戻るため、手動調整は不要です。

<a id="world"></a>
## world（タイムゾーンと表示）

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `timezone` | `Asia/Tokyo` | `/pal world today` など、すべての時刻表示に使う IANA タイムゾーン。各サーバーの `timezone` で上書きできます |
| `locale` | `zh-CN` | 実行時メッセージの言語：`zh-CN`（簡体字中国語）、`ja`（日本語）、`en`（英語） |
| `fps_smooth` | 50 | この値以上の FPS を「快適」と表示します |
| `fps_moderate` | 35 | この値以上かつ `fps_smooth` 未満を「普通」と表示します |
| `fps_laggy` | 20 | この値以上かつ `fps_moderate` 未満を「重い」と表示し、さらに低い FPS は「非常に重い」と表示します |

<a id="presentation"></a>
## presentation（表示とカード外観）

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `me_card_theme` | `light` | 画像プロフィールカード（`/pal me 卡`）の配色：`light`、`dark`、`auto`。auto は**サーバーのローカル時計**に従い、06:00–18:00 は light、それ以外は dark を使います。加速するゲーム内昼夜ではなく実時間を使います。テキスト版には影響しません |

<a id="bases"></a>
## bases（拠点推定。strict プライバシーでは全体を停止）

拠点は API から直接返されず、採取したプレイヤー位置から推定されます。同じ grid の位置が必要回数
一貫して観測された後に、拠点として確定します。

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `enabled` | true | 拠点と PalBox の推定を有効化。strict プライバシーでは強制的に無効です |
| `assignment_radius` | 5000 | プレイヤーの観測位置を拠点へ割り当てる最大距離。ワールド座標単位です |
| `ambiguity_ratio` | 0.20 | 最短距離と 2 番目の距離の差の比率。これ未満は曖昧として無視します |
| `confirmation_samples` | 3 | 拠点を確定するために必要な一貫した観測回数 |
| `position_grid_size` | 2000 | 保存前に座標を量子化する grid サイズ。正確な位置を公開しない境界を実装します |
| `z_weight` | 0.5 | 距離計算における Z 軸の重み。立体的な地形での誤判定を抑えます |

<a id="history"></a>
## history（保持目標。自動削除は未実装）

| 項目 | 初期値 | 意味 |
| --- | --- | --- |
| `raw_metrics_days` | 7 | 各ポーリングの未加工 metrics を保持する日数 |
| `aggregate_days` | 90 | 事前集計した統計を保持する日数 |
| `session_days` | 365 | プレイヤーのログインセッションを保持する日数 |
| `observation_days` | 180 | ワールド観測を保持する日数 |

> 現行版はこれらの値を読み取って保存しますが、scheduler は期限切れの行をまだ削除しません。
> 運用とコンプライアンスに合わせて AstrBot のデータディレクトリを管理してください。
> これらは自動削除を保証する設定ではありません。

<a id="custom-headers"></a>
## custom_headers（独自 HTTP 要求ヘッダー）

対象となる REST API のポーリング要求に付加します。Cloudflare Access の
`CF-Access-Client-Id` / `CF-Access-Client-Secret` など、リバースプロキシや gateway で追加認証が
必要な場合に使います。設定画面からエントリを追加または削除します。

| フィールド | 初期値 | 意味 |
|------|------|------|
| `name` | 空 | Header 名。例：`CF-Access-Client-Id` |
| `value` | 空 | 平文の Header 値。`value_env` と排他で、`data/config/` に保存されます |
| `value_env` | 空 | 値を格納する環境変数名。gateway の token など秘密値に推奨します |
| `servers` | 空 | Header を送るサーバー名。複数はカンマ区切り。**空の場合は将来追加するものを含む全サーバー**へ送るため、認証情報を含む Header は必ず範囲を限定してください |

注意：

- `Authorization`、`Host`、`Expect`、`Content-Length`、`Transfer-Encoding`、`Connection` は予約済みで
  無視されます。Basic Auth はサーバーエントリの username と password が担当します。
- `value_env` または `password_env` が参照する環境変数を変更したら、AstrBot プロセス全体を
  再起動してください。画面での保存はプラグインだけを hot reload し、環境変数はプロセスに属します。
- 無効で無視されたエントリは起動時に名前と理由だけを warning へ出し、値は記録しません。

<a id="plugin-page"></a>
## プラグイン画面（WebUI の構成と稼働状況）

正式な対応範囲は **AstrBot 4.24.1 以上、5 未満**です。4.24.1 以降ではプラグイン詳細、
4.25.3 以降ではサイドバーの「プラグインページ」から PalWorldTerminal の設定を開けます。
サーバーやアクセス制御を視覚的に編集し、各サーバーの読み取り専用の稼働状況を確認できます。
4.24.1 未満は必要な画面と初回構成の flow を提供できないため、対応対象外です。

- **保存時に即再読み込み：** 構成の検証と保存後、内部 container を再起動します。ポーリングは短時間
  中断し、オンライン時間統計にごく小さな欠落が生じる可能性があります。チャットコマンドは一時的に
  再読み込み中と表示します。
- **秘密フィールド：** パスワードや独自 Header 値は再表示されません。設定済みの印を表示し、
  空の送信は変更なしとして内部の `__unchanged__` を使います。安全のため `base_url` を変更した
  サーバーではパスワードの再入力が必要で、以前の認証情報が新しいアドレスへ送られることを防ぎます。
- **認証：** 画面の要求は AstrBot Dashboard のログイン状態を通じて転送されます。未ログインでは利用できません。

<a id="features"></a>
## features（機能グループ）

> **v0.9.6 以降はコマンドツリー権限が正本です：** 旧 boolean の `features` は削除され、有効状態は
> 3 状態の `command_permissions` 行に保存されます。[権限管理](#permissions)を参照してください。
> コマンドは引き続き下記の機能グループへ分類されます。グループは初期状態と派生データ収集を決めます。
> 変更するには「権限」でコマンドまたはグループに `enabled=on/off` の行を追加します。

機能グループが初期値を提供し、実効値は `command_permissions` で上書きできます。

| 機能グループ | 初期状態 | コマンド | 意味 |
|------|------|------|------|
| `core` | 常に有効 | `world status/rules` `online` `whoami` `whereami` `help` `confirm` 引数なしの `link` 引数なしの `server` | 無効にできない基本コマンド |
| `report` | 有効 | `/pal world today` | 日報とオンライン統計 |
| `events` | 有効 | `/pal world events` | ワールドイベント履歴。無効中はイベントを生成しません |
| `players` | **無効** | `/pal player info` `/pal player bind` `/pal player unbind` `/pal rank` `/pal me` | 個人単位のクエリ。プライバシーのため初期状態は無効です |
| `guilds_bases` | **有効** | `/pal world overview` `/pal guild list` `/pal guild info` `/pal guild bases` `/pal guild base` `/pal dex` | `game-data`（PalGameDataBridge）由来のギルド、拠点、ワールド概要、パル図鑑。安定した game-data 提供に伴い初期状態で有効です |
| `server_admin_basic` | **無効** | `/pal server announce` `/pal server save` `/pal server kick` `/pal server unban` | 基本的な制御付き書き込み。認可済み管理者だけが利用できます。[server_admin](#server-admin)を参照 |
| `server_admin_danger` | **無効** | `/pal server ban` `/pal server shutdown` `/pal server stop` | BAN や停止など危険な制御付き書き込み。再確認を推奨します。[server_admin](#server-admin)を参照 |

無効なコマンドは有効ではないと返し、`/pal help` から消えます。**収集は実効的な有効状態に従います：**
読み取り専用の観測 endpoint（`/info`、`/metrics`、`/players`、`/settings`）はコマンドに関係なく
常にポーリングします。`/game-data` は `guilds_bases` のコマンドが 1 個以上有効な場合だけポーリングし、
`bases.*` と `game_data_seconds` も同じ条件に従います。

**初期状態が有効な `guilds_bases` について：** ギルド、拠点、PalBox、`world overview` は
`/v1/api/game-data`（PalGameDataBridge）から導出します。初期状態が無効な `players` と異なり、
game-data API の安定提供に伴って有効になりました。グループ内のコマンドが有効な間は `/game-data`
をポーリングして `bases.*` の推定項目を適用します。不要ならコマンドツリーで対応項目を無効にしてください。

<a id="server-admin"></a>
## server_admin（サーバー操作）

制御付き書き込みの項目です。すべての書き込みコマンドは初期状態で無効です。`command_permissions`
で対応する `server` コマンドを明示的に有効化します。機能グループは `server_admin_basic` と
`server_admin_danger` で、どちらも初期状態は off です。有効化後も `permission_admins` のメンバー
だけが利用でき、実行段階に到達した操作は監査データベースに記録されます。
[コマンド一覧 · サーバー操作](commands.ja.md#server-admin)も参照してください。

| 項目 | 型 | 初期値 | 意味 |
| --- | --- | --- | --- |
| `require_confirmation` | bool | `false` | 有効にすると `server_admin_danger` のコマンド（`ban`、`shutdown`、`stop`）は最初にプレビューを返し、制限時間内の `/pal confirm` 後に実行します。basic コマンドは再確認しません |
| `confirmation_timeout` | int（秒） | `30` | 再確認の待機時間。範囲は 5–600 で、超過すると保留中の操作を破棄します |
| `audit_retention_days` | int（日） | `180` | 監査記録の保持目標。範囲は 1–3650 です。現行版は期限切れの行をまだ自動削除しません |

**重要なセキュリティ上の注意：**

- **open アクセスの影響範囲：** `routing.access_mode=open` では書き込みがグループ認可に制限されません。
  任意の認可済み管理者が、どのグループやダイレクトメッセージからでも現在の route を通じて
  `stop` や `ban` を実行できます。特に複数グループで共有する bot では open と
  `server_admin_danger` を組み合わせないでください。restricted では、単一サーバー書き込みは
  `single_allowed_groups` の読み取りリストを無視し、複数サーバー書き込みはグループの現在の
  バインドを使います。操作コマンドは一時的な `@server` 上書きを受け付けません。
- **`server stop` による進行喪失：** `/pal server stop` は保存せず強制停止します。先に
  `/pal server save` を実行するか、カウントダウン中に保存できる `/pal server shutdown` を使います。
  そのため danger は初期状態で無効で、`require_confirmation` を推奨します。
- **監査保持と個人情報：** `admin_audit` は `admin_id`、`target_name`、時刻を平文の管理対象情報として
  保存します。対象 user ID は観測側と同じワールド単位の名前空間で hash だけを保存します。
  初期値 180 日は自動適用されないため、データディレクトリを自身で管理してください。
- **管理者の名前解決はプライバシー filter を迂回：** `kick` / `ban` の名前解決は `/players`
  から未加工の user ID を読み、`/pal me hide` と `exclude_names` を迂回します。書き込みには実 ID が
  必要で、運営者はゲーム内でも全オンラインプレイヤーを確認できるため、peer に hidden player の
  存在を公開するものではありません。
