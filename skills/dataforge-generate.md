---
name: dataforge-generate
description: Generate production-ready dbt models, SQL transforms, or Python ETL code grounded in DataHub metadata
tools:
  - generate_dbt_model
  - generate_sql
  - generate_python_etl
  - explore_catalog
---

# DataForge: Metadata-Aware Code Generation

You have access to DataForge tools that generate production-ready data pipeline code using real metadata from DataHub.

## When to use

Use DataForge when the user asks to:
- Create a dbt model or SQL transformation
- Generate ETL code for a data pipeline
- Build a data mart or analytical view
- Write data quality checks grounded in actual schemas

## How it works

1. **Explore first**: Use `explore_catalog` to discover available datasets
2. **Generate**: Use `generate_dbt_model`, `generate_sql`, or `generate_python_etl` with a natural language description
3. **Review**: The tool validates generated code against actual schemas — check the validation results

## Guidelines

- Always describe WHAT you want the output to show, not HOW to build it
- Mention specific metrics, dimensions, or business concepts in your request
- The tool reads real column names and types from DataHub — you don't need to specify them
- PII columns are automatically masked in output
- Generated dbt models include schema YAML with column descriptions and tests

## Examples

```
"Monthly revenue by product category with refund handling"
"Customer segmentation based on lifetime value and recency"
"Daily active users with cohort analysis by signup month"
"Data quality report: null rates and freshness for tier-1 datasets"
```
