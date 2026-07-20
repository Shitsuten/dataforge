"""Core agent that orchestrates metadata fetching, code generation, and validation."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum

import anthropic

from .context import CodeContext, DataHubClient, MockDataHubClient
from .prompts import (
    DBT_MODEL_PROMPT,
    PYTHON_ETL_PROMPT,
    SQL_TRANSFORM_PROMPT,
    SYSTEM_PROMPT,
    VALIDATION_PROMPT,
)


class OutputType(str, Enum):
    DBT = "dbt"
    SQL = "sql"
    PYTHON = "python"


@dataclass
class GenerationResult:
    output_type: OutputType
    files: dict[str, str]
    description: str
    validation: dict | None = None
    context_summary: str = ""


class DataForgeAgent:
    def __init__(
        self,
        datahub_url: str | None = None,
        datahub_token: str | None = None,
        anthropic_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        use_mock: bool = False,
    ):
        if use_mock or not datahub_url:
            self.datahub = MockDataHubClient()
        else:
            self.datahub = DataHubClient(datahub_url, datahub_token)

        api_key = anthropic_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY required — set it in env or pass anthropic_key")
        self.llm = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, request: str, output_type: OutputType = OutputType.DBT) -> GenerationResult:
        context = self.datahub.build_context(request)
        context.request = request
        context_block = context.to_prompt_block()

        prompt_template = {
            OutputType.DBT: DBT_MODEL_PROMPT,
            OutputType.SQL: SQL_TRANSFORM_PROMPT,
            OutputType.PYTHON: PYTHON_ETL_PROMPT,
        }[output_type]

        user_msg = prompt_template.format(context=context_block, request=request)

        response = self.llm.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = response.content[0].text
        parsed = self._extract_json(raw)

        files, description = self._build_files(parsed, output_type)

        validation = self._validate(context_block, files, output_type)

        return GenerationResult(
            output_type=output_type,
            files=files,
            description=description,
            validation=validation,
            context_summary=f"Used {len(context.datasets)} datasets from DataHub",
        )

    def _build_files(self, parsed: dict, output_type: OutputType) -> tuple[dict[str, str], str]:
        files = {}

        if output_type == OutputType.DBT:
            model_name = parsed.get("model_name", "generated_model")
            files[f"models/marts/{model_name}.sql"] = parsed.get("model_sql", "")
            files[f"models/marts/schema.yml"] = parsed.get("schema_yml", "")
            description = f"dbt model: {model_name}"

        elif output_type == OutputType.SQL:
            files["query.sql"] = parsed.get("sql", "")
            description = parsed.get("description", "SQL transform")

        elif output_type == OutputType.PYTHON:
            files["etl.py"] = parsed.get("script", "")
            description = parsed.get("description", "Python ETL script")

        else:
            description = "Generated code"

        return files, description

    def _validate(self, context_block: str, files: dict[str, str], output_type: OutputType) -> dict:
        code_to_validate = "\n\n".join(
            f"--- {name} ---\n{content}" for name, content in files.items()
        )
        user_msg = VALIDATION_PROMPT.format(context=context_block, code=code_to_validate)

        response = self.llm.messages.create(
            model=self.model,
            max_tokens=2048,
            system="You are a code validation assistant. Return only valid JSON.",
            messages=[{"role": "user", "content": user_msg}],
        )

        raw = response.content[0].text
        return self._extract_json(raw)

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1
            for i, line in enumerate(lines):
                if i > 0 and line.strip() == "```":
                    end = i
                    break
            text = "\n".join(lines[start:end])

        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            text = text[brace_start : brace_end + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_output": text, "parse_error": True}
