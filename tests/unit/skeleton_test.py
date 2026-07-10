from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_palchronicle_package_importable():
    import palchronicle

    assert palchronicle.__version__ == "0.1.0"


def test_metadata_yaml_has_all_top_keys():
    data = yaml.safe_load((REPO_ROOT / "metadata.yaml").read_text(encoding="utf-8"))
    for key in ("name", "display_name", "desc", "version", "author", "repo", "astrbot_version"):
        assert key in data, f"missing {key}"
    assert data["name"] == "astrbot_plugin_palword"
    assert data["display_name"] == "PalChronicle · 帕鲁纪事"
    assert data["astrbot_version"] == ">=4.10.4"


def test_requirements_lists_runtime_and_dev_deps():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "aiohttp" in text
    assert "aiosqlite" in text
    assert "pytest" in text
    assert "pytest-asyncio" in text


def test_fake_clock_fixture_is_deterministic(fake_clock):
    assert fake_clock.now() == 1_700_000_000
    fake_clock.advance(5)
    assert fake_clock.now() == 1_700_000_005
