"""Fetches metadata context from a DataHub instance for grounding code generation."""

from __future__ import annotations

import httpx
from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    glossary_terms: list[str] = field(default_factory=list)
    nullable: bool = True


@dataclass
class Dataset:
    urn: str
    name: str
    platform: str
    description: str = ""
    columns: list[Column] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    glossary_terms: list[str] = field(default_factory=list)
    upstream: list[str] = field(default_factory=list)
    downstream: list[str] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)


@dataclass
class CodeContext:
    """All the metadata context an LLM needs to generate grounded code."""
    datasets: list[Dataset]
    lineage_paths: dict[str, list[str]] = field(default_factory=dict)
    request: str = ""

    def to_prompt_block(self) -> str:
        parts = []
        for ds in self.datasets:
            header = f"## {ds.platform}.{ds.name}"
            if ds.description:
                header += f"\n{ds.description}"
            cols = []
            for c in ds.columns:
                line = f"  - {c.name} ({c.type})"
                if c.description:
                    line += f" — {c.description}"
                if c.tags:
                    line += f" [{', '.join(c.tags)}]"
                if not c.nullable:
                    line += " NOT NULL"
                cols.append(line)
            col_block = "\n".join(cols) if cols else "  (no schema available)"

            meta_lines = []
            if ds.tags:
                meta_lines.append(f"  Tags: {', '.join(ds.tags)}")
            if ds.owners:
                meta_lines.append(f"  Owners: {', '.join(ds.owners)}")
            if ds.glossary_terms:
                meta_lines.append(f"  Terms: {', '.join(ds.glossary_terms)}")
            if ds.upstream:
                meta_lines.append(f"  Upstream: {', '.join(ds.upstream)}")
            if ds.downstream:
                meta_lines.append(f"  Downstream: {', '.join(ds.downstream)}")

            section = header + "\n\nColumns:\n" + col_block
            if meta_lines:
                section += "\n\n" + "\n".join(meta_lines)

            if ds.sample_queries:
                section += "\n\nSample queries:\n"
                for q in ds.sample_queries[:3]:
                    section += f"```sql\n{q}\n```\n"

            parts.append(section)

        if self.lineage_paths:
            paths_section = "\n## Lineage paths\n"
            for key, path in self.lineage_paths.items():
                paths_section += f"  {key}: {' → '.join(path)}\n"
            parts.append(paths_section)

        return "\n\n---\n\n".join(parts)


