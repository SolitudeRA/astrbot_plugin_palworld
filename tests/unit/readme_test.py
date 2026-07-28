from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_keeps_first_screen_safety_claims():
    for phrase in (
        "受控写",
        "仅授权管理员",
        "审计",
        "不存储 IP",
        "不公开精确位置",
        "启用 REST",
        "勿暴露公网",
    ):
        assert phrase in README, f"README 缺少安全声明: {phrase}"


def test_readme_links_to_core_docs():
    for link in ("docs/configuration.md", "docs/commands.md"):
        assert link in README, f"README 缺少子文档链接: {link}"
