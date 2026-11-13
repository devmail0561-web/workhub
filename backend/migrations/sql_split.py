"""Découpage d'un script SQL en instructions exécutables.

`psycopg` n'accepte pas plusieurs instructions dans un même `execute`. Le DDL v0 contient des
fonctions `plpgsql` (délimitées par `$$`), des littéraux et des commentaires : un simple
`split(";")` serait faux. Ce module suit l'état du parseur (chaîne, identifiant, commentaire,
dollar-quoting) pour ne couper que sur les points-virgules de premier niveau.
"""

from __future__ import annotations

import re

_DOLLAR_TAG = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")


def split_sql(script: str) -> list[str]:
    """Retourne les instructions SQL non vides, sans leur point-virgule final."""
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    length = len(script)
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    dollar_tag: str | None = None

    while index < length:
        char = script[index]

        if in_line_comment:
            buffer.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if script.startswith("*/", index):
                buffer.append("*/")
                in_block_comment = False
                index += 2
            else:
                buffer.append(char)
                index += 1
            continue

        if dollar_tag is not None:
            if script.startswith(dollar_tag, index):
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                dollar_tag = None
            else:
                buffer.append(char)
                index += 1
            continue

        if in_single:
            buffer.append(char)
            if char == "'":
                if index + 1 < length and script[index + 1] == "'":
                    buffer.append("'")
                    index += 2
                    continue
                in_single = False
            index += 1
            continue

        if in_double:
            buffer.append(char)
            if char == '"':
                if index + 1 < length and script[index + 1] == '"':
                    buffer.append('"')
                    index += 2
                    continue
                in_double = False
            index += 1
            continue

        if script.startswith("--", index):
            in_line_comment = True
            buffer.append("--")
            index += 2
            continue

        if script.startswith("/*", index):
            in_block_comment = True
            buffer.append("/*")
            index += 2
            continue

        if char == "'":
            in_single = True
            buffer.append(char)
            index += 1
            continue

        if char == '"':
            in_double = True
            buffer.append(char)
            index += 1
            continue

        if char == "$":
            match = _DOLLAR_TAG.match(script, index)
            if match is not None:
                dollar_tag = match.group(0)
                buffer.append(dollar_tag)
                index += len(dollar_tag)
                continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)

    return statements
