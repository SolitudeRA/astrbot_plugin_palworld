from pathlib import Path

README = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")


def test_readme_first_screen_safety_claims():
    for phrase in ("只读", "不控制服务器", "不存储 IP", "不公开精确位置", "启用 REST", "勿暴露公网"):
        assert phrase in README, f"README 缺少安全声明: {phrase}"


def test_readme_requirements_and_usage():
    assert "AstrBot ≥ 4.24.1" in README or "AstrBot >= 4.24.1" in README
    for phrase in ("/pal use", "多服务器", "@server", "群授权", "安装", "配置"):
        assert phrase in README, f"README 缺少用法段落: {phrase}"


def test_readme_lists_readonly_endpoints():
    for ep in ("/info", "/metrics", "/players", "/settings", "/game-data"):
        assert ep in README, f"README 未声明只读端点: {ep}"


def test_readme_install_splits_runtime_and_dev_deps():
    # 安装节：运行时三件套 + 开发者另装 requirements-dev.txt
    for phrase in ("aiohttp", "aiosqlite", "tzdata", "requirements-dev.txt"):
        assert phrase in README, f"README 安装说明缺少: {phrase}"


def test_readme_documents_polling_section():
    for phrase in ("metrics_seconds", "players_seconds", "info_seconds",
                   "settings_seconds", "game_data_seconds",
                   "jitter_ratio", "max_concurrency", "背压"):
        assert phrase in README, f"README polling 配置文档缺少: {phrase}"


def test_readme_documents_world_section():
    # 流畅度四档缺一不可："严重卡顿"（fps < fps_laggy）曾在文档中丢失
    for phrase in ("world", "Asia/Tokyo", "fps_smooth", "fps_moderate", "fps_laggy",
                   "流畅", "一般", "卡顿", "严重卡顿"):
        assert phrase in README, f"README world 配置文档缺少: {phrase}"


def test_readme_documents_bases_section():
    for phrase in ("assignment_radius", "ambiguity_ratio", "confirmation_samples",
                   "position_grid_size", "z_weight"):
        assert phrase in README, f"README bases 配置文档缺少: {phrase}"


def test_readme_documents_history_section():
    for phrase in ("raw_metrics_days", "aggregate_days",
                   "session_days", "observation_days"):
        assert phrase in README, f"README history 配置文档缺少: {phrase}"


def test_readme_documents_custom_headers_section():
    for phrase in ("custom_headers", "value_env", "servers 留空",
                   "所有服务器", "重启 AstrBot"):
        assert phrase in README, f"README custom_headers 配置文档缺少: {phrase}"


def test_readme_documents_plugin_page_section():
    for phrase in ("插件页面", "4.24.1", "4.25.3", "__unchanged__", "重载"):
        assert phrase in README, f"README 插件页面文档缺少: {phrase}"


def test_readme_documents_feature_groups():
    for phrase in ("功能开关", "features", "guilds_bases", "默认关", "game-data"):
        assert phrase in README, f"README 特性分组文档缺少: {phrase}"


def test_readme_command_table_and_matrix():
    # 命令详细表：表头 + 每个命令 + @server 尾缀
    for phrase in ("命令详细说明", "功能组", "可用命令矩阵",
                   "/pal status", "/pal online", "/pal world", "/pal rules",
                   "/pal today", "/pal events", "/pal guilds", "/pal guild",
                   "/pal bases", "/pal base", "/pal servers", "/pal help",
                   "/pal use", "/pal unbind", "@<服务器名>"):
        assert phrase in README, f"README 命令详细表缺少: {phrase}"
    # 功能分组命令矩阵：四组 + 关闭时行为文案
    for phrase in ("core", "report", "events", "guilds_bases", "未开放", "help 隐藏"):
        assert phrase in README, f"README 命令可用性矩阵缺少: {phrase}"


def test_readme_documents_players_group():
    for phrase in ("/pal rank", "/pal player", "/pal me", "/pal bind", "players"):
        assert phrase in README, f"README 缺少 players 组说明: {phrase}"
