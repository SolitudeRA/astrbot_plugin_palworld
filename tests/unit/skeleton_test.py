from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_palchronicle_package_importable():
    import palchronicle

    assert palchronicle.__version__ == "0.1.0"


def test_metadata_yaml_has_all_top_keys():
    data = yaml.safe_load((REPO_ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    for key in ("name", "display_name", "desc", "version", "author",
                "repo", "astrbot_version", "license"):
        assert key in data, f"missing {key}"
    assert data["name"] == "astrbot_plugin_palword"
    assert data["display_name"] == "PalChronicle · 帕鲁纪事"
    assert data["astrbot_version"] == ">=4.24.1"
    assert data["license"] == "GPL-3.0"


def test_requirements_runtime_only():
    # AstrBot 会把 requirements.txt 整个装给最终用户 → 只留运行时依赖
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for dep in ("aiohttp", "aiosqlite", "tzdata"):
        assert dep in text, f"运行时依赖缺失: {dep}"
    for dev_only in ("pytest", "pyyaml"):
        assert dev_only not in text, f"dev 依赖不应出现在 requirements.txt: {dev_only}"


def test_requirements_dev_extends_runtime():
    # 开发/CI 依赖单独放 requirements-dev.txt，并叠加运行时依赖
    text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "-r requirements.txt" in text
    for dep in ("pyyaml", "pytest", "pytest-asyncio"):
        assert dep in text, f"dev 依赖缺失: {dep}"


def test_fake_clock_fixture_is_deterministic(fake_clock):
    assert fake_clock.now() == 1_700_000_000
    fake_clock.advance(5)
    assert fake_clock.now() == 1_700_000_005
