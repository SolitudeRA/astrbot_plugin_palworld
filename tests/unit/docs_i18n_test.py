"""三语用户文档与 README 正式图片的结构契约。

只使用显式 manifest；不得用 glob 把 docs/superpowers 内部设计史纳入。
Markdown 提取器只覆盖本仓库需要的结构，并显式处理 fenced code、inline code 与 escaped pipe。
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOCALES = ("zh-CN", "ja", "en")
ANCHOR_RE = re.compile(r'^<a id="([a-z0-9][a-z0-9-]*)"></a>$')
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})([^`]*)$")
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)\s]+)(?:\s+['\"][^)]*['\"])?\)")
HTML_SRC_RE = re.compile(r'<(?:img|a)\b[^>]*(?:src|href)="([^"]+)"', re.IGNORECASE)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*}")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class DocFamily:
    key: str
    paths: dict[str, str]
    headings: tuple[tuple[int, str], ...]


DOC_FAMILIES = (
    DocFamily(
        "readme",
        {"zh-CN": "README.md", "ja": "README.ja.md", "en": "README.en.md"},
        (
            (1, "readme"),
            (2, "actual-ui"),
            (3, "settings-dashboard"),
            (3, "features-and-permissions"),
            (3, "single-and-multi-world"),
            (2, "chat-examples"),
            (2, "capabilities"),
            (2, "quick-start"),
            (3, "requirements"),
            (3, "enable-rest-api"),
            (3, "install-plugin"),
            (3, "configure-servers"),
            (3, "authorize-admins"),
            (3, "verify-installation"),
            (2, "common-commands"),
            (2, "security-boundaries"),
            (2, "faq"),
            (2, "docs-and-contributing"),
            (2, "license"),
        ),
    ),
    DocFamily(
        "contributing",
        {
            "zh-CN": "CONTRIBUTING.md",
            "ja": "CONTRIBUTING.ja.md",
            "en": "CONTRIBUTING.en.md",
        },
        (
            (1, "contributing"),
            (2, "development"),
            (2, "frontend-build"),
            (2, "checks"),
            (2, "commit-conventions"),
        ),
    ),
    DocFamily(
        "configuration",
        {
            "zh-CN": "docs/configuration.md",
            "ja": "docs/configuration.ja.md",
            "en": "docs/configuration.en.md",
        },
        (
            (1, "configuration"),
            (2, "servers"),
            (2, "routing"),
            (3, "single-allowed-groups"),
            (3, "mode-transfer"),
            (2, "permissions"),
            (3, "command-tree-permissions"),
            (3, "legacy-permission-migration"),
            (2, "polling"),
            (2, "world"),
            (2, "presentation"),
            (2, "bases"),
            (2, "history"),
            (2, "custom-headers"),
            (2, "plugin-page"),
            (2, "features"),
            (2, "server-admin"),
        ),
    ),
    DocFamily(
        "commands",
        {"zh-CN": "docs/commands.md", "ja": "docs/commands.ja.md", "en": "docs/commands.en.md"},
        (
            (1, "commands"),
            (2, "first-setup"),
            (2, "command-reference"),
            (3, "world-commands"),
            (3, "guild-commands"),
            (3, "player-commands"),
            (3, "flat-commands"),
            (3, "server-commands"),
            (3, "link-commands"),
            (2, "feature-matrix"),
            (2, "world-modes"),
            (3, "single-world-access"),
            (3, "mode-transfer"),
            (3, "orphan-cleanup"),
            (2, "multi-world-routing"),
            (2, "permissions"),
            (3, "legacy-permission-migration"),
            (2, "server-admin"),
            (3, "three-layer-safety"),
            (3, "confirmation"),
            (3, "target-player-resolution"),
            (3, "audit"),
            (3, "security-notice"),
            (2, "degraded-behavior"),
        ),
    ),
)

FAMILY_BY_PATH = {
    path: (family, locale)
    for family in DOC_FAMILIES
    for locale, path in family.paths.items()
}

# 必需 token 按文档族/稳定章节守卫，禁止跨文件或跨章节抵消遗漏。
REQUIRED_TOKENS: dict[str, dict[str, tuple[str, ...]]] = {
    "readme": {
        "requirements": ("AstrBot", "Palworld REST API", "Python 3.11"),
        "enable-rest-api": ("RESTAPIEnabled=True", "RESTAPIPort=8212"),
        "common-commands": (
            "/pal world status",
            "/pal guild base",
            "/pal rank",
            "/pal me",
            "/pal dex",
            "/pal server announce",
        ),
        "security-boundaries": ("permission_admins", "server_admin_basic", "server_admin_danger"),
    },
    "contributing": {
        "development": ("pip install -r requirements-dev.txt", "npm ci"),
        "frontend-build": ("npm run build", "pages/settings"),
        "checks": ("pytest", "ruff check .", "mypy palworld_terminal", "lint-imports"),
        "commit-conventions": ("Conventional Commits",),
    },
    "configuration": {
        "servers": ("base_url", "password_env", "verify_tls", "timezone"),
        "routing": ("access_mode", "world_mode", "default_server", "setup_confirmed"),
        "permissions": ("permission_admins", "command_permissions"),
        "polling": ("poll_seconds", "timeout", "collect_timeout"),
        "world": ("locale", "fps_smooth", "fps_moderate", "fps_laggy"),
        "presentation": ("me_card_theme",),
        "custom-headers": ("custom_headers", "value_env"),
        "server-admin": (
            "confirm_dangerous",
            "confirm_ttl_seconds",
            "server_admin_basic",
            "server_admin_danger",
        ),
    },
    "commands": {
        "world-commands": ("/pal world status", "/pal world overview", "/pal world info"),
        "guild-commands": ("/pal guild list", "/pal guild info", "/pal guild base"),
        "player-commands": ("/pal player list", "/pal player info", "/pal player bind"),
        "flat-commands": (
            "/pal rank",
            "/pal online",
            "/pal me",
            "/pal dex",
            "/pal help",
            "/pal whoami",
            "/pal whereami",
            "/pal confirm",
        ),
        "server-admin": (
            "/pal server announce",
            "/pal server save",
            "/pal server kick",
            "/pal server unban",
            "/pal server ban",
            "/pal server shutdown",
            "/pal server stop",
        ),
        "degraded-behavior": ("cache_stale", "world_not_ready", "game_data_unavailable"),
    },
}

SCREENSHOT_NAMES = (
    "settings-servers.png",
    "settings-features.png",
    "settings-permissions.png",
    "settings-onboarding.png",
    "me-card-light.png",
    "me-card-dark.png",
)
EXPECTED_SETTING_SIZE = {
    "settings-servers.png": (2200, 1920),
    "settings-features.png": (2200, 1920),
    "settings-permissions.png": (2200, 1920),
    "settings-onboarding.png": (2200, 1200),
}
EN_PROSE_HAN_ALLOWLIST = {"卡", "图", "帕鲁世界终端"}
JA_FORBIDDEN_PHRASES = (
    "默认关闭",
    "设置页",
    "服务器管控",
    "仅管理员",
    "未开启",
    "首次设置",
    "多世界模式",
    "单世界模式",
    "配置项",
    "功能开关",
    "玩家档案",
    "随身帕鲁",
    "安全告知",
    "明文落盘",
)


def _read_utf8_lf(path: Path) -> str:
    assert path.is_file(), f"missing document: {path.relative_to(ROOT)}"
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.relative_to(ROOT)} must not contain UTF-8 BOM"
    assert b"\r" not in raw, f"{path.relative_to(ROOT)} must use LF only"
    return raw.decode("utf-8", errors="strict")


def _without_fences(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    fence_char = ""
    fence_len = 0
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if not fence_char:
                fence_char, fence_len = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char, fence_len = "", 0
            continue
        if not fence_char:
            out.append((number, line))
    assert not fence_char, "unclosed fenced code block"
    return out


def _heading_contract(text: str) -> tuple[tuple[int, str], ...]:
    lines = _without_fences(text)
    headings: list[tuple[int, str]] = []
    seen: set[str] = set()
    pending_anchor: tuple[int, str] | None = None
    for number, line in lines:
        stripped = line.strip()
        anchor = ANCHOR_RE.fullmatch(stripped)
        if anchor:
            assert pending_anchor is None, f"line {number}: anchor must be followed by exactly one heading"
            stable_id = anchor.group(1)
            assert stable_id not in seen, f"line {number}: duplicate anchor {stable_id}"
            pending_anchor = (number, stable_id)
            seen.add(stable_id)
            continue
        heading = HEADING_RE.match(stripped)
        if heading:
            assert pending_anchor is not None, f"line {number}: heading lacks adjacent stable anchor"
            anchor_line, stable_id = pending_anchor
            assert number == anchor_line + 1, f"line {number}: anchor {stable_id} is not adjacent to heading"
            headings.append((len(heading.group(1)), stable_id))
            pending_anchor = None
            continue
        if stripped and pending_anchor is not None:
            anchor_line, stable_id = pending_anchor
            raise AssertionError(f"line {anchor_line}: anchor {stable_id} is not followed by a heading")
    assert pending_anchor is None, "file ends with an orphan anchor"
    return tuple(headings)


def _fence_languages(text: str) -> tuple[str, ...]:
    languages: list[str] = []
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if not match:
            continue
        marker, info = match.group(1), match.group(2).strip()
        if not fence_char:
            fence_char, fence_len = marker[0], len(marker)
            languages.append(info.split(maxsplit=1)[0] if info else "")
        elif marker[0] == fence_char and len(marker) >= fence_len:
            fence_char, fence_len = "", 0
    assert not fence_char, "unclosed fenced code block"
    return tuple(languages)


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|") and not stripped.endswith(r"\|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    buf: list[str] = []
    escaped = False
    in_code = False
    for char in stripped:
        if escaped:
            buf.append(char)
            escaped = False
            continue
        if char == "\\":
            buf.append(char)
            escaped = True
            continue
        if char == "`":
            in_code = not in_code
            buf.append(char)
            continue
        if char == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    cells.append("".join(buf).strip())
    return cells


def _is_table_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _technical_first_cell(cell: str) -> str | None:
    code = re.search(r"`([^`]+)`", cell)
    if code:
        return code.group(1).replace(r"\|", "|")
    command = re.search(r"/pal(?:\s+[a-z]+){1,3}", cell)
    return command.group(0) if command else None


def _table_contract(text: str) -> tuple[tuple[str, int, int, tuple[str, ...]], ...]:
    lines = _without_fences(text)
    current_section = ""
    tables: list[tuple[str, int, int, tuple[str, ...]]] = []
    index = 0
    while index < len(lines):
        _, line = lines[index]
        anchor = ANCHOR_RE.fullmatch(line.strip())
        if anchor:
            current_section = anchor.group(1)
        if index + 1 >= len(lines) or "|" not in line:
            index += 1
            continue
        header = _split_table_row(line)
        separator = _split_table_row(lines[index + 1][1])
        if len(header) < 2 or len(separator) != len(header) or not _is_table_separator(separator):
            index += 1
            continue
        data_rows: list[list[str]] = []
        index += 2
        while index < len(lines) and "|" in lines[index][1]:
            row = _split_table_row(lines[index][1])
            if len(row) != len(header):
                break
            data_rows.append(row)
            index += 1
        keys = tuple(key for row in data_rows if (key := _technical_first_cell(row[0])) is not None)
        tables.append((current_section, len(header), len(data_rows), keys))
    return tuple(tables)


def _section_text(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for _, line in _without_fences(text):
        anchor = ANCHOR_RE.fullmatch(line.strip())
        if anchor:
            current = anchor.group(1)
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {key: "\n".join(lines) for key, lines in sections.items()}


def _expected_nav(family: DocFamily, locale: str) -> str:
    def target(target_locale: str) -> str:
        # 同一文档族的三个文件始终位于同一目录。
        return Path(family.paths[target_locale]).name

    zh = "**简体中文**" if locale == "zh-CN" else f"[简体中文]({target('zh-CN')})"
    ja = "**日本語**" if locale == "ja" else f"[日本語]({target('ja')})"
    en = "**English**" if locale == "en" else f"[English]({target('en')})"
    return f"{zh} | {ja} | {en}"


def _relative_targets(text: str) -> list[str]:
    targets = MARKDOWN_LINK_RE.findall(text)
    targets.extend(HTML_SRC_RE.findall(text))
    return [
        target.strip("<>")
        for target in targets
        if not re.match(r"^(?:https?://|mailto:|data:)", target, re.IGNORECASE)
    ]


def _prose(text: str) -> str:
    lines: list[str] = []
    for _, line in _without_fences(text):
        stripped = line.strip()
        if ANCHOR_RE.fullmatch(stripped) or HEADING_RE.match(stripped):
            line = HEADING_RE.sub(lambda match: match.group(2), line)
        if all(label in line for label in ("简体中文", "日本語", "English")):
            continue
        line = INLINE_CODE_RE.sub("", line)
        lines.append(line)
    return "\n".join(lines)


def _png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    assert raw.startswith(PNG_SIGNATURE), f"{path.relative_to(ROOT)} is not a PNG"
    assert raw[12:16] == b"IHDR", f"{path.relative_to(ROOT)} lacks IHDR"
    return struct.unpack(">II", raw[16:24])


@pytest.mark.parametrize(
    ("family", "locale", "relative"),
    [
        (family, locale, relative)
        for family in DOC_FAMILIES
        for locale, relative in family.paths.items()
    ],
)
def test_user_docs_exist_utf8_lf(family: DocFamily, locale: str, relative: str):
    path = ROOT / relative
    assert path.is_file(), f"{family.key}/{locale} missing: {relative}"
    _read_utf8_lf(path)


@pytest.mark.parametrize("family", DOC_FAMILIES, ids=lambda family: family.key)
def test_navigation_heading_structure_fences_and_tables_are_parallel(family: DocFamily):
    texts = {
        locale: _read_utf8_lf(ROOT / relative)
        for locale, relative in family.paths.items()
    }
    for locale, text in texts.items():
        nav = _expected_nav(family, locale)
        assert text.count(nav) == 1, f"{family.key}/{locale} must contain exactly one canonical nav: {nav}"
        assert _heading_contract(text) == family.headings, f"{family.key}/{locale} heading/anchor contract drift"
    zh_fences = _fence_languages(texts["zh-CN"])
    zh_tables = _table_contract(texts["zh-CN"])
    for locale in ("ja", "en"):
        assert _fence_languages(texts[locale]) == zh_fences, f"{family.key}/{locale} fence sequence drift"
        assert _table_contract(texts[locale]) == zh_tables, f"{family.key}/{locale} table structure/key drift"


@pytest.mark.parametrize(
    ("family", "locale", "relative"),
    [
        (family, locale, relative)
        for family in DOC_FAMILIES
        for locale, relative in family.paths.items()
    ],
)
def test_relative_links_exist_and_fragments_hit_stable_ids(family: DocFamily, locale: str, relative: str):
    path = ROOT / relative
    text = _read_utf8_lf(path)
    expected_nav_targets = {
        Path(target).name for target_locale, target in family.paths.items() if target_locale != locale
    }
    for raw_target in _relative_targets(text):
        target, _, fragment = raw_target.partition("#")
        if not target:
            target_path = path
        else:
            target_path = (path.parent / unquote(target)).resolve()
            assert target_path.is_relative_to(ROOT), f"{relative}: relative link escapes repository: {raw_target}"
            assert target_path.is_file(), f"{relative}: missing relative target: {raw_target}"
        if fragment:
            target_text = _read_utf8_lf(target_path)
            anchors = {stable_id for _, stable_id in _heading_contract(target_text)}
            assert unquote(fragment) in anchors, f"{relative}: missing stable fragment: {raw_target}"
        if locale in {"ja", "en"} and target.endswith(".md") and target not in expected_nav_targets:
            target_relative = target_path.relative_to(ROOT).as_posix()
            target_meta = FAMILY_BY_PATH.get(target_relative)
            if target_meta:
                _, target_locale = target_meta
                assert target_locale == locale, f"{relative}: body link falls into {target_locale}: {raw_target}"


@pytest.mark.parametrize("family", DOC_FAMILIES, ids=lambda family: family.key)
def test_required_technical_tokens_stay_in_the_same_family_and_section(family: DocFamily):
    required = REQUIRED_TOKENS.get(family.key, {})
    for locale, relative in family.paths.items():
        sections = _section_text(_read_utf8_lf(ROOT / relative))
        for stable_id, tokens in required.items():
            assert stable_id in sections, f"{family.key}/{locale}: missing section {stable_id}"
            for token in tokens:
                assert token in sections[stable_id], (
                    f"{family.key}/{locale}/{stable_id}: missing technical token {token!r}"
                )


def test_english_and_japanese_have_no_translation_residue():
    for family in DOC_FAMILIES:
        en_text = _prose(_read_utf8_lf(ROOT / family.paths["en"]))
        unexpected_han = sorted({match for match in HAN_RE.findall(en_text) if match not in EN_PROSE_HAN_ALLOWLIST})
        assert not unexpected_han, f"{family.key}/en unexpected CJK prose: {unexpected_han}"

        ja_text = _prose(_read_utf8_lf(ROOT / family.paths["ja"]))
        leaked = [phrase for phrase in JA_FORBIDDEN_PHRASES if phrase in ja_text]
        assert not leaked, f"{family.key}/ja simplified-Chinese residue: {leaked}"

        for locale, relative in family.paths.items():
            prose = _prose(_read_utf8_lf(ROOT / relative))
            authoring_residue = [token for token in ("TODO", "TBD", "待翻译") if token in prose]
            assert not authoring_residue, f"{family.key}/{locale} authoring residue: {authoring_residue}"
            assert not PLACEHOLDER_RE.search(prose), f"{family.key}/{locale} unresolved prose placeholder"


def test_readmes_use_only_their_locale_screenshots():
    for family in DOC_FAMILIES:
        if family.key != "readme":
            continue
        for locale, relative in family.paths.items():
            text = _read_utf8_lf(ROOT / relative)
            prefix = "docs/images" if locale == "zh-CN" else f"docs/images/{locale}"
            expected = {f"{prefix}/{name}" for name in SCREENSHOT_NAMES}
            actual = {
                target.removeprefix("./")
                for target in _relative_targets(text)
                if target.lower().endswith(".png") and "banner.png" not in target and "logo.png" not in target
            }
            assert actual == expected, f"README/{locale} screenshot mapping drift"


def test_screenshot_manifest_hashes_dimensions_and_source_commit():
    manifest_path = ROOT / "docs/images/screenshots.manifest.json"
    assert manifest_path.is_file(), "missing docs/images/screenshots.manifest.json"
    manifest = json.loads(_read_utf8_lf(manifest_path))
    assert manifest.get("schema_version") == 1
    source_commit = manifest.get("source_commit")
    assert isinstance(source_commit, str) and re.fullmatch(r"[0-9a-f]{40}", source_commit)
    images = manifest.get("images")
    assert isinstance(images, list) and len(images) == 18
    assert {item.get("source_commit", source_commit) for item in images} == {source_commit}

    expected_paths = {
        f"docs/images/{'' if locale == 'zh-CN' else locale + '/'}{name}"
        for locale in LOCALES
        for name in SCREENSHOT_NAMES
    }
    actual_paths = {item.get("path") for item in images}
    assert actual_paths == expected_paths

    for item in images:
        relative = item["path"]
        path = ROOT / relative
        assert path.is_file(), f"manifest image missing: {relative}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert item.get("sha256") == digest, f"manifest SHA-256 drift: {relative}"
        size = _png_size(path)
        assert item.get("width") == size[0] and item.get("height") == size[1]
        name = path.name
        if name in EXPECTED_SETTING_SIZE:
            assert size == EXPECTED_SETTING_SIZE[name], f"settings screenshot size drift: {relative}"
            assert item.get("dpr") == 2 and item.get("zoom") == 1
        else:
            assert size[0] == 1008, f"card width drift: {relative}"
            assert item.get("renderer_scale") == 2
