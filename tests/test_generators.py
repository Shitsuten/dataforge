"""Tests for generator utilities."""

from dataforge.context import Column, Dataset, CodeContext
from dataforge.generators.dbt import (
    detect_join_paths,
    extract_column_refs,
    generate_sources_yml,
    infer_source_config,
    suggest_materialization,
)


def _make_datasets():
    return [
        Dataset(
            urn="a", name="raw.stripe.payments", platform="snowflake",
            columns=[
                Column("payment_id", "VARCHAR", nullable=False),
                Column("customer_id", "VARCHAR"),
                Column("amount", "NUMBER"),
            ],
        ),
        Dataset(
            urn="b", name="raw.stripe.customers", platform="snowflake",
            columns=[
                Column("customer_id", "VARCHAR", nullable=False),
                Column("email", "VARCHAR"),
            ],
        ),
    ]


def test_infer_source_config():
    result = infer_source_config(_make_datasets())
    assert "stripe" in result
    assert "payments" in result["stripe"]
    assert "customers" in result["stripe"]


def test_generate_sources_yml():
    yml = generate_sources_yml(_make_datasets())
    assert "version: 2" in yml
    assert "name: stripe" in yml
    assert "name: payments" in yml
    assert "not_null" in yml


def test_suggest_materialization():
    ctx = CodeContext(datasets=[], request="Create a daily incremental model")
    assert suggest_materialization(ctx) == "incremental"

    ctx2 = CodeContext(datasets=[], request="Build a revenue mart")
    assert suggest_materialization(ctx2) == "table"

    ctx3 = CodeContext(datasets=[], request="Clean and rename staging columns")
    assert suggest_materialization(ctx3) == "view"


def test_detect_join_paths():
    joins = detect_join_paths(_make_datasets())
    assert len(joins) == 1
    assert joins[0]["on"] == "customer_id"
    assert "payments" in joins[0]["left"]
    assert "customers" in joins[0]["right"]


def test_extract_column_refs():
    sql = """
    SELECT
        p.customer_id,
        p.amount / 100.0 as amount_usd,
        c.email
    FROM payments p
    JOIN customers c ON p.customer_id = c.customer_id
    WHERE p.amount > 0
    """
    refs = extract_column_refs(sql)
    assert "customer_id" in refs
    assert "amount" in refs
    assert "email" in refs
    assert "amount_usd" in refs
    assert "select" not in refs
    assert "from" not in refs


def test_extract_column_refs_ignores_strings():
    sql = "SELECT id FROM t WHERE status = 'active' AND name LIKE '%test%'"
    refs = extract_column_refs(sql)
    assert "id" in refs
    assert "status" in refs
    assert "active" not in refs
    assert "test" not in refs
