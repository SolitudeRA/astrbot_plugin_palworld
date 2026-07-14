import pytest

from palworld_terminal.presentation.server_arg import ArgError, parse_group


def test_basic_sub_and_rest():
    p = parse_group("/pal guild info 战狼帮", "guild")
    assert p.sub == "info" and p.rest == "战狼帮" and p.server_override is None


def test_three_segment_with_override():
    p = parse_group("/pal guild info 战狼帮 @alpha", "guild")
    assert p.sub == "info" and p.rest == "战狼帮" and p.server_override == "alpha"


def test_group_word_absent_still_parses():
    # AstrBot 某些版本会剥掉组词，只留子动作
    p = parse_group("info 战狼帮", "guild")
    assert p.sub == "info" and p.rest == "战狼帮"
    assert p.server_override is None


def test_bare_group_empty_sub():
    p = parse_group("/pal server", "server")
    assert p.sub == "" and p.rest == ""


def test_reason_keeps_spaces_collapsed():
    p = parse_group("/pal server kick Alice 刷屏 挂机", "server")
    assert p.sub == "kick" and p.rest == "Alice 刷屏 挂机"


def test_double_override_raises():
    with pytest.raises(ArgError):
        parse_group("/pal server kick Alice @a @b", "server")
