"""Tests for the DataHub context layer."""

from dataforge.context import MockDataHubClient, Column, Dataset, CodeContext


def test_mock_client_search():
    client = MockDataHubClient()
    results = client.search("payments")
    assert len(results) > 0
    assert all("entity" in r for r in results)


def test_mock_client_search_filters():
    client = MockDataHubClient()
    results = client.search("products")
    urns = [r["entity"] for r in results]
    assert any("products" in u for u in urns)


def test_mock_client_get_dataset():
    client = MockDataHubClient()
    ds = client.get_dataset(
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.payments,PROD)"
    )
    assert ds.name == "raw.stripe.payments"
    assert ds.platform == "snowflake"
    assert len(ds.columns) == 8
    assert ds.columns[0].name == "payment_id"
    assert ds.columns[0].nullable is False


def test_mock_client_build_context():
    client = MockDataHubClient()
    ctx = client.build_context("revenue payments")
    assert isinstance(ctx, CodeContext)
    assert len(ctx.datasets) > 0


def test_code_context_to_prompt_block():
    ctx = CodeContext(
        datasets=[
            Dataset(
                urn="test:urn",
                name="test_table",
                platform="snowflake",
                description="A test table",
                columns=[
                    Column("id", "INTEGER", "Primary key", nullable=False),
                    Column("name", "VARCHAR", "User name", tags=["pii"]),
                    Column("amount", "NUMBER(12,2)", "Dollar amount"),
                ],
                tags=["tier-1"],
                owners=["team-a"],
            )
        ],
        request="test query",
    )
    block = ctx.to_prompt_block()
    assert "test_table" in block
    assert "id (INTEGER)" in block
    assert "NOT NULL" in block
    assert "pii" in block
    assert "tier-1" in block


def test_mock_lineage():
    client = MockDataHubClient()
    upstream = client.get_lineage(
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.marts.monthly_revenue,PROD)"
    )
    assert len(upstream) == 2
    assert any("payments" in u for u in upstream)


def test_mock_queries():
    client = MockDataHubClient()
    queries = client.get_queries("any_urn")
    assert len(queries) > 0
    assert "SELECT" in queries[0]
