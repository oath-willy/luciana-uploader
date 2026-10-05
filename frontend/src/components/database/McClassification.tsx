import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  Tooltip,
} from "@mui/material";
import { GridColDef } from "@mui/x-data-grid";
import { Plus, RefreshCw } from "lucide-react";
import CommitCell from "../common/CommitCell";
import ServerDataGrid, { ServerGridFetchParams } from "../common/ServerDataGrid";
import {
  ClassificationColumn,
  ClassificationMetadata,
  createClassificationRecord,
  fetchClassificationMetadata,
  fetchClassificationRows,
  updateClassificationRecord,
} from "./pdbMcClassificationApi";


const pageSizes = [25, 50, 100, 250, 500, 1000];

function fieldWidth(field: string) {
  if (field === "master_code") return 150;
  if (field === "mc_desc") return 480;
  return 260;
}

function NewRecordDialog({
  open,
  columns,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  columns: ClassificationColumn[];
  saving: boolean;
  onClose: () => void;
  onSave: (values: Record<string, string>) => Promise<void>;
}) {
  const [values, setValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (open) setValues({});
  }, [open]);

  const masterCode = (values.master_code || "").trim();
  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="md">
      <DialogTitle>Aggiungi riga MC Classification</DialogTitle>
      <DialogContent dividers>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
            gap: 2,
            pt: 0.5,
          }}
        >
          {columns.map((column) => (
            <TextField
              key={column.field}
              label={column.header_name}
              value={values[column.field] || ""}
              required={column.field === "master_code"}
              disabled={saving}
              multiline={column.field === "mc_desc"}
              minRows={column.field === "mc_desc" ? 3 : undefined}
              helperText={
                column.field === "master_code"
                  ? "Formato 00_00_00; dopo il salvataggio resta la chiave del record."
                  : undefined
              }
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  [column.field]: event.target.value,
                }))
              }
              sx={column.field === "mc_desc" ? { gridColumn: { md: "1 / -1" } } : undefined}
            />
          ))}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button disabled={saving} onClick={onClose}>Annulla</Button>
        <Button
          variant="contained"
          disabled={saving || !masterCode}
          onClick={() => void onSave(values)}
          startIcon={saving ? <CircularProgress size={16} /> : undefined}
        >
          Salva riga
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function McClassification() {
  const [metadata, setMetadata] = useState<ClassificationMetadata | null>(null);
  const [family, setFamily] = useState("");
  const [subfamily, setSubfamily] = useState("");
  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const loadMetadata = useCallback(async (signal?: AbortSignal) => {
    setLoadingMetadata(true);
    try {
      const result = await fetchClassificationMetadata(signal);
      if (signal?.aborted) return;
      setMetadata(result);
      setError("");
    } catch (err: any) {
      if (err.name !== "AbortError") setError(err.message || "Errore caricamento metadati");
    } finally {
      if (!signal?.aborted) setLoadingMetadata(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadMetadata(controller.signal);
    return () => controller.abort();
  }, [loadMetadata]);

  const availableSubfamilies = useMemo(
    () => family
      ? metadata?.subfamilies_by_family[family] || []
      : metadata?.subfamilies || [],
    [family, metadata]
  );

  const refresh = useCallback(async () => {
    setSuccess("");
    await loadMetadata();
    setRefreshToken((current) => current + 1);
  }, [loadMetadata]);

  const commit = useCallback(async (
    row: Record<string, any>,
    field: string,
    value: string
  ) => {
    if (saving) throw new Error("Attendere il salvataggio in corso");
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await updateClassificationRecord(row.master_code, { [field]: value });
      setSuccess(`Modifica salvata in ${result.runtime_file}.`);
      await loadMetadata();
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Salvataggio fallito");
      throw err;
    } finally {
      setSaving(false);
    }
  }, [loadMetadata, saving]);

  const columns = useMemo<GridColDef[]>(() => {
    const status: GridColDef = {
      field: "__change_status",
      headerName: "Stato",
      width: 105,
      minWidth: 105,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        if (params.value === "modified") return <Chip size="small" label="Modificata" color="warning" variant="outlined" />;
        if (params.value === "added") return <Chip size="small" label="Nuova" color="success" variant="outlined" />;
        return null;
      },
    };
    const dataColumns = (metadata?.columns || []).map<GridColDef>((column) => ({
      field: column.field,
      headerName: column.header_name,
      width: fieldWidth(column.field),
      minWidth: 130,
      sortable: false,
      renderCell: column.editable
        ? (params) => (
            <CommitCell
              value={params.value}
              label={`${column.header_name} ${params.row.master_code}`}
              disabled={saving}
              onCommit={(value) => commit(params.row, column.field, value)}
            />
          )
        : undefined,
      valueFormatter: (value: unknown) => String(value ?? ""),
    }));
    return [status, ...dataColumns];
  }, [commit, metadata?.columns, saving]);

  const fetchRows = useCallback((params: ServerGridFetchParams) => {
    if (!metadata?.available) return Promise.resolve({ rows: [], total: 0 });
    return fetchClassificationRows(params, family, subfamily);
  }, [family, metadata?.available, subfamily]);

  const saveNewRecord = async (values: Record<string, string>) => {
    if (saving) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await createClassificationRecord(values);
      setDialogOpen(false);
      setSuccess(`Nuova riga salvata in ${result.runtime_file}.`);
      await loadMetadata();
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Inserimento fallito");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box sx={{ height: "89vh", minHeight: 0, display: "flex", flexDirection: "column", gap: 1 }}>
      {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
      {success && <Alert severity="success" onClose={() => setSuccess("")}>{success}</Alert>}
      {metadata && !metadata.available && <Alert severity="warning">{metadata.message}</Alert>}

      <Box sx={{ flex: 1, minHeight: 0 }}>
        <ServerDataGrid
          key={`${family}:${subfamily}`}
          title="MC Classification"
          columns={columns}
          fetchRows={fetchRows}
          getRowId={(row) => row.__mc_classification_row_id}
          filterFields={(metadata?.columns || []).map((column) => column.field)}
          defaultPageSize={100}
          pageSizeOptions={pageSizes}
          refreshToken={refreshToken}
          height="100%"
          emptyMessage={loadingMetadata ? "Caricamento..." : "Nessun dato"}
          toolbarLeft={
            <>
              <Autocomplete
                size="small"
                options={metadata?.families || []}
                value={family || null}
                disabled={loadingMetadata || !metadata?.available}
                onChange={(_, value) => {
                  const nextFamily = value || "";
                  setFamily(nextFamily);
                  if (subfamily && nextFamily && !(metadata?.subfamilies_by_family[nextFamily] || []).includes(subfamily)) {
                    setSubfamily("");
                  }
                }}
                sx={{ width: 250, maxWidth: "100%" }}
                renderInput={(params) => <TextField {...params} label="Famiglia" />}
              />
              <Autocomplete
                size="small"
                options={availableSubfamilies}
                value={subfamily || null}
                disabled={loadingMetadata || !metadata?.available}
                onChange={(_, value) => setSubfamily(value || "")}
                sx={{ width: 250, maxWidth: "100%" }}
                renderInput={(params) => <TextField {...params} label="Sottofamiglia" />}
              />
            </>
          }
          toolbarRight={
            <>
              <Button
                variant="contained"
                size="small"
                startIcon={<Plus size={17} />}
                disabled={loadingMetadata || saving || !metadata?.available}
                onClick={() => setDialogOpen(true)}
              >
                Aggiungi riga
              </Button>
              <Tooltip title="Aggiorna MC Classification">
                <span>
                  <IconButton
                    aria-label="Aggiorna MC Classification"
                    disabled={loadingMetadata || saving}
                    onClick={() => void refresh()}
                  >
                    <RefreshCw size={18} />
                  </IconButton>
                </span>
              </Tooltip>
              {saving && <CircularProgress size={18} aria-label="Salvataggio" />}
            </>
          }
        />
      </Box>

      <NewRecordDialog
        open={dialogOpen}
        columns={metadata?.columns || []}
        saving={saving}
        onClose={() => setDialogOpen(false)}
        onSave={saveNewRecord}
      />
    </Box>
  );
}
