import { useMemo, useState } from "react";
import { GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import { Alert, Box, Button, Checkbox, TextField } from "@mui/material";
import ServerDataGrid from "../common/ServerDataGrid";
import { backendBaseUrl, fetchDatabaseTable } from "./databaseApi";

type CompanyRow = {
  id_company: number;
  company: string;
  manufacturer: boolean;
  dealer: boolean;
};

type CompanyEdit = {
  company: string;
  manufacturer: boolean;
  dealer: boolean;
};

export default function Companies() {
  const [edits, setEdits] = useState<Record<number, CompanyEdit>>({});
  const [refreshToken, setRefreshToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const updateEdit = (row: CompanyRow, patch: Partial<CompanyEdit>) => {
    setEdits((current) => {
      const base = current[row.id_company] ?? {
        company: row.company || "",
        manufacturer: Boolean(row.manufacturer),
        dealer: Boolean(row.dealer),
      };

      return {
        ...current,
        [row.id_company]: {
          ...base,
          ...patch,
        },
      };
    });
  };

  const saveChanges = async () => {
    const items = Object.entries(edits).map(([id, edit]) => ({
      id_company: Number(id),
      company: edit.company,
      manufacturer: edit.manufacturer,
      dealer: edit.dealer,
    }));

    if (items.length === 0) {
      setError("Nessuna modifica da salvare.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`${backendBaseUrl}/api/database/companies/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore salvataggio companies");
      }

      const data = await response.json();
      setMessage(`${data.updated} companies aggiornate`);
      setEdits({});
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  };

  const columns = useMemo<GridColDef[]>(
    () => [
      { field: "id_company", headerName: "ID", width: 90 },
      {
        field: "company",
        headerName: "Company",
        width: 320,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CompanyRow>) => {
          const row = params.row;
          const value = edits[row.id_company]?.company ?? row.company ?? "";

          return (
            <TextField
              size="small"
              value={value}
              onChange={(event) => updateEdit(row, { company: event.target.value })}
              sx={{ width: "100%" }}
            />
          );
        },
      },
      {
        field: "manufacturer",
        headerName: "Manufacturer",
        width: 160,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CompanyRow>) => {
          const row = params.row;
          const checked = edits[row.id_company]?.manufacturer ?? Boolean(row.manufacturer);

          return (
            <Checkbox
              checked={checked}
              onChange={(event) =>
                updateEdit(row, { manufacturer: event.target.checked })
              }
            />
          );
        },
      },
      {
        field: "dealer",
        headerName: "Dealer",
        width: 130,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CompanyRow>) => {
          const row = params.row;
          const checked = edits[row.id_company]?.dealer ?? Boolean(row.dealer);

          return (
            <Checkbox
              checked={checked}
              onChange={(event) => updateEdit(row, { dealer: event.target.checked })}
            />
          );
        },
      },
    ],
    [edits]
  );

  return (
    <Box sx={{ height: "89vh", width: "100%" }}>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}
      {message && (
        <Alert severity="success" sx={{ mb: 1 }}>
          {message}
        </Alert>
      )}
      <ServerDataGrid
        title="Companies"
        columns={columns}
        fetchRows={(params) => fetchDatabaseTable("companies", params)}
        getRowId={(row) => row.id_company}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        refreshToken={refreshToken}
        rowHeight={46}
        toolbarLeft={
          <Button
            variant="contained"
            onClick={saveChanges}
            disabled={saving || Object.keys(edits).length === 0}
          >
            {saving ? "Saving..." : "Save changes"}
          </Button>
        }
      />
    </Box>
  );
}
