import pytest

from palchronicle.presentation.server_arg import ArgError, ParsedArg, parse_arg


def test_name_with_spaces_and_server_override():
    r = parse_arg("/pal guild The Red Legion @alpha", "guild")
    assert r == ParsedArg(name="The Red Legion", server_override="alpha")


def test_no_at_token_gives_none_override():
    r = parse_arg("/pal guild The Red Legion", "guild")
    assert r == ParsedArg(name="The Red Legion", server_override=None)


def test_bare_subcommand_no_name():
    r = parse_arg("/pal status", "status")
    assert r == ParsedArg(name="", server_override=None)


def test_only_server_override():
    r = parse_arg("/pal status @beta", "status")
    assert r == ParsedArg(name="", server_override="beta")


def test_at_inside_name_not_triggered():
    # '@' not at the trailing token position => part of name
    r = parse_arg("/pal guild foo@bar legion", "guild")
    assert r == ParsedArg(name="foo@bar legion", server_override=None)


def test_multiple_trailing_at_tokens_is_error():
    with pytest.raises(ArgError):
        parse_arg("/pal guild legion @alpha @beta", "guild")


def test_prefix_without_leading_slash():
    r = parse_arg("pal base #2 @alpha", "base")
    assert r == ParsedArg(name="#2", server_override="alpha")


def test_only_subcommand_word_without_pal_prefix():
    # some frameworks strip the group prefix already
    r = parse_arg("guild My Guild @s", "guild")
    assert r == ParsedArg(name="My Guild", server_override="s")
