import { useCallback, useMemo, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import {
  Alert,
  Box,
  Checkbox,
  Chip,
  FormControlLabel,
  IconButton,
  Paper,
  TextField,
  Typography,
} from "@mui/material";
import CrudActionButton from "../common/CrudActionButton";
import ServerDataGrid from "../common/ServerDataGrid";
import { backendBaseUrl, fetchDatabaseTable } from "./databaseApi";


type CompanyRow = {
  id_company: number;
  company: string;
  manufacturer: boolean;
  dealer: boolean;
  decription: string | null;
  note: string | null;
};

type CompanyEdit = {
  company: string;
  manufacturer: boolean;
  dealer: boolean;
  decription: string;
  note: string;
};

const editFromRow = (row: CompanyRow): CompanyEdit => ({
  company: row.company || "",
  manufacturer: Boolean(row.manufacturer),
  dealer: Boolean(row.dealer),
  decription: row.decription || "",
  note: row.note || "",
});


export default function Companies() {
  const [selectedCompany, setSelectedCompany] = useState<CompanyRow | null>(null);
  const [edit, setEdit] = useState<CompanyEdit | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const columns = useMemo<GridColDef[]>(
    () => [
      { field: "company", headerName: "Company", flex: 1, minWidth: 260 },
      {
        field: "manufacturer",
        headerName: "Manufacturer",
        width: 150,
        sortable: false,
        renderCell: (params) => params.value ? (
          <Chip size="small" label="Manufacturer" variant="outlined" color="primary" />
        ) : null,
      },
      {
        field: "dealer",
        headerName: "Dealer",
        width: 110,
        sortable: false,
        renderCell: (params) => params.value ? (
          <Chip size="small" label="Dealer" variant="outlined" color="secondary" />
        ) : null,
      },
    ],
    []
  );

  const fetchCompanies = useCallback(
    (params: Parameters<typeof fetchDatabaseTable>[1]) =>
      fetchDatabaseTable("companies", params),
    []
  );

  const handleCompanyClick = useCallback((params: GridRowParams) => {
    const row = params.row as CompanyRow;
    setSelectedCompany(row);
    setEdit(editFromRow(row));
    setError("");
    setMessage("");
  }, []);

  const updateEdit = (patch: Partial<CompanyEdit>) => {
    setEdit((current) => current ? { ...current, ...patch } : current);
    setError("");
    setMessage("");
  };

  const hasChanges = Boolean(selectedCompany && edit && (
    edit.company !== (selectedCompany.company || "") ||
    edit.manufacturer !== Boolean(selectedCompany.manufacturer) ||
    edit.dealer !== Boolean(selectedCompany.dealer) ||
    edit.decription !== (selectedCompany.decription || "") ||
    edit.note !== (selectedCompany.note || "")
  ));

  const saveChanges = async () => {
    if (!selectedCompany || !edit || saving || !hasChanges) return;
    if (!edit.company.trim()) {
      setError("Il nome della company non può essere vuoto.");
      return;
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch(`${backendBaseUrl}/api/database/companies/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items: [{
            id_company: selectedCompany.id_company,
            company: edit.company,
            manufacturer: edit.manufacturer,
            dealer: edit.dealer,
            decription: edit.decription,
            note: edit.note,
          }],
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore salvataggio company");
      }

      const updated: CompanyRow = {
        id_company: selectedCompany.id_company,
        ...edit,
      };
      setSelectedCompany(updated);
      setEdit(editFromRow(updated));
      setMessage("Modifiche salvate direttamente in luciana_db_dev.");
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  };

  const closeDetail = () => {
    setSelectedCompany(null);
    setEdit(null);
    setError("");
    setMessage("");
  };

  return (
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
        title="Companies"
        columns={columns}
        fetchRows={fetchCompanies}
        getRowId={(row) => row.id_company}
        filterFields={["company"]}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        refreshToken={refreshToken}
        height="100%"
        onRowClick={handleCompanyClick}
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
        {selectedCompany && edit ? (
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
                    Scheda azienda · ID {selectedCompany.id_company}
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {edit.company || "Company senza nome"}
                  </Typography>
                </Box>
                <Chip size="small" label="luciana_db_dev" color="info" variant="outlined" />
                <IconButton
                  aria-label="Chiudi scheda azienda"
                  size="small"
                  onClick={closeDetail}
                >
                  ×
                </IconButton>
              </Box>
            </Box>

            <Box
              sx={{
                flex: 1,
                minHeight: 0,
                overflowY: "auto",
                p: 2,
                display: "flex",
                flexDirection: "column",
                gap: 2,
              }}
            >
              {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
              {message && <Alert severity="success" onClose={() => setMessage("")}>{message}</Alert>}

              <TextField
                fullWidth
                required
                label="Company"
                value={edit.company}
                disabled={saving}
                onChange={(event) => updateEdit({ company: event.target.value })}
              />

              <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap" }}>
                <FormControlLabel
                  control={(
                    <Checkbox
                      checked={edit.manufacturer}
                      disabled={saving}
                      onChange={(event) => updateEdit({ manufacturer: event.target.checked })}
                    />
                  )}
                  label="Manufacturer"
                />
                <FormControlLabel
                  control={(
                    <Checkbox
                      checked={edit.dealer}
                      disabled={saving}
                      onChange={(event) => updateEdit({ dealer: event.target.checked })}
                    />
                  )}
                  label="Dealer"
                />
              </Box>

              <TextField
                fullWidth
                multiline
                minRows={4}
                label="Description"
                helperText="Campo database: decription"
                value={edit.decription}
                disabled={saving}
                onChange={(event) => updateEdit({ decription: event.target.value })}
              />

              <TextField
                fullWidth
                multiline
                minRows={7}
                label="Note"
                value={edit.note}
                disabled={saving}
                onChange={(event) => updateEdit({ note: event.target.value })}
              />

              <Box sx={{ display: "flex", justifyContent: "flex-end", mt: "auto" }}>
                <CrudActionButton
                  crudAction="save"
                  disabled={saving || !hasChanges || !edit.company.trim()}
                  onClick={() => void saveChanges()}
                >
                  {saving ? "Salvataggio..." : "Salva modifiche"}
                </CrudActionButton>
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
                Scheda azienda
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Seleziona una company dalla tabella per visualizzare e modificare
                description, note e ruoli.
              </Typography>
            </Box>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
