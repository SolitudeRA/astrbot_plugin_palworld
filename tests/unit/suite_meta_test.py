from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_phase6_test_files_present():
    expected = [
        "tests/unit/fixtures_loader_test.py",
        "tests/unit/fixtures_boundary_test.py",
        "tests/integration/pipeline_test.py",
        "tests/integration/privacy_test.py",
        "tests/integration/routing_test.py",
        "tests/integration/smoke_test.py",
        "tests/unit/metadata_seed_test.py",
        "tests/unit/readme_test.py",
    ]
    missing = [p for p in expected if not (ROOT / p).is_file()]
    assert missing == [], f"缺失测试文件: {missing}"


def test_fixtures_scenarios_present():
    scenarios = ["normal_world", "no_players", "multi_guild_base", "missing_fields",
                 "unknown_class", "mixed_case_keys", "unauthorized",
                 "api_interrupt_recovery", "worldguid_switch"]
    root = ROOT / "tests" / "fixtures"
    missing = [s for s in scenarios if not (root / s).is_dir()]
    assert missing == [], f"缺失 fixture 场景: {missing}"
