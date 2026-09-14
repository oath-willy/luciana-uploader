import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Autocomplete, Box, IconButton, TextField, Tooltip } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { RefreshCw } from "lucide-react";
import ServerDataGrid, { ServerGridFetchParams } from "../common/ServerDataGrid";
import { DatasetMetadata, DatasetName, fetchDatasetMetadata, fetchDatasetRows } from "./itemsCodeApi";

const getRowId = (row: Record<string, any>) => row.__items_code_row_id;
const pageSizes = [25, 50, 100, 250, 500, 1000];

export default function DatasetTable({ dataset, title, requireCompany = false }: {
  dataset: DatasetName; title: string; requireCompany?: boolean;
}) {
  const [company, setCompany] = useState("");
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchDatasetMetadata(dataset, company, controller.signal)
      .then(setMetadata)
      .catch((err) => { if (err.name !== "AbortError") setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [dataset, company, refreshToken]);

  const columns = useMemo<GridColDef[]>(() => (metadata?.columns || []).map((column) => ({
    field: column.field, headerName: column.header_name, sortable: false,
    width: column.field === "description" || column.field === "item_extra_descriptions" ? 360 : 185,
    minWidth: 120,
    type: /^(DECIMAL|DOUBLE|FLOAT|BIGINT|INTEGER|SMALLINT)/.test(column.data_type) ? "number" : "string",
    valueFormatter: (value: unknown) => Array.isArray(value) ? value.join(" | ") : value && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
  })), [metadata?.columns]);

  const fetchRows = useCallback((params: ServerGridFetchParams) => {
    if (!metadata?.available || (requireCompany && !company)) return Promise.resolve({ rows: [], total: 0 });
    return fetchDatasetRows(dataset, company, params);
  }, [dataset, company, metadata?.available, requireCompany]);

  return (
    <Box component="section" sx={{ minHeight: 0, minWidth: 0, height: "100%", display: "flex", flexDirection: "column" }}>
      {error && <Alert severity="error">{error}</Alert>}
      {metadata && !metadata.available && <Alert severity="warning">{metadata.message}</Alert>}
      <ServerDataGrid
        key={`${dataset}:${company}`} title={title} columns={columns} fetchRows={fetchRows}
        getRowId={getRowId} defaultPageSize={100} pageSizeOptions={pageSizes}
        height="100%" refreshToken={refreshToken}
        externalPagination
        emptyMessage={loading ? "Caricamento..." : requireCompany && !company ? "Seleziona una Company" : "Nessun dato"}
        toolbarLeft={
          <Autocomplete size="small" options={metadata?.companies || []} value={company || null}
            onChange={(_, value) => setCompany(value || "")} loading={loading}
            sx={{ width: 280, maxWidth: "100%" }}
            renderInput={(params) => <TextField {...params} label={requireCompany ? "Company" : "Company (tutte)"} />}
          />
        }
        toolbarRight={
          <Tooltip title={`Aggiorna ${metadata?.source_file || title}`}>
            <IconButton aria-label={`Aggiorna ${title}`} onClick={() => setRefreshToken((value) => value + 1)}><RefreshCw size={18} /></IconButton>
          </Tooltip>
        }
      />
    </Box>
  );
}
