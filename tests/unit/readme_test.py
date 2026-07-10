from pathlib import Path

README = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")


def test_readme_first_screen_safety_claims():
    for phrase in ("只读", "不控制服务器", "不存储 IP", "不公开精确位置", "启用 REST", "勿暴露公网"):
        assert phrase in README, f"README 缺少安全声明: {phrase}"


def test_readme_requirements_and_usage():
    assert "AstrBot ≥ 4.10.4" in README or "AstrBot >= 4.10.4" in README
    for phrase in ("/pal use", "多服务器", "@server", "群授权", "安装", "配置"):
        assert phrase in README, f"README 缺少用法段落: {phrase}"


def test_readme_lists_readonly_endpoints():
    for ep in ("/info", "/metrics", "/players", "/settings", "/game-data"):
        assert ep in README, f"README 未声明只读端点: {ep}"
