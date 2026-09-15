import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Autocomplete, Box, Checkbox, CircularProgress, FormControl, FormControlLabel, IconButton, InputLabel, ListItemText, MenuItem, Select, Switch, TextField, Tooltip } from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { ClipboardPaste, Copy, PanelBottom, RefreshCw } from "lucide-react";
import CommitCell from "../common/CommitCell";
import ServerDataGrid, { ServerGridFetchParams } from "../common/ServerDataGrid";
import { DatasetMetadata, DatasetName, fetchDatasetMetadata, fetchDatasetRows, saveItemValues } from "./itemsCodeApi";

const getRowId = (row: Record<string, any>) => row.__items_code_row_id;
const editKey = (row: Record<string, any>) => JSON.stringify([row.company, row.item_code]);
const pageSizes = [25, 50, 100, 250, 500, 1000];
const FULL_PDB = "- FULL PDB -";
const frozenNewItemColumns = [{ field: "__check__" }, { field: "company" }, { field: "item_code" }];
const isExtraColumn = (field: string) => field === "item_extra_descriptions" || field.startsWith("item_extra_descriptions.");

export type ReferenceSelection = { row: Record<string, any>; fields: string[] };

const EditContext = createContext<{
  saving: boolean;
  commit: (row: Record<string, any>, field: string, value: string, many: boolean) => Promise<void>;
} | null>(null);

function ItemEditCell({ row, field, value, label }: { row: Record<string, any>; field: string; value: unknown; label: string }) {
  const editing = useContext(EditContext)!;
  return <CommitCell value={value} label={label} disabled={editing.saving}
    onCommit={(value, many) => editing.commit(row, field, value, many)} />;
}

