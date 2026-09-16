"""TogoMCP client restricted to PubCaseFinder evidence tools."""

import json
import os
import re

import requests


DEFAULT_BASE_URL = "https://togomcp.rdfportal.org/mcp"
ALLOWED_TOOLS = {
    "pubcasefinder_rank_by_phenotypes",
    "pubcasefinder_get_case_reports",
}


def get_base_url():
    return (os.environ.get("TOGOMCP_BASE_URL") or DEFAULT_BASE_URL).strip()


def extract_hpo_ids(values):
    """Return unique canonical HPO IDs from strings such as case phenotypes."""
    text = " ".join(str(value or "") for value in values)
    matches = re.findall(r"HP:\d{7}", text, re.IGNORECASE)
    return list(dict.fromkeys(match.upper() for match in matches))


def _response_payload(response):
    response.raise_for_status()
    if "text/event-stream" not in response.headers.get("Content-Type", ""):
        return response.json()
    for line in response.content.decode("utf-8").splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise RuntimeError("TogoMCP returned an empty event stream.")


class _McpSession:
    def __init__(self):
        self.http = requests.Session()
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        self.request_id = 0

    def __enter__(self):
        payload = self._request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "ExpertBoard", "version": "0.1"},
            },
        )
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "TogoMCP initialization failed."))
        session_id = self.last_response.headers.get("Mcp-Session-Id")
        if session_id:
            self.headers["Mcp-Session-Id"] = session_id
        self.last_response = self.http.post(
            get_base_url(),
            headers=self.headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            timeout=30,
        )
        self.last_response.raise_for_status()
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        if "Mcp-Session-Id" in self.headers:
            try:
                self.http.delete(get_base_url(), headers=self.headers, timeout=10)
            except requests.RequestException:
                pass
        self.http.close()

    def _request(self, method, params):
        self.request_id += 1
        self.last_response = self.http.post(
            get_base_url(),
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params,
            },
            timeout=90,
        )
        return _response_payload(self.last_response)

    def call_tool(self, tool_name, arguments):
        if tool_name not in ALLOWED_TOOLS:
            raise ValueError(f"TogoMCP tool is not allowed: {tool_name}")
        payload = self._request(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", f"{tool_name} failed"))
        result = payload.get("result") or {}
        text = "\n".join(
            block.get("text", "")
            for block in result.get("content", [])
            if block.get("type") == "text"
        )
        if result.get("isError"):
            raise RuntimeError(text or f"{tool_name} failed")
        return json.loads(text)


def collect_pubcasefinder_evidence(phenotypes, rank_limit=10, report_limit=10):
    hpo_ids = extract_hpo_ids(phenotypes)
    if not hpo_ids:
        raise ValueError("No valid HPO IDs were found. Expected values such as HP:0001250.")

    try:
        with _McpSession() as client:
            ranking = client.call_tool(
                "pubcasefinder_rank_by_phenotypes",
                {"hpo_ids": hpo_ids, "target": "omim", "limit": rank_limit},
            )
            case_reports = None
            report_disease = None
            for candidate in ranking.get("results", []):
                mondo_ids = candidate.get("mondo_ids") or []
                if mondo_ids:
                    report_disease = candidate
                    case_reports = client.call_tool(
                        "pubcasefinder_get_case_reports",
                        {"mondo_id": mondo_ids[0], "lang": "en", "limit": report_limit},
                    )
                    break
    except requests.RequestException as exc:
        raise RuntimeError(f"TogoMCP request failed: {exc}") from exc

    return {
        "source": "TogoMCP / PubCaseFinder",
        "hpo_ids": hpo_ids,
        "ranking": ranking,
        "case_report_disease": report_disease,
        "case_reports": case_reports,
    }


def collect_pubcasefinder_gene_ranking(
    phenotypes, rank_limit=50, disease_limit=100
):
    """Rank phenotype-associated genes and fetch related disease context."""
    hpo_ids = extract_hpo_ids(phenotypes)
    if not hpo_ids:
        raise ValueError("No confirmed HPO IDs are available for gene ranking.")

    try:
        with _McpSession() as client:
            ranking = client.call_tool(
                "pubcasefinder_rank_by_phenotypes",
                {"hpo_ids": hpo_ids, "target": "gene", "limit": rank_limit},
            )
            disease_ranking = client.call_tool(
                "pubcasefinder_rank_by_phenotypes",
                {"hpo_ids": hpo_ids, "target": "omim", "limit": disease_limit},
            )
    except requests.RequestException as exc:
        raise RuntimeError(f"TogoMCP request failed: {exc}") from exc

    return {
        "source": "TogoMCP / PubCaseFinder",
        "hpo_ids": hpo_ids,
        "ranking": ranking,
        "disease_ranking": disease_ranking,
    }


def collect_pubcasefinder_disease_ranking(phenotypes, rank_limit=10):
    """Rank phenotype-associated diseases, including inheritance modes."""
    hpo_ids = extract_hpo_ids(phenotypes)
    if not hpo_ids:
        raise ValueError("No confirmed HPO IDs are available for disease ranking.")

    try:
        with _McpSession() as client:
            ranking = client.call_tool(
                "pubcasefinder_rank_by_phenotypes",
                {"hpo_ids": hpo_ids, "target": "omim", "limit": rank_limit},
            )
    except requests.RequestException as exc:
        raise RuntimeError(f"TogoMCP request failed: {exc}") from exc

    return {
        "source": "TogoMCP / PubCaseFinder",
        "hpo_ids": hpo_ids,
        "ranking": ranking,
    }