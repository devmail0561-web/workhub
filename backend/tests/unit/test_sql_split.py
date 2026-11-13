from migrations.sql_split import split_sql


def test_split_simple_statements() -> None:
    assert split_sql("select 1; select 2;") == ["select 1", "select 2"]


def test_split_ignores_empty_statements() -> None:
    assert split_sql(";;\n select 1 ;;\n") == ["select 1"]


def test_split_preserves_semicolon_in_string_literal() -> None:
    assert split_sql("select 'a;b'; select 2;") == ["select 'a;b'", "select 2"]


def test_split_preserves_escaped_quote() -> None:
    assert split_sql("select 'it''s;ok';") == ["select 'it''s;ok'"]


def test_split_preserves_dollar_quoted_body() -> None:
    script = """create function f() returns void language plpgsql as $$
begin
    perform 1;
    perform 2;
end;
$$;
select 1;
"""
    statements = split_sql(script)
    assert len(statements) == 2
    assert "perform 1;" in statements[0]
    assert statements[0].endswith("$$")
    assert statements[1] == "select 1"


def test_split_ignores_semicolon_in_comments() -> None:
    script = "-- un; commentaire\nselect 1;\n/* bloc; commentaire */\nselect 2;"
    assert split_sql(script) == [
        "-- un; commentaire\nselect 1",
        "/* bloc; commentaire */\nselect 2",
    ]


def test_split_keeps_trailing_statement_without_semicolon() -> None:
    assert split_sql("select 1") == ["select 1"]
