"""Tests for the agent module (unit tests that don't require API keys)."""

from dataforge.agent import DataForgeAgent, OutputType


def test_extract_json_from_markdown():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    text = '```json\n{"model_sql": "SELECT 1", "model_name": "test"}\n```'
    result = agent._extract_json(text)
    assert result["model_sql"] == "SELECT 1"
    assert result["model_name"] == "test"


def test_extract_json_raw():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    text = '{"sql": "SELECT * FROM t", "description": "test query"}'
    result = agent._extract_json(text)
    assert result["sql"] == "SELECT * FROM t"


def test_extract_json_with_text_around():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    text = 'Here is the result:\n{"valid": true, "issues": []}\nEnd of output.'
    result = agent._extract_json(text)
    assert result["valid"] is True
    assert result["issues"] == []


def test_extract_json_invalid():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    text = "This is not JSON at all"
    result = agent._extract_json(text)
    assert "parse_error" in result


def test_build_files_dbt():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    parsed = {
        "model_sql": "SELECT 1 as id",
        "schema_yml": "version: 2\nmodels: []",
        "model_name": "test_model",
    }
    files, desc = agent._build_files(parsed, OutputType.DBT)
    assert "models/marts/test_model.sql" in files
    assert "models/marts/schema.yml" in files
    assert files["models/marts/test_model.sql"] == "SELECT 1 as id"


def test_build_files_sql():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    parsed = {"sql": "SELECT 1", "description": "test"}
    files, desc = agent._build_files(parsed, OutputType.SQL)
    assert "query.sql" in files


def test_build_files_python():
    agent = DataForgeAgent.__new__(DataForgeAgent)
    parsed = {"script": "print('hello')", "description": "test"}
    files, desc = agent._build_files(parsed, OutputType.PYTHON)
    assert "etl.py" in files


def test_output_type_values():
    assert OutputType.DBT == "dbt"
    assert OutputType.SQL == "sql"
    assert OutputType.PYTHON == "python"
