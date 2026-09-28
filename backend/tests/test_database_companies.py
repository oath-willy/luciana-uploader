from types import SimpleNamespace
from unittest.mock import patch

from api.db import database_tables as tables


class _Result:
    def __init__(self, rows=None, scalar_value=None, rowcount=-1):
        self._rows = rows or []
        self._scalar_value = scalar_value
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar_value


class _FakeCompanySession:
    def __init__(self):
        self.calls = []
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params or {}))
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            return _Result(rows=[("id",), ("company_name",), ("manufacturer",),
                                ("dealer",), ("description",), ("note",)])
        if "COUNT(*)" in sql:
            return _Result(scalar_value=1)
        if "UPDATE dbo.companies" in sql:
            return _Result(rowcount=1)
        return _Result(rows=[SimpleNamespace(_mapping={
            "id_company": 7,
            "company": "ACME",
            "manufacturer": True,
            "dealer": False,
            "decription": "Dental manufacturer",
            "note": "Priority account",
        })])

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def close(self):
        self.closed = True


def test_company_search_uses_dedicated_dev_session_and_returns_detail_fields():
    db = _FakeCompanySession()
    request = tables.TableSearchRequest(page=0, page_size=50)

    with patch.object(tables, "CompaniesSessionLocal", return_value=db), \
         patch.object(tables, "DatabaseSessionLocal") as dictionary_session:
        result = tables.search_database_table("companies", request)

    dictionary_session.assert_not_called()
    assert result["total"] == 1
    assert result["rows"][0]["decription"] == "Dental manufacturer"
    assert result["rows"][0]["note"] == "Priority account"
    rows_sql = next(sql for sql, _ in db.calls if "OFFSET" in sql)
    assert "[id] AS id_company" in rows_sql
    assert "[company_name] AS company" in rows_sql
    assert db.closed


def test_company_update_writes_all_detail_fields_through_dev_session():
    db = _FakeCompanySession()
    request = tables.CompanyUpdateRequest(items=[tables.CompanyUpdateItem(
        id_company=7,
        company="ACME updated",
        manufacturer=True,
        dealer=True,
        decription="Updated description",
        note="Updated note",
    )])

    with patch.object(tables, "CompaniesSessionLocal", return_value=db), \
         patch.object(tables, "DatabaseSessionLocal") as dictionary_session:
        result = tables.update_companies(request)

    dictionary_session.assert_not_called()
    assert result == {"updated": 1}
    update_sql, update_params = next(
        (sql, params) for sql, params in db.calls if "UPDATE dbo.companies" in sql
    )
    assert "[description] = :decription" in update_sql
    assert "[note] = :note" in update_sql
    assert "WHERE [id] = :id_company" in update_sql
    assert update_params["decription"] == "Updated description"
    assert update_params["note"] == "Updated note"
    assert db.closed
