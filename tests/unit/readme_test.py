from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
README = (_ROOT / "README.md").read_text(encoding="utf-8")
# README 多级化后,配置详解与指令全表迁至 docs/;内容型锚点在文档合集中断言,
# 安全声明仍强制留在主页(第一屏可见)。
DOCS = README + "\n" + "\n".join(
    (_ROOT / "docs" / name).read_text(encoding="utf-8")
    for name in ("configuration.md", "commands.md")
)


def test_readme_first_screen_safety_claims():
    # 安全声明必须在主 README(不接受移入子文档)。
    # v0.9.5 定位为「受控写」:观测仍只读,但含受控写命令
    # (默认全关、仅授权管理员、全程审计),首屏安全声明须如实反映。
    for phrase in ("受控写", "仅授权管理员", "审计", "不存储 IP",
                   "不公开精确位置", "启用 REST", "勿暴露公网"):
        assert phrase in README, f"README 缺少安全声明: {phrase}"


def test_readme_links_to_docs():
    # 主页必须链接到两份子文档(防断链/防孤儿文档)
    for link in ("docs/configuration.md", "docs/commands.md"):
        assert link in README, f"README 缺少子文档链接: {link}"


def test_readme_requirements_and_usage():
    assert "AstrBot ≥ 4.24.1" in DOCS or "AstrBot >= 4.24.1" in DOCS
    for phrase in ("/pal link add", "多服务器", "@server", "群授权", "安装", "配置"):
        assert phrase in DOCS, f"文档缺少用法段落: {phrase}"


def test_readme_lists_readonly_endpoints():
    for ep in ("/info", "/metrics", "/players", "/settings", "/game-data"):
        assert ep in DOCS, f"文档未声明只读端点: {ep}"


def test_readme_install_splits_runtime_and_dev_deps():
    # 安装节:运行时三件套 + 开发者另装 requirements-dev.txt
    for phrase in ("aiohttp", "aiosqlite", "tzdata", "requirements-dev.txt"):
        assert phrase in DOCS, f"文档安装说明缺少: {phrase}"


def test_readme_documents_polling_section():
    for phrase in ("metrics_seconds", "players_seconds", "info_seconds",
                   "settings_seconds", "game_data_seconds",
                   "jitter_ratio", "max_concurrency", "背压"):
        assert phrase in DOCS, f"文档 polling 配置缺少: {phrase}"


def test_readme_documents_world_section():
    # 流畅度四档缺一不可:「严重卡顿」(fps < fps_laggy)曾在文档中丢失
    for phrase in ("world", "Asia/Tokyo", "fps_smooth", "fps_moderate", "fps_laggy",
                   "流畅", "一般", "卡顿", "严重卡顿"):
        assert phrase in DOCS, f"文档 world 配置缺少: {phrase}"


def test_readme_documents_bases_section():
    for phrase in ("assignment_radius", "ambiguity_ratio", "confirmation_samples",
                   "position_grid_size", "z_weight"):
        assert phrase in DOCS, f"文档 bases 配置缺少: {phrase}"


def test_readme_documents_history_section():
    for phrase in ("raw_metrics_days", "aggregate_days",
                   "session_days", "observation_days"):
        assert phrase in DOCS, f"文档 history 配置缺少: {phrase}"


def test_readme_documents_custom_headers_section():
    for phrase in ("custom_headers", "value_env", "servers 留空",
                   "所有服务器", "重启 AstrBot"):
        assert phrase in DOCS, f"文档 custom_headers 配置缺少: {phrase}"


def test_readme_documents_plugin_page_section():
    for phrase in ("插件页面", "4.24.1", "4.25.3", "__unchanged__", "重载"):
        assert phrase in DOCS, f"文档插件页面说明缺少: {phrase}"


def test_readme_documents_feature_groups():
    for phrase in ("功能开关", "features", "guilds_bases", "默认关", "game-data"):
        assert phrase in DOCS, f"文档特性分组说明缺少: {phrase}"


def test_readme_command_table_and_matrix():
    # 分级指令详表(v0.9.5):5 组 + 6 扁平;表头 + 组/子动作完整路径 + @server 尾缀
    for phrase in ("指令详表", "功能组", "可用指令矩阵", "分级",
                   "/pal world status", "/pal online", "/pal world rules",
                   "/pal world today", "/pal world events",
                   "/pal guild list", "/pal guild bases", "/pal guild base",
                   "/pal server", "/pal whoami", "/pal help",
                   "@<服务器名>"):
        assert phrase in DOCS, f"文档指令表缺少: {phrase}"
    # 功能开关指令矩阵:四组 + 关闭时行为文案。
    # 行为义(命令被停用时的聊天回执)锚 = 「回「未开启」」(T13 起回执由「未开放」改为「未开启」)。
    # (game-data 上游 2026-07 已上线,「上游未开放」锁定期文案随解禁回收,不再设上游义锚。)
    for phrase in ("core", "report", "events", "guilds_bases",
                   "回「未开启」", "help 隐藏"):
        assert phrase in DOCS, f"文档指令可用性矩阵缺少: {phrase}"


def test_readme_documents_players_group():
    # players 组分级:rank(扁平变体)/player 组(info/bind/unbind)/me(扁平)
    for phrase in ("/pal rank", "/pal player info", "/pal me",
                   "/pal player bind", "/pal player unbind", "players",
                   "today", "total", "level"):
        assert phrase in DOCS, f"文档缺少 players 组说明: {phrase}"


def test_readme_documents_world_mode_and_link():
    # 单/多世界模式 + link 组(服务器选择,仅多世界)
    for phrase in ("world_mode", "single", "multi", "单世界", "多世界",
                   "/pal link", "/pal link add", "/pal link remove"):
        assert phrase in DOCS, f"文档缺少 world_mode / link 说明: {phrase}"


def test_readme_documents_permission_migration():
    # legacy 权限键会自动迁移到 command_permissions；无效锁明确告警。
    for phrase in ("自动迁移", "command_permissions", "完整命令路径",
                   "无效锁", "启动告警"):
        assert phrase in DOCS, f"文档缺少权限自动迁移说明: {phrase}"


def test_readme_documents_permission_management():
    # 权限管理:whoami 自查 + 管理员名单 + 命令门 + 三条安全告知
    for phrase in ("/pal whoami", "管理员名单", "permission_admins", "command_permissions"):
        assert phrase in DOCS, f"文档缺少权限管理说明: {phrase}"
    # 三条安全告知必须落在文档里
    for phrase in ("全局", "命名空间", "明文", "PII"):
        assert phrase in DOCS, f"文档缺少权限安全告知: {phrase}"


def test_readme_documents_server_admin_commands():
    # 服务器管控(分级 server 组):7 写命令 + confirm 二次确认,均须在文档指令表出现
    for cmd in ("/pal server announce", "/pal server save", "/pal server kick",
                "/pal server unban", "/pal server ban", "/pal server shutdown",
                "/pal server stop", "/pal confirm"):
        assert cmd in DOCS, f"文档缺少服务器管控命令: {cmd}"
    # 两个 feature 组 + 危险分级
    for phrase in ("服务器管控", "server_admin_basic", "server_admin_danger",
                   "二次确认", "受控写"):
        assert phrase in DOCS, f"文档缺少服务器管控说明: {phrase}"


def test_readme_documents_server_admin_safety():
    # 安全告知:OPEN 爆炸半径、stop 丢档、审计留存/PII
    for phrase in ("仅授权管理员", "审计", "爆炸半径", "丢档",
                   "audit_retention_days", "require_confirmation"):
        assert phrase in DOCS, f"文档缺少服务器管控安全告知: {phrase}"