export default function DatasetTable({ dataset, title, requireCompany = false, referenceSelection, onReferenceSelection, referenceVisible, onReferenceVisibleChange }: {
  dataset: DatasetName; title: string; requireCompany?: boolean;
  referenceSelection?: ReferenceSelection | null;
  onReferenceSelection?: (selection: ReferenceSelection | null) => void;
  referenceVisible?: boolean;
  onReferenceVisibleChange?: (visible: boolean) => void;
}) {
  const [company, setCompany] = useState("");
  const effectiveCompany = dataset === "pdb" && company === FULL_PDB ? "" : company;
  const [metadata, setMetadata] = useState<DatasetMetadata | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);
  const [dataRefreshToken, setDataRefreshToken] = useState(0);
  const [showExtraColumns, setShowExtraColumns] = useState(true);
  const [selectedRows, setSelectedRows] = useState<Record<string, any>[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Record<string, any>>>({});
  const [excludedCopyFields, setExcludedCopyFields] = useState<string[]>([]);
  const [excludedPasteFields, setExcludedPasteFields] = useState<string[]>([]);
  const [clipboard, setClipboard] = useState<Record<string, any> | null>(null);
  const [visibleRows, setVisibleRows] = useState<Record<string, any>[]>([]);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const handleRowsChange = useCallback((rows: Record<string, any>[]) => setVisibleRows(rows), []);
  const editableFields = useMemo(() => {
    const available = metadata?.columns || [];
    return new Set(dataset === "new-items" ? available.filter((column) => column.editable).map((column) => column.field) : []);
  }, [dataset, metadata?.columns]);
  const pasteColumns = useMemo(() => {
    const available = metadata?.columns || [];
    const start = available.findIndex((column) => column.field === "father_name");
    return start >= 0 ? available.slice(start).filter((column) => editableFields.has(column.field)) : [];
  }, [metadata?.columns, editableFields]);
  const pasteFields = useMemo(() => pasteColumns.map((column) => column.field)
    .filter((field) => !excludedPasteFields.includes(field)), [pasteColumns, excludedPasteFields]);
  const copyColumns = useMemo(() => {
    const available = metadata?.columns || [];
    const start = available.findIndex((column) => column.field === "father_name");
    return dataset === "pdb" && start >= 0 ? available.slice(start).filter((column) => column.field !== "last_update") : [];
  }, [dataset, metadata?.columns]);
  const copyFields = useMemo(() => copyColumns.map((column) => column.field)
    .filter((field) => !excludedCopyFields.includes(field)), [copyColumns, excludedCopyFields]);
  const transformRow = useCallback((row: Record<string, any>) => ({ ...row, ...drafts[editKey(row)] }), [drafts]);
  const handleSelectionChange = useCallback((_: Set<number | string>, rows: Record<string, any>[]) => {
    setSelectedRows(rows);
  }, []);
  useEffect(() => {
    onReferenceSelection?.(selectedRows[0] ? { row: selectedRows[0], fields: copyFields } : null);
  }, [selectedRows, copyFields, onReferenceSelection]);
  const persistValues = useCallback(async (targets: Record<string, any>[], values: Record<string, any>) => {
    if (!targets.length || !Object.keys(values).length) return;
    if (savingRef.current) throw new Error("Attendere il salvataggio in corso");
    savingRef.current = true; setSaving(true); setError("");
    try {
      const result = await saveItemValues(company, [...new Set(targets.map((row) => String(row.item_code)))], values);
      setDrafts((current) => {
        const next = { ...current };
        targets.forEach((row) => { next[editKey(row)] = { ...next[editKey(row)], ...result.values }; });
        return next;
      });
      setDataRefreshToken((current) => current + 1);
    } catch (err: any) { setError(err.message); throw err; }
    finally { savingRef.current = false; setSaving(false); }
  }, [company]);
  const copyReference = async () => {
    if (!referenceSelection?.fields.length || !selectedRows.length) return;
    const values = Object.fromEntries(referenceSelection.fields.filter((field) => editableFields.has(field))
      .map((field) => [field, referenceSelection.row[field] ?? null]));
    await persistValues(selectedRows, values);
  };
  const pasteClipboard = async () => {
    if (!clipboard) return;
    await persistValues(selectedRows, Object.fromEntries(pasteFields.filter((field) => field in clipboard)
      .map((field) => [field, clipboard[field]])));
  };
  const editing = useMemo(() => ({ saving, commit: (row: Record<string, any>, field: string, value: string, many: boolean) =>
    persistValues(many ? [row, ...(selectedRows.length ? selectedRows : visibleRows)] : [row], { [field]: value })
  }), [saving, persistValues, selectedRows, visibleRows]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    fetchDatasetMetadata(dataset, effectiveCompany, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setMetadata(data); })
      .catch((err) => { if (err.name !== "AbortError") setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [dataset, effectiveCompany, refreshToken]);

  const columns = useMemo<GridColDef[]>(() => (metadata?.columns || []).map((column) => ({
    field: column.field, headerName: column.header_name, sortable: false,
    headerClassName: isExtraColumn(column.field) ? "items-code-extra-header" : undefined,
    width: column.field === "description" || column.field === "item_extra_descriptions" ? 360 : 185,
    minWidth: 120,
    renderCell: editableFields.has(column.field) ? (params) => <ItemEditCell value={params.value} row={params.row} field={column.field}
      label={`${column.header_name} ${params.row.company_item_code}`} /> : undefined,
    type: /^(DECIMAL|DOUBLE|FLOAT|BIGINT|INTEGER|SMALLINT)/.test(column.data_type) ? "number" : "string",
    valueFormatter: (value: unknown) => Array.isArray(value) ? value.join(" | ") : value && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
  })), [metadata?.columns, editableFields]);
  const columnVisibilityModel = useMemo(() => Object.fromEntries(
    (metadata?.columns || []).filter((column) => isExtraColumn(column.field))
      .map((column) => [column.field, column.field === "item_extra_descriptions" ? false : showExtraColumns])
  ), [metadata?.columns, showExtraColumns]);

  const fetchRows = useCallback((params: ServerGridFetchParams) => {
    if (!metadata?.available || (requireCompany && !company)) return Promise.resolve({ rows: [], total: 0 });
    return fetchDatasetRows(dataset, effectiveCompany, params);
  }, [dataset, company, effectiveCompany, metadata?.available, requireCompany]);

  return (
    <Box component="section" sx={{ minHeight: 0, minWidth: 0, height: "100%", display: "flex", flexDirection: "column",
      "& .MuiDataGrid-columnHeader.items-code-extra-header": { backgroundColor: "#d8eee8" },
    }}>
      {error && <Alert severity="error">{error}</Alert>}
      {metadata && !metadata.available && <Alert severity="warning">{metadata.message}</Alert>}
      <EditContext.Provider value={editing}><ServerDataGrid
        key={`${dataset}:${company}`} title={title} columns={columns} fetchRows={fetchRows}
        getRowId={getRowId} defaultPageSize={100} pageSizeOptions={pageSizes}
        height="100%" refreshToken={refreshToken + dataRefreshToken}
        selectionResetToken={refreshToken}
        externalPagination
        columnVisibilityModel={columnVisibilityModel}
        checkboxSelection={dataset === "new-items"}
        visibleRowsSelection={dataset === "new-items"}
        ctrlClickSelection={dataset === "new-items"}
        frozenColumns={dataset === "new-items" ? frozenNewItemColumns : undefined}
        singleSelection={dataset === "pdb"}
        onSelectionChange={handleSelectionChange}
        onRowsChange={handleRowsChange}
        transformRow={dataset === "new-items" ? transformRow : undefined}
        emptyMessage={loading ? "Caricamento..." : requireCompany && !company ? "Seleziona una Company" : "Nessun dato"}
        toolbarLeft={
          <>
          <Autocomplete size="small" options={dataset === "pdb" ? [FULL_PDB, ...(metadata?.companies || [])] : metadata?.companies || []} value={company || null} disabled={saving}
            onChange={(_, value) => { setDrafts({}); setSelectedRows([]); onReferenceSelection?.(null); setCompany(value || ""); }} loading={loading}
            sx={{ width: 280, maxWidth: "100%" }}
            renderInput={(params) => <TextField {...params} label={dataset === "pdb" ? "SELECT COMPANY" : requireCompany ? "Company" : "Company (tutte)"} />}
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
          {dataset === "new-items" && onReferenceVisibleChange && <FormControlLabel
            label={<Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}><PanelBottom size={18} />Reference PDB</Box>}
            control={<Switch size="small" checked={!!referenceVisible} onChange={(_, checked) => onReferenceVisibleChange(checked)} />} />}
          {dataset === "new-items" && <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <FormControl size="small" sx={{ width: 190 }}>
              <InputLabel shrink id="items-code-paste-fields-label">Campi da incollare</InputLabel>
              <Select multiple labelId="items-code-paste-fields-label" label="Campi da incollare" value={pasteFields}
                disabled={saving || !pasteColumns.length} displayEmpty
                renderValue={(selected) => `${selected.length} campi`}
                onChange={(event) => {
                  const selected = typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value;
                  setExcludedPasteFields(pasteColumns.map((column) => column.field).filter((field) => !selected.includes(field)));
                }} MenuProps={{ PaperProps: { sx: { maxHeight: 360 } } }}>
                {pasteColumns.map((column) => <MenuItem key={column.field} value={column.field}>
                  <Checkbox checked={pasteFields.includes(column.field)} tabIndex={-1} disableRipple />
                  <ListItemText primary={column.header_name} />
                </MenuItem>)}
              </Select>
            </FormControl>
            <Tooltip title="Copia caratteristiche della riga selezionata"><span>
              <IconButton aria-label="Copia caratteristiche" disabled={saving || selectedRows.length !== 1 || !pasteColumns.length}
                onClick={() => setClipboard(Object.fromEntries(pasteColumns.map((column) => [column.field, selectedRows[0][column.field] ?? null])))}>
                <Copy size={18} />
              </IconButton>
            </span></Tooltip>
            <Tooltip title="Incolla caratteristiche nelle righe selezionate"><span>
              <IconButton aria-label="Incolla caratteristiche" disabled={saving || !clipboard || !selectedRows.length || !pasteFields.length}
                onClick={() => { void pasteClipboard().catch(() => {}); }}><ClipboardPaste size={18} /></IconButton>
            </span></Tooltip>
            {saving && <CircularProgress size={18} aria-label="Salvataggio" />}
          </Box>}
          </>
        }
        toolbarRight={
          <>
          {dataset === "new-items" && <Tooltip title="Copia dal Reference PDB">
            <span><IconButton aria-label="Copia dal Reference PDB" disabled={saving || !selectedRows.length || !referenceSelection?.fields.length}
              onClick={() => { void copyReference().catch(() => {}); }}><Copy size={18} /></IconButton></span>
          </Tooltip>}
          <Tooltip title={`Aggiorna ${metadata?.source_file || title}`}>
            <IconButton disabled={saving} aria-label={`Aggiorna ${title}`} onClick={() => { setDrafts({}); setSelectedRows([]); onReferenceSelection?.(null); setRefreshToken((value) => value + 1); }}><RefreshCw size={18} /></IconButton>
          </Tooltip>
          </>
        }
      /></EditContext.Provider>
    </Box>
  );
}
