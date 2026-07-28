from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import capture_docs_assets, export_docs_cards

ROOT = Path(__file__).resolve().parents[2]


def test_card_exporter_uses_real_production_builder(monkeypatch, tmp_path):
    calls = []

    def fake_builder(dto, icons, theme):
        calls.append((dto, icons, theme))
        return f'<div data-theme="{theme}">REAL-BUILDER</div>'

    monkeypatch.setattr(export_docs_cards, "build_me_card_html", fake_builder)
    monkeypatch.setattr(export_docs_cards, "_load_icons", lambda: {"neutral": "<svg/>"})
    jobs = export_docs_cards.prepare_card_jobs(tmp_path / "html", tmp_path / "images")

    assert len(jobs) == 6
    assert [job["output"] for job in jobs] == [
        "me-card-light.png",
        "me-card-dark.png",
        "ja/me-card-light.png",
        "ja/me-card-dark.png",
        "en/me-card-light.png",
        "en/me-card-dark.png",
    ]
    assert len(calls) == 6
    assert {theme for _, _, theme in calls} == {"light", "dark"}
    assert all(dto is export_docs_cards.DEMO_CARD for dto, _, _ in calls)
    assert all("REAL-BUILDER" in Path(job["htmlPath"]).read_text(encoding="utf-8") for job in jobs)


def test_real_card_html_has_locked_native_scale():
    html = export_docs_cards.render_card_html("en", "dark")
    flat = html.replace(" ", "")
    assert 'data-theme="dark"' in html
    assert "Ahead of recorded players" in html
    assert "zoom:2" in flat
    assert "width:max-content" in flat


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr=stderr)


def test_source_commit_requires_existing_head_ancestor_and_clean_source():
    sha = "a" * 40
    responses = {
        ("rev-parse", "--verify", f"{sha}^{{commit}}"): _completed(stdout=f"{sha}\n"),
        ("merge-base", "--is-ancestor", sha, "HEAD"): _completed(),
        ("diff", "--name-only", f"{sha}..HEAD"): _completed(stdout="docs/images/en/me-card-light.png\n"),
        ("status", "--porcelain=v1", "--untracked-files=all"): _completed(
            stdout=" M docs/images/screenshots.manifest.json\n"
        ),
    }
    assert capture_docs_assets.validate_source_commit(
        ROOT, sha, run_git=lambda args: responses[tuple(args)]
    ) == sha


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {("merge-base", "--is-ancestor", "a" * 40, "HEAD"): _completed(returncode=1)},
            "not an ancestor",
        ),
        (
            {("diff", "--name-only", f"{'a' * 40}..HEAD"): _completed(stdout="README.md\n")},
            "changed after source commit",
        ),
        (
            {
                ("status", "--porcelain=v1", "--untracked-files=all"): _completed(
                    stdout=" M scripts/capture_docs_assets.py\n"
                )
            },
            "worktree is dirty",
        ),
    ],
)
def test_source_commit_rejects_invalid_or_dirty_source(overrides, message):
    sha = "a" * 40
    responses = {
        ("rev-parse", "--verify", f"{sha}^{{commit}}"): _completed(stdout=f"{sha}\n"),
        ("merge-base", "--is-ancestor", sha, "HEAD"): _completed(),
        ("diff", "--name-only", f"{sha}..HEAD"): _completed(),
        ("status", "--porcelain=v1", "--untracked-files=all"): _completed(),
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        capture_docs_assets.validate_source_commit(ROOT, sha, run_git=lambda args: responses[tuple(args)])


def test_manifest_has_single_source_commit_hashes_dimensions_and_scale():
    manifest_path = ROOT / "docs" / "images" / "screenshots.manifest.json"
    if not manifest_path.exists():
        pytest.skip("formal Phase 3 assets are generated in Task 8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sha = manifest["source_commit"]
    # source_commit 的存在性、祖先关系与 clean source 在生成入口中强制，并由上面的 fake-git
    # 单测覆盖。仓库使用 squash merge；合并后的全新 checkout 不保证仍下载 PR 分支 commit
    # 对象，因此永久 CI 不应尝试 cat-file/merge-base 解引用它。
    assert len(sha) == 40 and all(char in "0123456789abcdef" for char in sha)
    assert len(manifest["images"]) == 18
    assert {item["source_commit"] for item in manifest["images"]} == {sha}
    for item in manifest["images"]:
        if item["kind"] == "settings":
            assert item["dpr"] == 2 and item["zoom"] == 1
        else:
            assert item["width"] == 1008
            assert item["dpr"] == 1 and item["renderer_scale"] == item["zoom"] == 2
