"""Generate and atomically install all 18 localized README screenshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "docs" / "images"
SETTINGS_RENDERER = ROOT / "frontend" / "scripts" / "capture-docs-screenshots.mjs"
CARD_EXPORTER = ROOT / "scripts" / "export_docs_cards.py"
VITE_ENTRY = ROOT / "frontend" / "node_modules" / "vite" / "bin" / "vite.js"
VITE_PACKAGE = ROOT / "frontend" / "node_modules" / "vite" / "package.json"
LOCALES = ("zh-CN", "ja", "en")
SETTING_NAMES = (
    "settings-servers.png",
    "settings-features.png",
    "settings-permissions.png",
    "settings-onboarding.png",
)
CARD_NAMES = ("me-card-light.png", "me-card-dark.png")
MANIFEST_NAME = "screenshots.manifest.json"
CAPTURE_PORT = 4173
EXPECTED_SETTING_SIZE = {
    "settings-servers.png": (2200, 1920),
    "settings-features.png": (2200, 1920),
    "settings-permissions.png": (2200, 1920),
    "settings-onboarding.png": (2200, 1200),
}

RunGit = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run_git(repo: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _is_generated_path(relative: str) -> bool:
    normalized = relative.replace("\\", "/").strip('"')
    return normalized == "docs/images" or normalized.startswith("docs/images/")


def validate_source_commit(
    repo: Path,
    source_commit: str,
    *,
    run_git: RunGit | None = None,
) -> str:
    """Require an existing HEAD ancestor with no source drift outside generated assets."""
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be a full lowercase 40-character SHA")
    runner = run_git or (lambda args: _run_git(repo, args))

    resolved = runner(["rev-parse", "--verify", f"{source_commit}^{{commit}}"])
    if resolved.returncode != 0 or resolved.stdout.strip() != source_commit:
        raise ValueError(f"source commit does not exist: {source_commit}")
    ancestor = runner(["merge-base", "--is-ancestor", source_commit, "HEAD"])
    if ancestor.returncode != 0:
        raise ValueError(f"source commit is not an ancestor of HEAD: {source_commit}")

    committed = runner(["diff", "--name-only", f"{source_commit}..HEAD"])
    if committed.returncode != 0:
        raise RuntimeError(committed.stderr.strip() or "git diff failed")
    committed_source = [line for line in committed.stdout.splitlines() if line and not _is_generated_path(line)]
    if committed_source:
        raise ValueError(f"source files changed after source commit: {', '.join(committed_source)}")

    status = runner(["status", "--porcelain=v1", "--untracked-files=all"])
    if status.returncode != 0:
        raise RuntimeError(status.stderr.strip() or "git status failed")
    dirty_source: list[str] = []
    for line in status.stdout.splitlines():
        if not line:
            continue
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        if not _is_generated_path(relative):
            dirty_source.append(relative)
    if dirty_source:
        raise ValueError(f"source worktree is dirty: {', '.join(dirty_source)}")
    return source_commit


def _run_json(command: Sequence[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _wait_for_vite(process: subprocess.Popen[str], base_url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Vite exited before becoming ready (exit {process.returncode})")
        try:
            with urllib.request.urlopen(f"{base_url}/dev.html", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise TimeoutError(f"Vite did not become ready at {base_url}")


def _stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return int.from_bytes(payload[16:20], "big"), int.from_bytes(payload[20:24], "big")


def _asset_relative(locale: str, name: str) -> Path:
    return Path(name) if locale == "zh-CN" else Path(locale) / name


def _manifest_entry(
    staging: Path,
    relative: Path,
    *,
    source_commit: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    path = staging / relative
    width, height = _png_dimensions(path)
    return {
        "path": (Path("docs/images") / relative).as_posix(),
        "source_commit": source_commit,
        **metadata,
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def build_manifest(
    staging: Path,
    source_commit: str,
    settings_result: dict[str, Any],
    cards_result: dict[str, Any],
) -> dict[str, Any]:
    """Create the schema-v1 manifest and reject incomplete or inconsistent capture results."""
    setting_rows = settings_result.get("captures", [])
    card_rows = cards_result.get("captures", [])
    setting_captures = {item["output"]: item for item in setting_rows}
    card_captures = {item["output"]: item for item in card_rows}
    if len(setting_rows) != 12 or len(setting_captures) != 12:
        raise ValueError("settings renderer must return exactly 12 unique captures")
    if len(card_rows) != 6 or len(card_captures) != 6:
        raise ValueError("card renderer must return exactly 6 unique captures")
    entries: list[dict[str, Any]] = []
    for locale in LOCALES:
        for name in SETTING_NAMES:
            relative = _asset_relative(locale, name)
            output = relative.as_posix()
            capture = setting_captures.get(output)
            if capture is None:
                raise ValueError(f"missing settings capture metadata: {output}")
            entry = _manifest_entry(
                staging,
                relative,
                source_commit=source_commit,
                metadata={
                    "kind": "settings",
                    "locale": locale,
                    "scenario": capture["scenario"],
                    "chapter": capture["chapter"],
                    "theme": capture["theme"],
                    "viewport": capture["viewport"],
                    "dpr": capture["deviceScaleFactor"],
                    "zoom": 1,
                },
            )
            if (entry["width"], entry["height"]) != EXPECTED_SETTING_SIZE[name]:
                raise ValueError(f"unexpected settings dimensions: {output}")
            entries.append(entry)
        for name in CARD_NAMES:
            relative = _asset_relative(locale, name)
            output = relative.as_posix()
            capture = card_captures.get(output)
            if capture is None:
                raise ValueError(f"missing card capture metadata: {output}")
            entry = _manifest_entry(
                staging,
                relative,
                source_commit=source_commit,
                metadata={
                    "kind": "card",
                    "locale": locale,
                    "theme": capture["theme"],
                    "viewport": capture["viewport"],
                    "dpr": capture["deviceScaleFactor"],
                    "zoom": capture["rendererScale"],
                    "renderer_scale": capture["rendererScale"],
                },
            )
            if entry["width"] != 1008:
                raise ValueError(f"unexpected card width: {output}")
            entries.append(entry)

    paths = [item["path"] for item in entries]
    if len(entries) != 18 or len(set(paths)) != 18:
        raise ValueError("manifest must contain exactly 18 unique image paths")
    staged_paths = {path.relative_to(staging).as_posix() for path in staging.rglob("*.png")}
    expected_staged = {Path(path).relative_to("docs/images").as_posix() for path in paths}
    if staged_paths != expected_staged:
        raise ValueError("staging directory does not contain exactly the 18 managed images")
    playwright_versions = {settings_result.get("playwrightVersion"), cards_result.get("playwrightVersion")}
    chromium_versions = {settings_result.get("chromiumVersion"), cards_result.get("chromiumVersion")}
    if None in playwright_versions or len(playwright_versions) != 1:
        raise ValueError("settings and card renderers used different Playwright versions")
    if None in chromium_versions or len(chromium_versions) != 1:
        raise ValueError("settings and card renderers used different Chromium versions")
    vite_version = json.loads(VITE_PACKAGE.read_text(encoding="utf-8"))["version"]
    return {
        "schema_version": 1,
        "source_commit": source_commit,
        "tools": {
            "python": platform.python_version(),
            "vite": vite_version,
            "playwright": playwright_versions.pop(),
            "chromium": chromium_versions.pop(),
        },
        "images": entries,
    }


def _install_atomically(staging: Path, manifest: dict[str, Any]) -> None:
    docs_dir = IMAGES_DIR.parent
    replacement = docs_dir / f".images-next-{uuid.uuid4()}"
    backup = docs_dir / f".images-backup-{uuid.uuid4()}"
    try:
        shutil.copytree(IMAGES_DIR, replacement)
        for locale in LOCALES:
            for name in (*SETTING_NAMES, *CARD_NAMES):
                relative = _asset_relative(locale, name)
                destination = replacement / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(staging / relative, destination)
        (replacement / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        os.replace(IMAGES_DIR, backup)
        try:
            os.replace(replacement, IMAGES_DIR)
        except Exception:
            os.replace(backup, IMAGES_DIR)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    finally:
        if replacement.exists():
            shutil.rmtree(replacement, ignore_errors=True)
        if backup.exists() and not IMAGES_DIR.exists():
            os.replace(backup, IMAGES_DIR)


def capture_all(source_commit: str, *, node: str = "node") -> dict[str, Any]:
    validate_source_commit(ROOT, source_commit)
    if not VITE_ENTRY.is_file():
        raise FileNotFoundError("frontend dependencies are missing; run npm ci in frontend")

    with tempfile.TemporaryDirectory(prefix="palword-docs-assets-") as temp:
        temp_dir = Path(temp)
        staging = temp_dir / "staging"
        settings_dir = temp_dir / "settings"
        cards_dir = temp_dir / "cards"
        staging.mkdir()
        vite_log = (temp_dir / "vite.log").open("w", encoding="utf-8")
        vite = subprocess.Popen(
            [
                node,
                str(VITE_ENTRY),
                "--host",
                "127.0.0.1",
                "--port",
                str(CAPTURE_PORT),
                "--strictPort",
            ],
            cwd=ROOT / "frontend",
            stdout=vite_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        base_url = f"http://127.0.0.1:{CAPTURE_PORT}"
        try:
            _wait_for_vite(vite, base_url)
            settings_result = _run_json(
                [
                    node,
                    str(SETTINGS_RENDERER),
                    "--output-dir",
                    str(settings_dir),
                    "--base-url",
                    base_url,
                ],
                cwd=ROOT,
            )
        finally:
            _stop_process_tree(vite)
            vite_log.close()

        cards_result = _run_json(
            [sys.executable, str(CARD_EXPORTER), "--output-dir", str(cards_dir), "--node", node],
            cwd=ROOT,
        )
        for source in (settings_dir, cards_dir):
            for path in source.rglob("*.png"):
                relative = path.relative_to(source)
                destination = staging / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
        manifest = build_manifest(staging, source_commit, settings_result, cards_result)
        _install_atomically(staging, manifest)
        return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--node", default="node")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = capture_all(args.source_commit, node=args.node)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
