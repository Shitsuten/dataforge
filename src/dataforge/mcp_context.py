"""DataHub context via MCP protocol — chains through DataHub's MCP Server."""

from __future__ import annotations

import json

import httpx

from .context import CodeContext, Column, Dataset


class DataHubMCPClient:
    """Fetches metadata from DataHub via its MCP Server endpoint.

    This is the recommended integration path for DataHub Cloud — the MCP server
    handles authentication, pagination, and provides a stable tool interface.
    """

    def __init__(self, mcp_url: str, token: str | None = None):
        self.mcp_url = mcp_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.http = httpx.Client(headers=headers, timeout=30)
        self._request_id = 0

    def _call(self, tool_name: str, arguments: dict) -> dict:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        resp = self.http.post(self.mcp_url, json=payload)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            raise RuntimeError(f"MCP error: {result['error']}")
        content = result.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            text = content[0]["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}
        return {}

    def search(self, query: str, limit: int = 10) -> list[dict]:
        result = self._call("search", {"query": query, "count": limit})
        return result.get("results", result.get("entities", []))

    def get_entities(self, urns: list[str]) -> list[dict]:
        result = self._call("get_entities", {"urns": urns})
        return result.get("entities", [result] if "urn" in result else [])

    def get_lineage(self, urn: str, direction: str = "UPSTREAM", depth: int = 3) -> list[str]:
        result = self._call("get_lineage", {
            "urn": urn,
            "direction": direction,
            "max_hops": depth,
        })
        entities = result.get("entities", [])
        return [e.get("urn", "") for e in entities if e.get("urn")]

    def get_schema_fields(self, urn: str) -> list[dict]:
        result = self._call("list_schema_fields", {"urn": urn})
        return result.get("fields", [])

    def get_queries(self, urn: str, limit: int = 5) -> list[str]:
        result = self._call("get_dataset_queries", {"urn": urn, "count": limit})
        return [q.get("query", "") for q in result.get("queries", [])]

    def build_context(self, query: str, max_datasets: int = 8) -> CodeContext:
        search_results = self.search(query, limit=max_datasets)

        urns = []
        for r in search_results:
            urn = r.get("urn", r.get("entity", ""))
            if urn:
                urns.append(urn)

        if not urns:
            return CodeContext(datasets=[], request=query)

        entities = self.get_entities(urns)

        datasets = []
        for entity in entities:
            urn = entity.get("urn", "")
            ds = self._entity_to_dataset(urn, entity)

            fields = self.get_schema_fields(urn)
            ds.columns = [
                Column(
                    name=f.get("fieldPath", f.get("name", "")),
                    type=f.get("nativeDataType", f.get("type", "UNKNOWN")),
                    description=f.get("description", ""),
                    nullable=f.get("nullable", True),
                    tags=[t.get("name", "") for t in f.get("tags", [])],
                    glossary_terms=[t.get("name", "") for t in f.get("glossaryTerms", [])],
                )
                for f in fields
            ]

            ds.upstream = self.get_lineage(urn, "UPSTREAM")
            ds.downstream = self.get_lineage(urn, "DOWNSTREAM")
            ds.sample_queries = self.get_queries(urn)
            datasets.append(ds)

        return CodeContext(datasets=datasets, request=query)

    def _entity_to_dataset(self, urn: str, entity: dict) -> Dataset:
        platform = ""
        name = urn
        if "urn:li:dataPlatform:" in urn:
            parts = urn.split(",")
            if len(parts) >= 2:
                platform = parts[0].split("urn:li:dataPlatform:")[1] if "urn:li:dataPlatform:" in parts[0] else ""
                name = parts[1]

        props = entity.get("properties", entity.get("datasetProperties", {}))
        tags = [t.get("name", t.get("tag", "")) for t in entity.get("tags", [])]
        owners = [o.get("owner", "") for o in entity.get("owners", [])]
        terms = [t.get("name", "") for t in entity.get("glossaryTerms", [])]

        return Dataset(
            urn=urn,
            name=props.get("name", name),
            platform=platform,
            description=props.get("description", ""),
            tags=tags,
            owners=owners,
            glossary_terms=terms,
        )
