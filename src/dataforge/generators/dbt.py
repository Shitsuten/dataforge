"""dbt-specific generation utilities — source/ref resolution, materialization hints."""

from __future__ import annotations

import re

from ..context import CodeContext, Dataset


def infer_source_config(datasets: list[Dataset]) -> dict[str, list[str]]:
    """Group datasets into dbt sources by schema/platform.

    Returns dict of source_name → list of table names.
    """
    sources: dict[str, list[str]] = {}
    for ds in datasets:
        parts = ds.name.split(".")
        if len(parts) >= 2:
            schema = parts[-2]
            table = parts[-1]
        else:
            schema = ds.platform or "default"
            table = ds.name

        sources.setdefault(schema, []).append(table)
    return sources


def generate_sources_yml(datasets: list[Dataset]) -> str:
    """Generate a dbt sources.yml from discovered datasets."""
    source_groups = infer_source_config(datasets)

    lines = ["version: 2", "", "sources:"]
    for source_name, tables in source_groups.items():
        lines.append(f"  - name: {source_name}")

        platform = next((ds.platform for ds in datasets if source_name in ds.name), None)
        if platform:
            lines.append(f"    database: {platform}")

        lines.append("    tables:")
        for table in tables:
            matching = [ds for ds in datasets if ds.name.endswith(table)]
            ds = matching[0] if matching else None

            lines.append(f"      - name: {table}")
            if ds and ds.description:
                lines.append(f"        description: \"{ds.description}\"")
            if ds and ds.columns:
                lines.append("        columns:")
                for col in ds.columns:
                    lines.append(f"          - name: {col.name}")
                    if col.description:
                        lines.append(f"            description: \"{col.description}\"")
                    tests = []
                    if not col.nullable:
                        tests.append("not_null")
                    if "id" in col.name.lower() and not col.nullable:
                        tests.append("unique")
                    if tests:
                        lines.append("            tests:")
                        for t in tests:
                            lines.append(f"              - {t}")

    return "\n".join(lines)


def suggest_materialization(context: CodeContext) -> str:
    """Suggest materialization strategy based on context."""
    request = context.request.lower()

    if any(kw in request for kw in ["daily", "hourly", "incremental", "append"]):
        return "incremental"
    if any(kw in request for kw in ["mart", "report", "dashboard", "kpi"]):
        return "table"
    if any(kw in request for kw in ["staging", "stg_", "clean", "rename"]):
        return "view"
    return "table"


def detect_join_paths(datasets: list[Dataset]) -> list[dict]:
    """Detect potential join paths between datasets based on column names."""
    joins = []
    for i, ds_a in enumerate(datasets):
        for ds_b in datasets[i + 1 :]:
            a_cols = {c.name.lower(): c for c in ds_a.columns}
            b_cols = {c.name.lower(): c for c in ds_b.columns}

            shared = set(a_cols.keys()) & set(b_cols.keys())
            id_cols = [c for c in shared if c.endswith("_id") or c == "id"]

            for col_name in id_cols:
                joins.append({
                    "left": ds_a.name,
                    "right": ds_b.name,
                    "on": col_name,
                    "left_col": a_cols[col_name],
                    "right_col": b_cols[col_name],
                })

    return joins


def extract_column_refs(sql: str) -> set[str]:
    """Extract column name references from SQL for validation."""
    sql_clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    sql_clean = re.sub(r"/\*.*?\*/", "", sql_clean, flags=re.DOTALL)
    sql_clean = re.sub(r"'[^']*'", "''", sql_clean)

    tokens = re.findall(r"\b[a-z_][a-z0-9_]*\b", sql_clean.lower())

    sql_keywords = {
        "select", "from", "where", "join", "left", "right", "inner", "outer",
        "full", "cross", "on", "and", "or", "not", "in", "is", "null", "as",
        "case", "when", "then", "else", "end", "group", "by", "order", "having",
        "limit", "offset", "union", "all", "distinct", "with", "recursive",
        "insert", "into", "values", "update", "set", "delete", "create", "table",
        "drop", "alter", "index", "view", "true", "false", "between", "like",
        "exists", "asc", "desc", "count", "sum", "avg", "min", "max",
        "coalesce", "nullif", "cast", "date_trunc", "datediff", "current_date",
        "current_timestamp", "extract", "year", "month", "day", "hour",
        "round", "abs", "upper", "lower", "trim", "concat", "substring",
        "lateral", "flatten", "input", "value", "iff", "to_date", "over",
        "partition", "row_number", "rank", "dense_rank", "lag", "lead",
        "first_value", "last_value", "materialized", "config", "source", "ref",
        "integer", "varchar", "number", "timestamp", "boolean", "variant",
        "date", "float", "text",
    }

    return {t for t in tokens if t not in sql_keywords}
