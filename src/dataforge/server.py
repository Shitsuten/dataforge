"""DataForge MCP Server — expose code generation as MCP tools for AI assistants."""

from __future__ import annotations

import json
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .agent import DataForgeAgent, OutputType

server = Server("dataforge")


def _get_agent() -> DataForgeAgent:
    return DataForgeAgent(
        datahub_url=os.environ.get("DATAHUB_GMS_URL"),
        datahub_token=os.environ.get("DATAHUB_GMS_TOKEN"),
        anthropic_key=os.environ.get("ANTHROPIC_API_KEY"),
        model=os.environ.get("DATAFORGE_MODEL", "claude-sonnet-4-20250514"),
        use_mock=not os.environ.get("DATAHUB_GMS_URL"),
    )


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="generate_dbt_model",
            description=(
                "Generate a production-ready dbt model (SQL + schema YAML) from a natural language "
                "description. The model is grounded in real schemas, lineage, and documentation "
                "from DataHub — column names, types, and joins are all verified against the catalog."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "Natural language description of the dbt model to generate. "
                        "Example: 'Monthly revenue by product category with refund handling'",
                    },
                },
                "required": ["request"],
            },
        ),
        Tool(
            name="generate_sql",
            description=(
                "Generate a SQL transformation query grounded in real DataHub metadata. "
                "Uses actual table schemas, column types, and lineage to produce correct SQL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "Natural language description of the SQL query to generate.",
                    },
                },
                "required": ["request"],
            },
        ),
        Tool(
            name="generate_python_etl",
            description=(
                "Generate a Python ETL script grounded in real DataHub metadata. "
                "Includes proper connectors, type handling, and error management."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "Natural language description of the ETL pipeline to generate.",
                    },
                },
                "required": ["request"],
            },
        ),
        Tool(
            name="explore_catalog",
            description=(
                "Search and explore datasets in DataHub. Returns schema information, "
                "descriptions, tags, ownership, and lineage for matching datasets."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — keywords like 'revenue', 'customers', 'orders'.",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    agent = _get_agent()

    if name == "explore_catalog":
        query = arguments.get("query", "*")
        context = agent.datahub.build_context(query)
        return [TextContent(type="text", text=context.to_prompt_block())]

    type_map = {
        "generate_dbt_model": OutputType.DBT,
        "generate_sql": OutputType.SQL,
        "generate_python_etl": OutputType.PYTHON,
    }

    output_type = type_map.get(name)
    if not output_type:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    request = arguments.get("request", "")
    result = agent.generate(request, output_type)

    output_parts = [f"## {result.description}\n{result.context_summary}\n"]

    for filename, content in result.files.items():
        lang = "sql" if filename.endswith(".sql") else "yaml" if filename.endswith(".yml") else "python"
        output_parts.append(f"### {filename}\n```{lang}\n{content}\n```\n")

    if result.validation:
        valid = result.validation.get("valid", False)
        issues = result.validation.get("issues", [])
        if valid:
            output_parts.append("**✓ Validation passed**")
        else:
            output_parts.append("**✗ Validation issues:**\n" + "\n".join(f"- {i}" for i in issues))

    return [TextContent(type="text", text="\n".join(output_parts))]


async def run():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()
