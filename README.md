# DataForge

**Metadata-aware code generator powered by DataHub** — generates production-ready dbt models, SQL transforms, and Python ETL code that works on the first try because it reads real schemas, lineage, and documentation from your data catalog.

> Built for the [DataHub Agent Hackathon](https://datahub.com/blog/build-with-datahub-agent-hackathon) (July–August 2026)

## The Problem

AI code generators produce data pipeline code that *looks* right but fails in production because they guess at column names, assume join keys, and ignore data quality signals. You end up debugging AI-generated SQL that references columns that don't exist.

## The Solution

DataForge reads your actual metadata from DataHub before generating any code:

1. **Discovers** relevant source tables via DataHub search
2. **Reads** full schemas — column names, types, descriptions, tags, quality signals
3. **Traces** lineage to understand how tables connect
4. **Generates** production-ready code using only verified columns and relationships
5. **Validates** the output against the catalog — no hallucinated column references

The result: dbt models, SQL queries, and ETL scripts that compile on the first try.

## Quick Start

### Install

```bash
pip install dataforge
# or
uv pip install dataforge
```

### CLI Usage

```bash
# With a live DataHub instance
export DATAHUB_GMS_URL=https://your-datahub.acryl.io
export DATAHUB_GMS_TOKEN=your-token
export ANTHROPIC_API_KEY=your-key

dataforge generate "Monthly revenue by product category with refund handling" --type dbt

# With sample data (no DataHub needed)
dataforge generate "Customer segmentation by spend tiers" --type dbt --mock

# Explore your catalog
dataforge explore
```

### MCP Server (for Claude Code, Cursor, etc.)

DataForge runs as an MCP server, so any AI assistant can use it:

```bash
# Claude Code
claude mcp add dataforge -- python -m dataforge.server

# Cursor / other MCP clients
{
  "mcpServers": {
    "dataforge": {
      "command": "python",
      "args": ["-m", "dataforge.server"],
      "env": {
        "DATAHUB_GMS_URL": "https://your-datahub.acryl.io",
        "DATAHUB_GMS_TOKEN": "your-token",
        "ANTHROPIC_API_KEY": "your-key"
      }
    }
  }
}
```

Available tools:
- `generate_dbt_model` — Generate a complete dbt model + schema YAML
- `generate_sql` — Generate a SQL transformation query
- `generate_python_etl` — Generate a Python ETL script
- `explore_catalog` — Search and explore datasets in DataHub

### Python API

```python
from dataforge.agent import DataForgeAgent, OutputType

agent = DataForgeAgent(
    datahub_url="https://your-datahub.acryl.io",
    datahub_token="your-token",
)

result = agent.generate(
    "Monthly revenue by product category with refund handling",
    output_type=OutputType.DBT,
)

for filename, content in result.files.items():
    print(f"--- {filename} ---")
    print(content)

print(f"Validation: {result.validation}")
```

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  User        │     │  DataHub     │     │  Claude      │     │  Validator   │
│  "Create a   │────▶│  Search +    │────▶│  Generate    │────▶│  Verify all  │
│   dbt model  │     │  Schema +    │     │  code with   │     │  columns     │
│   for..."    │     │  Lineage     │     │  full        │     │  exist in    │
│              │     │  + Docs      │     │  context     │     │  schema      │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                           │                     │                     │
                           ▼                     ▼                     ▼
                     Real schemas          Code uses only       Zero hallucinated
                     28 columns            verified columns     column references
                     3 datasets            correct SQL dialect  PII properly masked
```

### What DataForge checks from DataHub:

| Metadata | How it's used |
|----------|---------------|
| **Column names & types** | Only reference columns that actually exist; correct type casting |
| **Descriptions** | Added to generated schema YAML for documentation |
| **Tags** (pii, tier-1, etc.) | PII columns masked in outputs; tier-1 sources preferred |
| **Lineage** | Determines join paths between tables |
| **Sample queries** | Learns common patterns and dialect from real usage |
| **Nullable flags** | Adds `not_null` tests and `coalesce()` where needed |
| **Glossary terms** | Maps business terms to the correct technical columns |

## Examples

See the [`examples/`](./examples/) directory for pre-generated outputs:

- **[Monthly Revenue](./examples/monthly_revenue/)** — dbt model joining Stripe payments with Shopify orders and products. Handles currency conversion, refunds, and line item expansion.
- **[Customer Segmentation](./examples/customer_segmentation/)** — Customer lifecycle model with PII masking, spend tiers, and churn detection.

Each example includes the generated SQL, schema YAML, and a README explaining what metadata was used and how.

## DataHub Integration

DataForge connects to DataHub through two methods:

### 1. Direct GMS API (default)
Talks to DataHub's GraphQL/REST API. Works with both DataHub Cloud and self-hosted instances.

```bash
export DATAHUB_GMS_URL=https://your-instance.acryl.io
export DATAHUB_GMS_TOKEN=your-personal-access-token
```

### 2. DataHub MCP Server
When DataForge is used *inside* another AI assistant (via its own MCP server), it chains through DataHub's MCP Server for metadata access.

## Configuration

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `DATAHUB_GMS_URL` | Yes* | DataHub GMS endpoint |
| `DATAHUB_GMS_TOKEN` | Yes* | Personal access token |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for code generation |
| `DATAFORGE_MODEL` | No | Claude model (default: `claude-sonnet-4-20250514`) |

\* Not required when using `--mock` mode for demos.

## Development

```bash
git clone https://github.com/Shitsuten/dataforge.git
cd dataforge
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

## Architecture

```
src/dataforge/
├── agent.py      # Core orchestrator: fetch context → generate → validate
├── context.py    # DataHub client + metadata models (Dataset, Column, CodeContext)
├── prompts.py    # System prompts for dbt/SQL/Python generation
├── server.py     # MCP server exposing tools to AI assistants
├── cli.py        # Click-based CLI
└── generators/   # (extensible) output-specific generators
```

## License

Apache-2.0
