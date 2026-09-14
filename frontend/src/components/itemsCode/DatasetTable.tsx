import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Autocomplete, Box, Checkbox, FormControl, FormControlLabel, IconButton, InputLabel, ListItemText, MenuItem, Select, Switch, TextField, Tooltip } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { Copy, RefreshCw } from "lucide-react";
import ServerDataGrid, { ServerGridFetchParams } from "../common/ServerDataGrid";
import { DatasetMetadata, DatasetName, fetchDatasetMetadata, fetchDatasetRows } from "./itemsCodeApi";

const getRowId = (row: Record<string, any>) => row.__items_code_row_id;
const pageSizes = [25, 50, 100, 250, 500, 1000];
const isExtraColumn = (field: string) => field === "item_extra_descriptions" || field.startsWith("item_extra_descriptions.");

export type ReferenceSelection = { row: Record<string, any>; fields: string[] };

export default function DatasetTable({ dataset, title, requireCompany = false, referenceSelection, onReferenceSelection }: {
  dataset: DatasetName; title: string; requireCompany?: boolean;
  referenceSelection?: ReferenceSelection | null;
  onReferenceSelection?: (selection: ReferenceSelection | null) => void;
}) {
  const [company, setCompany] = useState("");
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);
  const [showExtraColumns, setShowExtraColumns] = useState(true);
  const [selectedRows, setSelectedRows] = useState<Record<string, any>[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Record<string, any>>>({});
  const [excludedCopyFields, setExcludedCopyFields] = useState<string[]>([]);
  const copyColumns = useMemo(() => {
    const available = metadata?.columns || [];
    const start = available.findIndex((column) => column.field === "father_name");
    return dataset === "pdb" && start >= 0 ? available.slice(start).filter((column) => column.field !== "last_update") : [];
  }, [dataset, metadata?.columns]);
  const copyFields = useMemo(() => copyColumns.map((column) => column.field)
    .filter((field) => !excludedCopyFields.includes(field)), [copyColumns, excludedCopyFields]);
  const transformRow = useCallback((row: Record<string, any>) => ({ ...row, ...drafts[getRowId(row)] }), [drafts]);
  const handleSelectionChange = useCallback((_: Set<number | string>, rows: Record<string, any>[]) => {
    setSelectedRows(rows);
  }, []);
  useEffect(() => {
    onReferenceSelection?.(selectedRows[0] ? { row: selectedRows[0], fields: copyFields } : null);
  }, [selectedRows, copyFields, onReferenceSelection]);
  const copyReference = () => {
    if (!referenceSelection?.fields.length || !selectedRows.length) return;
    const targetFields = new Set(metadata?.columns.map((column) => column.field));
    const values = Object.fromEntries(referenceSelection.fields.filter((field) => targetFields.has(field))
      .map((field) => [field, referenceSelection.row[field] ?? null]));
    setDrafts((current) => {
      const next = { ...current };
      selectedRows.forEach((row) => { next[getRowId(row)] = { ...next[getRowId(row)], ...values }; });
      return next;
    });
  };

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
    headerClassName: isExtraColumn(column.field) ? "items-code-extra-header" : undefined,
    width: column.field === "description" || column.field === "item_extra_descriptions" ? 360 : 185,
    minWidth: 120,
    type: /^(DECIMAL|DOUBLE|FLOAT|BIGINT|INTEGER|SMALLINT)/.test(column.data_type) ? "number" : "string",
    valueFormatter: (value: unknown) => Array.isArray(value) ? value.join(" | ") : value && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
  })), [metadata?.columns]);
  const columnVisibilityModel = useMemo(() => Object.fromEntries(
    (metadata?.columns || []).filter((column) => isExtraColumn(column.field))
      .map((column) => [column.field, column.field === "item_extra_descriptions" ? false : showExtraColumns])
  ), [metadata?.columns, showExtraColumns]);

  const fetchRows = useCallback((params: ServerGridFetchParams) => {
    if (!metadata?.available || (requireCompany && !company)) return Promise.resolve({ rows: [], total: 0 });
    return fetchDatasetRows(dataset, company, params);
  }, [dataset, company, metadata?.available, requireCompany]);

  return (
    <Box component="section" sx={{ minHeight: 0, minWidth: 0, height: "100%", display: "flex", flexDirection: "column",
      "& .MuiDataGrid-columnHeader.items-code-extra-header": { backgroundColor: "#d8eee8" },
    }}>
      {error && <Alert severity="error">{error}</Alert>}
      {metadata && !metadata.available && <Alert severity="warning">{metadata.message}</Alert>}
      <ServerDataGrid
        key={`${dataset}:${company}`} title={title} columns={columns} fetchRows={fetchRows}
        getRowId={getRowId} defaultPageSize={100} pageSizeOptions={pageSizes}
        height="100%" refreshToken={refreshToken}
        selectionResetToken={refreshToken}
        externalPagination
        columnVisibilityModel={columnVisibilityModel}
        checkboxSelection={dataset === "new-items"}
        visibleRowsSelection={dataset === "new-items"}
        singleSelection={dataset === "pdb"}
        onSelectionChange={handleSelectionChange}
        transformRow={dataset === "new-items" ? transformRow : undefined}
        emptyMessage={loading ? "Caricamento..." : requireCompany && !company ? "Seleziona una Company" : "Nessun dato"}
        toolbarLeft={
          <>
          <Autocomplete size="small" options={metadata?.companies || []} value={company || null}
            onChange={(_, value) => { setDrafts({}); setSelectedRows([]); onReferenceSelection?.(null); setCompany(value || ""); }} loading={loading}
            sx={{ width: 280, maxWidth: "100%" }}
            renderInput={(params) => <TextField {...params} label={requireCompany ? "Company" : "Company (tutte)"} />}
          />
          {dataset === "pdb" && <FormControl size="small" sx={{ width: 230, maxWidth: "100%" }}>
            <InputLabel shrink id="items-code-copy-fields-label">Campi da copiare</InputLabel>
            <Select multiple labelId="items-code-copy-fields-label" label="Campi da copiare"
              value={copyFields} disabled={loading || !copyColumns.length}
              renderValue={(selected) => `${selected.length} campi selezionati`}
              displayEmpty
              onChange={(event) => {
                const selected = typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value;
                setExcludedCopyFields(copyColumns.map((column) => column.field).filter((field) => !selected.includes(field)));
              }}
              MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}>
              {copyColumns.map((column) => <MenuItem key={column.field} value={column.field}>
                <Checkbox checked={copyFields.includes(column.field)} tabIndex={-1} disableRipple />
                <ListItemText primary={column.header_name} />
              </MenuItem>)}
            </Select>
          </FormControl>}
          {dataset === "new-items" && <FormControlLabel label="Colonne extra" control={
            <Switch size="small" checked={showExtraColumns} onChange={(_, checked) => setShowExtraColumns(checked)} />
          } />}
          </>
        }
        toolbarRight={
          <>
          {dataset === "new-items" && <Tooltip title="Copy">
            <span><IconButton aria-label="Copy" disabled={!selectedRows.length || !referenceSelection?.fields.length}
              onClick={copyReference}><Copy size={18} /></IconButton></span>
          </Tooltip>}
          <Tooltip title={`Aggiorna ${metadata?.source_file || title}`}>
            <IconButton aria-label={`Aggiorna ${title}`} onClick={() => { setDrafts({}); setSelectedRows([]); onReferenceSelection?.(null); setRefreshToken((value) => value + 1); }}><RefreshCw size={18} /></IconButton>
          </Tooltip>
          </>
        }
      />
    </Box>
  );
}
