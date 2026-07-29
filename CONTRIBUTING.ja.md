<a id="contributing"></a>
# コントリビューションガイド

[简体中文](CONTRIBUTING.md) | **日本語** | [English](CONTRIBUTING.en.md)

<a id="development"></a>
## 開発環境

- Python 3.11 以上。`pip install -r requirements-dev.txt` でテスト用ツールを含む依存関係をインストールします。
- フロントエンドは Node 20 以上を使用し、`cd frontend && npm ci` を実行します。

<a id="frontend-build"></a>
## フロントエンド変更後の配布アセット再生成

設定画面の成果物は `pages/settings/` にコミットされ、プラグインとともに配布されます。`frontend/src`
を変更した場合は、必ず次を実行してください。

```bash
cd frontend && npm run build
```

更新された `pages/settings/` をソース変更と同じコミットに含めます。`npm run build` は `normalize-eol`
で改行を正規化するため、Windows でも不要な CRLF 差分は発生しません。CI は `verify-bundle`
も実行し、成果物が単一ファイル構成（JS は 1 個、CSS は最大 1 個、dynamic import なし）を維持していることを確認します。
バックエンドのみの変更では、この手順は不要です。

<a id="checks"></a>
## テストとチェック

```bash
# Backend (use the virtual-environment Python on Windows)
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m mypy palworld_terminal/
./.venv/Scripts/lint-imports.exe

# Frontend
cd frontend && npm run test:run && npm run typecheck
```

CI は Linux で静的解析・フロントエンド検査・バックエンドテストを実行し、Windows でもバックエンドテストを
実行します。すべての検査が成功した変更のみマージできます。

<a id="commit-conventions"></a>
## コミット規約

- Conventional Commits（`feat:`、`fix:`、`docs:`、`chore:`）を使用し、説明は中国語で記述します。
- 機能開発はリポジトリの手順に従います。spec（`docs/superpowers/specs/`）→ review → plan →
  implementation → ブランチ全体の最終レビュー → PR の順です。
