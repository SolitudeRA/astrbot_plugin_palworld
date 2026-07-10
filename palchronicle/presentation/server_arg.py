from __future__ import annotations

from dataclasses import dataclass


class ArgError(ValueError):
    """Raised when the argument string is malformed (e.g. multiple @tokens)."""


@dataclass(slots=True)
class ParsedArg:
    name: str
    server_override: str | None


def _strip_prefix(message_str: str, subcommand: str) -> str:
    text = message_str.strip()
    if text.startswith("/"):
        text = text[1:]
    parts = text.split()
    # drop optional command-group token "pal"
    if parts and parts[0] == "pal":
        parts = parts[1:]
    # drop the subcommand token if present
    if parts and parts[0] == subcommand:
        parts = parts[1:]
    return " ".join(parts).strip()


def parse_arg(message_str: str, subcommand: str) -> ParsedArg:
    body = _strip_prefix(message_str, subcommand)
    if not body:
        return ParsedArg(name="", server_override=None)

    tokens = body.split()
    override: str | None = None
    if tokens[-1].startswith("@") and len(tokens[-1]) > 1:
        # trailing @token detected; reject a second trailing @token
        if len(tokens) >= 2 and tokens[-2].startswith("@") and len(tokens[-2]) > 1:
            raise ArgError("multiple server overrides")
        override = tokens[-1][1:]
        tokens = tokens[:-1]

    name = " ".join(tokens).strip()
    return ParsedArg(name=name, server_override=override)
