import time
from dataclasses import dataclass
from typing import Any

import requests
from azure.identity import DefaultAzureCredential


DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELED", "CLOSED"}
DEFAULT_CREDENTIAL = DefaultAzureCredential(
    exclude_interactive_browser_credential=True
)


class DatabricksStatementError(RuntimeError):
    pass


@dataclass(frozen=True)
class StatementParameter:
    name: str
    value: Any
    type: str = "STRING"


class DatabricksStatementClient:
    def __init__(
        self,
        host: str,
        warehouse_id: str,
        catalog: str,
        schema: str,
        credential: DefaultAzureCredential | None = None,
    ):
        self.host = host.rstrip("/")
        self.warehouse_id = warehouse_id
        self.catalog = catalog
        self.schema = schema
        self.credential = credential or DEFAULT_CREDENTIAL

    def execute(
        self,
        statement: str,
        parameters: list[StatementParameter] | None = None,
        timeout_seconds: int = 90,
    ) -> list[dict[str, Any]]:
        payload = {
            "warehouse_id": self.warehouse_id,
            "catalog": self.catalog,
            "schema": self.schema,
            "statement": statement,
            "parameters": [
                {
                    "name": parameter.name,
                    "value": str(parameter.value),
                    "type": parameter.type,
                }
                for parameter in (parameters or [])
            ],
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "disposition": "INLINE",
            "format": "JSON_ARRAY",
        }

        response = self._request("POST", "/api/2.0/sql/statements", json=payload)
        statement_id = response.get("statement_id")
        deadline = time.monotonic() + timeout_seconds

        while self._state(response) not in TERMINAL_STATES:
            if not statement_id or time.monotonic() >= deadline:
                self._cancel(statement_id)
                raise DatabricksStatementError(
                    "Timeout durante l'esecuzione della query Databricks"
                )
            time.sleep(1)
            response = self._request(
                "GET", f"/api/2.0/sql/statements/{statement_id}"
            )

        state = self._state(response)
        if state != "SUCCEEDED":
            error = response.get("status", {}).get("error", {})
            message = error.get("message") or f"Query Databricks terminata con stato {state}"
            raise DatabricksStatementError(message)

        return self._rows(response)

    def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.host}{path}"
        token = self.credential.get_token(DATABRICKS_SCOPE)
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=60,
                **kwargs,
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            suffix = f" (HTTP {status})" if status else ""
            raise DatabricksStatementError(
                f"Databricks non raggiungibile{suffix}"
            ) from exc

    def _cancel(self, statement_id: str | None) -> None:
        if not statement_id:
            return
        try:
            self._request(
                "POST", f"/api/2.0/sql/statements/{statement_id}/cancel"
            )
        except DatabricksStatementError:
            pass

    @staticmethod
    def _state(response: dict[str, Any]) -> str:
        return response.get("status", {}).get("state", "")

    def _rows(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        manifest = response.get("manifest", {})
        columns = manifest.get("schema", {}).get("columns", [])
        names = [column["name"] for column in columns]
        types = [column.get("type_name", "STRING") for column in columns]

        result = response.get("result") or {}
        raw_rows = list(result.get("data_array") or [])
        next_link = result.get("next_chunk_internal_link")

        while next_link:
            chunk = self._request("GET", next_link)
            raw_rows.extend(chunk.get("data_array") or [])
            next_link = chunk.get("next_chunk_internal_link")

        return [
            {
                name: self._convert_value(value, type_name)
                for name, type_name, value in zip(names, types, raw_row)
            }
            for raw_row in raw_rows
        ]

    @staticmethod
    def _convert_value(value: Any, type_name: str) -> Any:
        if value is None:
            return None
        if type_name in {"BYTE", "SHORT", "INT", "LONG"}:
            return int(value)
        if type_name in {"FLOAT", "DOUBLE", "DECIMAL"}:
            return float(value)
        if type_name == "BOOLEAN":
            return str(value).lower() == "true"
        return value
