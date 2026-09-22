import { useCallback, useEffect, useMemo, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import CommitCell from "../common/CommitCell";
import CrudActionButton from "../common/CrudActionButton";
import ServerDataGrid from "../common/ServerDataGrid";
import {
  BrandRawRow,
  BrandRow,
  createBrandRaw,
  fetchBrandRaw,
  fetchBrands,
  updateBrandRaw,
} from "./pdbBrandsApi";


function NewBrandRawDialog({
  brand,
  open,
  saving,
  onClose,
  onSave,
}: {
  brand: string;
  open: boolean;
  saving: boolean;
  onClose: () => void;
  onSave: (value: string) => Promise<void>;
}) {
  const [value, setValue] = useState("");

  useEffect(() => {
    if (open) setValue("");
  }, [open]);

  return (
    <Dialog open={open} onClose={saving ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle>Aggiungi occorrenza brand_raw</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Brand: {brand}
        </Typography>
        <TextField
          autoFocus
          fullWidth
          required
          label="Brand raw"
          value={value}
          disabled={saving}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && value.trim() && !saving) {
              event.preventDefault();
              void onSave(value);
            }
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button disabled={saving} onClick={onClose}>Annulla</Button>
        <CrudActionButton
          crudAction="save"
          disabled={saving || !value.trim()}
          onClick={() => void onSave(value)}
        >
          {saving ? "Salvataggio..." : "Salva occorrenza"}
        </CrudActionButton>
      </DialogActions>
    </Dialog>
  );
}


export default function Brands() {
  const [selectedBrand, setSelectedBrand] = useState<BrandRow | null>(null);
  const [saving, setSaving] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const brandColumns = useMemo<GridColDef[]>(
    () => [
      { field: "brand", headerName: "Brand", flex: 1, minWidth: 220 },
      { field: "prefix", headerName: "Prefissi", flex: 1, minWidth: 180 },
    ],
    []
  );

  const handleBrandClick = useCallback((params: GridRowParams) => {
    setSelectedBrand(params.row as BrandRow);
    setError("");
    setSuccess("");
  }, []);

  const commitBrandRaw = useCallback(async (row: BrandRawRow, value: string) => {
    if (!selectedBrand) throw new Error("Selezionare un brand");
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await updateBrandRaw(row.record_key, selectedBrand.brand, value);
      setSuccess(`Modifica salvata in ${result.edits_file}.`);
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Salvataggio fallito");
      throw err;
    } finally {
      setSaving(false);
    }
  }, [selectedBrand]);

  const rawColumns = useMemo<GridColDef[]>(
    () => [
      {
        field: "change_status",
        headerName: "Stato",
        width: 110,
        sortable: false,
        renderCell: (params) => {
          if (params.value === "modified") {
            return <Chip size="small" label="Modificata" color="warning" variant="outlined" />;
          }
          if (params.value === "added") {
            return <Chip size="small" label="Nuova" color="success" variant="outlined" />;
          }
          return null;
        },
      },
      {
        field: "brand_raw",
        headerName: "Brand raw",
        flex: 1,
        minWidth: 220,
        sortable: false,
        renderCell: (params) => (
          <CommitCell
            value={params.value}
            label={`Brand raw ${params.row.record_key}`}
            disabled={saving}
            onCommit={(value) => commitBrandRaw(params.row as BrandRawRow, value)}
          />
        ),
      },
    ],
    [commitBrandRaw, saving]
  );

  const fetchSelectedBrandRaw = useCallback(
    (params: Parameters<typeof fetchBrandRaw>[1]) => {
      if (!selectedBrand) {
        return Promise.resolve({ rows: [], total: 0 });
      }
      return fetchBrandRaw(selectedBrand.brand, params);
    },
    [selectedBrand]
  );

  const prefixes = selectedBrand?.prefix
    ? selectedBrand.prefix.split(",").map((prefix) => prefix.trim()).filter(Boolean)
    : [];

  const saveNewBrandRaw = async (value: string) => {
    if (!selectedBrand || saving) return;
    setSaving(true);
    setError("");
    setSuccess("");
    try {
      const result = await createBrandRaw(selectedBrand.brand, value);
      setDialogOpen(false);
      setSuccess(`Nuova occorrenza salvata in ${result.edits_file}.`);
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Inserimento fallito");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Box
        sx={{
          height: "89vh",
          width: "100%",
          minHeight: 0,
          display: "grid",
          gridTemplateColumns: {
            xs: "minmax(0, 1fr)",
            lg: "minmax(460px, 3fr) minmax(360px, 2fr)",
          },
          gap: 1.5,
        }}
      >
      <ServerDataGrid
        title="Brands"
        columns={brandColumns}
        fetchRows={fetchBrands}
        getRowId={(row) => row.brand}
        filterFields={["brand", "prefix"]}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        height="100%"
        onRowClick={handleBrandClick}
        singleSelection
      />

      <Paper
        elevation={1}
        sx={{
          height: "100%",
          minHeight: 0,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          borderRadius: 1,
        }}
      >
        {selectedBrand ? (
          <>
            <Box
              sx={{
                px: 1.5,
                py: 1,
                borderBottom: "1px solid",
                borderColor: "divider",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="overline" color="text.secondary">
                    Scheda brand
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {selectedBrand.brand}
                  </Typography>
                </Box>
                <IconButton
                  aria-label="Chiudi scheda brand"
                  size="small"
                  onClick={() => setSelectedBrand(null)}
                >
                  ×
                </IconButton>
              </Box>
              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 0.75 }}>
                {prefixes.length > 0 ? (
                  prefixes.map((prefix) => (
                    <Chip key={prefix} label={prefix} size="small" variant="outlined" />
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Nessun prefisso associato
                  </Typography>
                )}
              </Box>
            </Box>

            <Box sx={{ flex: 1, minHeight: 0, p: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
              {success && <Alert severity="success" onClose={() => setSuccess("")}>{success}</Alert>}
              <Box sx={{ flex: 1, minHeight: 0 }}>
              <ServerDataGrid
                title="Occorrenze brand_raw"
                columns={rawColumns}
                fetchRows={fetchSelectedBrandRaw}
                getRowId={(row) => row.record_key}
                filterFields={["brand_raw"]}
                defaultPageSize={50}
                pageSizeOptions={[25, 50, 100, 500]}
                refreshToken={refreshToken}
                rowHeight={46}
                height="100%"
                emptyMessage="Nessuna occorrenza brand_raw"
                toolbarLeft={
                  <CrudActionButton
                    crudAction="add"
                    size="small"
                    disabled={saving}
                    onClick={() => setDialogOpen(true)}
                  >
                    Aggiungi occorrenza
                  </CrudActionButton>
                }
              />
              </Box>
            </Box>
          </>
        ) : (
          <Box
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              p: 3,
              textAlign: "center",
            }}
          >
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                Scheda brand
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Seleziona un brand dalla tabella per visualizzare tutte le occorrenze
                brand_raw associate.
              </Typography>
            </Box>
          </Box>
        )}
        </Paper>
      </Box>

      <NewBrandRawDialog
        brand={selectedBrand?.brand || ""}
        open={dialogOpen && Boolean(selectedBrand)}
        saving={saving}
        onClose={() => setDialogOpen(false)}
        onSave={saveNewBrandRaw}
      />
    </>
  );
}