class DataHubClient:
    """Talks to DataHub GMS API to fetch metadata for code generation."""

    def __init__(self, gms_url: str, token: str | None = None):
        self.gms_url = gms_url.rstrip("/")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = httpx.Client(base_url=self.gms_url, headers=headers, timeout=30)

    def search(self, query: str, entity_type: str = "dataset", limit: int = 10) -> list[dict]:
        resp = self.http.post(
            "/entities",
            params={"action": "search"},
            json={
                "input": query,
                "entity": entity_type,
                "start": 0,
                "count": limit,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("value", {}).get("entities", [])

    def get_dataset(self, urn: str) -> Dataset:
        resp = self.http.get(
            "/aspects",
            params={
                "urn": urn,
                "aspects": "datasetProperties,schemaMetadata,ownership,globalTags,glossaryTerms,upstreamLineage",
            },
        )
        resp.raise_for_status()
        aspects = resp.json()
        return self._parse_dataset(urn, aspects)

    def get_lineage(self, urn: str, direction: str = "UPSTREAM", depth: int = 3) -> list[str]:
        resp = self.http.get(
            "/relationships",
            params={
                "urn": urn,
                "direction": direction,
                "types": "DownstreamOf" if direction == "UPSTREAM" else "Produces",
                "maxHops": depth,
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [r.get("entity", "") for r in data.get("relationships", [])]

    def get_queries(self, urn: str, limit: int = 5) -> list[str]:
        resp = self.http.get(
            "/aspects",
            params={"urn": urn, "aspects": "datasetUsageStatistics"},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        queries = []
        for aspect in data.get("aspects", []):
            stats = aspect.get("datasetUsageStatistics", {})
            for q in stats.get("topSqlQueries", []):
                queries.append(q)
                if len(queries) >= limit:
                    break
        return queries

    def build_context(self, query: str, max_datasets: int = 8) -> CodeContext:
        results = self.search(query, limit=max_datasets)
        datasets = []
        for r in results:
            urn = r.get("entity", "")
            if not urn:
                continue
            ds = self.get_dataset(urn)
            ds.upstream = self.get_lineage(urn, "UPSTREAM")
            ds.downstream = self.get_lineage(urn, "DOWNSTREAM")
            ds.sample_queries = self.get_queries(urn)
            datasets.append(ds)

        lineage_paths = {}
        if len(datasets) >= 2:
            for i, ds in enumerate(datasets[1:], 1):
                key = f"{datasets[0].name} → {ds.name}"
                lineage_paths[key] = [datasets[0].name, ds.name]

        return CodeContext(datasets=datasets, lineage_paths=lineage_paths, request=query)

    def _parse_dataset(self, urn: str, aspects: dict) -> Dataset:
        name = urn.split(",")[-1].rstrip(")") if "," in urn else urn
        platform = ""
        if "urn:li:dataPlatform:" in urn:
            platform = urn.split("urn:li:dataPlatform:")[1].split(",")[0]

        props = {}
        schema_meta = {}
        ownership = {}
        tags_aspect = {}
        terms_aspect = {}

        for aspect_wrapper in aspects.get("aspects", []):
            if "datasetProperties" in aspect_wrapper:
                props = aspect_wrapper["datasetProperties"]
            if "schemaMetadata" in aspect_wrapper:
                schema_meta = aspect_wrapper["schemaMetadata"]
            if "ownership" in aspect_wrapper:
                ownership = aspect_wrapper["ownership"]
            if "globalTags" in aspect_wrapper:
                tags_aspect = aspect_wrapper["globalTags"]
            if "glossaryTerms" in aspect_wrapper:
                terms_aspect = aspect_wrapper["glossaryTerms"]

        columns = []
        for f in schema_meta.get("fields", []):
            col = Column(
                name=f.get("fieldPath", ""),
                type=f.get("nativeDataType", f.get("type", "UNKNOWN")),
                description=f.get("description", ""),
                nullable=f.get("nullable", True),
                tags=[
                    t.get("tag", "").split(":")[-1]
                    for t in f.get("globalTags", {}).get("tags", [])
                ],
                glossary_terms=[
                    t.get("urn", "").split(":")[-1]
                    for t in f.get("glossaryTerms", {}).get("terms", [])
                ],
            )
            columns.append(col)

        owners = [
            o.get("owner", "").split(":")[-1]
            for o in ownership.get("owners", [])
        ]
        ds_tags = [
            t.get("tag", "").split(":")[-1]
            for t in tags_aspect.get("tags", [])
        ]
        ds_terms = [
            t.get("urn", "").split(":")[-1]
            for t in terms_aspect.get("terms", [])
        ]

        return Dataset(
            urn=urn,
            name=props.get("name", name),
            platform=platform,
            description=props.get("description", ""),
            columns=columns,
            tags=ds_tags,
            owners=owners,
            glossary_terms=ds_terms,
        )


class MockDataHubClient(DataHubClient):
    """A mock client with sample data for demos and testing without a live DataHub instance."""

    def __init__(self):
        self.gms_url = "mock://datahub"
        self.http = None

    def search(self, query: str, entity_type: str = "dataset", limit: int = 10) -> list[dict]:
        return [{"entity": urn} for urn in self._sample_urns(query)]

    def get_dataset(self, urn: str) -> Dataset:
        return self._sample_datasets().get(urn, Dataset(urn=urn, name="unknown", platform="unknown"))

    def get_lineage(self, urn: str, direction: str = "UPSTREAM", depth: int = 3) -> list[str]:
        lineage_map = {
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.marts.monthly_revenue,PROD)": [
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.payments,PROD)",
                "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.shopify.orders,PROD)",
            ],
        }
        return lineage_map.get(urn, [])

    def get_queries(self, urn: str, limit: int = 5) -> list[str]:
        return [
            "SELECT date_trunc('month', order_date) as month, SUM(amount) as revenue FROM raw.stripe.payments GROUP BY 1",
        ]

    def _sample_urns(self, query: str) -> list[str]:
        all_urns = list(self._sample_datasets().keys())
        q = query.lower()
        matched = [u for u in all_urns if any(kw in u.lower() for kw in q.split())]
        return matched or all_urns[:3]

    def _sample_datasets(self) -> dict[str, Dataset]:
        return {
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.payments,PROD)": Dataset(
                urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.payments,PROD)",
                name="raw.stripe.payments",
                platform="snowflake",
                description="Raw payment events from Stripe webhooks, loaded via Fivetran.",
                columns=[
                    Column("payment_id", "VARCHAR(64)", "Stripe payment intent ID", nullable=False),
                    Column("customer_id", "VARCHAR(64)", "Stripe customer ID"),
                    Column("amount", "NUMBER(12,2)", "Payment amount in USD cents"),
                    Column("currency", "VARCHAR(3)", "ISO currency code", tags=["pii-free"]),
                    Column("status", "VARCHAR(20)", "Payment status: succeeded, failed, refunded"),
                    Column("payment_method", "VARCHAR(30)", "Card, bank_transfer, etc."),
                    Column("created_at", "TIMESTAMP_NTZ", "When the payment was created"),
                    Column("metadata_json", "VARIANT", "Raw Stripe metadata blob"),
                ],
                tags=["tier-1", "pii", "financial"],
                owners=["data-eng-team"],
                glossary_terms=["Revenue", "Payment"],
            ),
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.shopify.orders,PROD)": Dataset(
                urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.shopify.orders,PROD)",
                name="raw.shopify.orders",
                platform="snowflake",
                description="Shopify order data synced daily. Each row is one order.",
                columns=[
                    Column("order_id", "VARCHAR(64)", "Shopify order ID", nullable=False),
                    Column("customer_email", "VARCHAR(255)", "Customer email", tags=["pii"]),
                    Column("total_price", "NUMBER(12,2)", "Order total in shop currency"),
                    Column("subtotal_price", "NUMBER(12,2)", "Before tax/shipping"),
                    Column("currency", "VARCHAR(3)", "Shop currency"),
                    Column("financial_status", "VARCHAR(20)", "paid, pending, refunded"),
                    Column("fulfillment_status", "VARCHAR(20)", "fulfilled, partial, null"),
                    Column("order_date", "TIMESTAMP_NTZ", "When the order was placed"),
                    Column("line_items_json", "VARIANT", "Array of line item objects"),
                    Column("discount_codes", "VARIANT", "Applied discount codes"),
                ],
                tags=["tier-1", "pii", "ecommerce"],
                owners=["data-eng-team"],
                glossary_terms=["Revenue", "Order", "Customer"],
            ),
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.shopify.products,PROD)": Dataset(
                urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.shopify.products,PROD)",
                name="raw.shopify.products",
                platform="snowflake",
                description="Shopify product catalog. One row per product variant.",
                columns=[
                    Column("product_id", "VARCHAR(64)", "Shopify product ID", nullable=False),
                    Column("variant_id", "VARCHAR(64)", "Variant ID", nullable=False),
                    Column("title", "VARCHAR(500)", "Product title"),
                    Column("product_type", "VARCHAR(100)", "Category/type"),
                    Column("vendor", "VARCHAR(200)", "Product vendor/brand"),
                    Column("price", "NUMBER(12,2)", "Variant price"),
                    Column("sku", "VARCHAR(100)", "Stock keeping unit"),
                    Column("inventory_quantity", "INTEGER", "Current stock count"),
                    Column("created_at", "TIMESTAMP_NTZ", "When product was created"),
                    Column("updated_at", "TIMESTAMP_NTZ", "Last update timestamp"),
                ],
                tags=["tier-2"],
                owners=["data-eng-team"],
                glossary_terms=["Product", "Inventory"],
            ),
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.customers,PROD)": Dataset(
                urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw.stripe.customers,PROD)",
                name="raw.stripe.customers",
                platform="snowflake",
                description="Stripe customer records with billing details.",
                columns=[
                    Column("customer_id", "VARCHAR(64)", "Stripe customer ID", nullable=False),
                    Column("email", "VARCHAR(255)", "Customer email", tags=["pii"]),
                    Column("name", "VARCHAR(255)", "Customer name", tags=["pii"]),
                    Column("created_at", "TIMESTAMP_NTZ", "Account creation date"),
                    Column("metadata_json", "VARIANT", "Custom metadata"),
                    Column("default_payment_method", "VARCHAR(64)", "Default payment method ID"),
                ],
                tags=["tier-1", "pii"],
                owners=["data-eng-team"],
                glossary_terms=["Customer"],
            ),
        }
