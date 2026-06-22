import React, { useEffect, useMemo, useState } from "react";
import {
  DataGrid,
  GridColDef,
  GridFilterModel,
  GridPagination,
  GridRowSelectionModel,
} from "@mui/x-data-grid";
import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from "@mui/material";

type Company = {
  id: number;
  company_name: string;
  company_code?: string | null;
};

type CompanyRole = "any" | "dealer" | "manufacturer";

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

const columns: GridColDef[] = [
  { field: "id_prod_version", headerName: "Prod Version ID", width: 130 },
  { field: "id_prod", headerName: "Prod ID", width: 90 },
  { field: "company_item_code", headerName: "Item Code", width: 170 },
  { field: "version", headerName: "Version", width: 100 },
  { field: "is_current", headerName: "Current", width: 100, type: "boolean" },
  { field: "valid_from", headerName: "Valid From", width: 145 },
  { field: "valid_to", headerName: "Valid To", width: 145 },
  { field: "prod_version_data_creation", headerName: "Created", width: 170 },
  { field: "description", headerName: "Description", width: 280 },
  { field: "prod_version_notes", headerName: "Version Notes", width: 220 },
  { field: "id_dealer", headerName: "Dealer ID", width: 100 },
  { field: "dealer_company_name", headerName: "Dealer", width: 200 },
  { field: "dealer_company_code", headerName: "Dealer Code", width: 130 },
  { field: "id_manufacturer", headerName: "Manufacturer ID", width: 140 },
  { field: "manufacturer_company_name", headerName: "Manufacturer", width: 220 },
  { field: "manufacturer_company_code", headerName: "Manufacturer Code", width: 160 },
  { field: "id_prefix_encoding", headerName: "Encoding ID", width: 120 },
  { field: "prefix_encoding", headerName: "Encoding", width: 140 },
  { field: "id_prefix_code", headerName: "Prefix Code ID", width: 130 },
  { field: "prefix_code", headerName: "Prefix Code", width: 140 },
  { field: "id_father_name", headerName: "Father ID", width: 110 },
  { field: "father_name", headerName: "Father Name", width: 170 },
  { field: "id_mc", headerName: "MC ID", width: 90 },
  { field: "id_mc_lvl1", headerName: "MC L1 ID", width: 100 },
  { field: "mc_lvl1_code", headerName: "MC L1 Code", width: 120 },
  { field: "mc_lvl1_desc", headerName: "MC L1 Desc", width: 220 },
  { field: "mc_lvl1_status_code", headerName: "MC L1 Status", width: 135 },
  { field: "id_mc_lvl2", headerName: "MC L2 ID", width: 100 },
  { field: "mc_lvl2_code", headerName: "MC L2 Code", width: 120 },
  { field: "mc_lvl2_desc", headerName: "MC L2 Desc", width: 220 },
  { field: "mc_lvl2_status_code", headerName: "MC L2 Status", width: 135 },
  { field: "id_mc_lvl3", headerName: "MC L3 ID", width: 100 },
  { field: "mc_lvl3_code", headerName: "MC L3 Code", width: 120 },
  { field: "mc_lvl3_desc", headerName: "MC L3 Desc", width: 220 },
  { field: "mc_lvl3_status_code", headerName: "MC L3 Status", width: 135 },
  { field: "id_pack", headerName: "Pack ID", width: 100 },
  { field: "pack", headerName: "Pack", width: 140 },
  { field: "id_pack_qty", headerName: "Pack Qty ID", width: 120 },
  { field: "pack_qty_raw", headerName: "Pack Qty Raw", width: 150 },
  { field: "inner_count", headerName: "Inner Count", width: 120 },
  { field: "inner_qty", headerName: "Inner Qty", width: 120 },
  { field: "is_composite_pack", headerName: "Composite Pack", width: 145, type: "boolean" },
  { field: "id_pack_measure_unit", headerName: "Pack Unit ID", width: 130 },
  { field: "pack_measure_unit", headerName: "Pack Unit", width: 130 },
  { field: "pack_qty_notes", headerName: "Pack Qty Notes", width: 220 },
  { field: "id_feature", headerName: "Feature ID", width: 110 },
  { field: "feature", headerName: "Feature", width: 160 },
  { field: "id_measure", headerName: "Measure ID", width: 115 },
  { field: "measure", headerName: "Measure", width: 140 },
  { field: "id_split", headerName: "Split ID", width: 100 },
  { field: "id_parent_prod", headerName: "Parent Prod ID", width: 130 },
  { field: "parent_company_item_code", headerName: "Parent Item Code", width: 170 },
  { field: "split_percentage", headerName: "Split %", width: 110 },
  { field: "id_user", headerName: "User ID", width: 90 },
  { field: "user_nome", headerName: "User Name", width: 140 },
  { field: "user_cognome", headerName: "User Last Name", width: 160 },
];

export default function Products() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [companyRole, setCompanyRole] = useState<CompanyRole>("any");
  const [rows, setRows] = useState<any[]>([]);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filterModel, setFilterModel] = useState<GridFilterModel>({ items: [] });
  const [rowSelectionModel, setRowSelectionModel] =
    useState<GridRowSelectionModel>({
      type: "include",
      ids: new Set(),
    });

  useEffect(() => {
    setLoadingCompanies(true);
    fetch(`${backendBaseUrl}/api/products/companies`)
      .then((res) => {
        if (!res.ok) throw new Error("Impossibile caricare le aziende");
        return res.json();
      })
      .then((data) => setCompanies(data))
      .catch((err) => setError(err.message || "Errore caricamento aziende"))
      .finally(() => setLoadingCompanies(false));
  }, []);

  const selectedCount =
    rowSelectionModel.type === "include"
      ? rowSelectionModel.ids.size
      : rows.length - rowSelectionModel.ids.size;

  const selectedCompany = useMemo(
    () => companies.find((company) => String(company.id) === selectedCompanyId),
    [companies, selectedCompanyId]
  );

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setFilterModel({
      items: value
        ? [
            {
              field: "description",
              operator: "contains",
              value,
            },
          ]
        : [],
    });
  };

  const handleRun = async () => {
    if (!selectedCompanyId) {
      setError("Seleziona una company prima di eseguire la query.");
      return;
    }

    setError("");
    setLoadingRows(true);
    setRows([]);

    try {
      const response = await fetch(`${backendBaseUrl}/api/products/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_company: Number(selectedCompanyId),
          company_role: companyRole,
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore durante l'esecuzione della query");
      }

      const data = await response.json();
      setRows(
        data.map((row: any, index: number) => ({
          id: `${row.id_prod_version ?? "pv"}-${row.id_pack_qty ?? "pq"}-${row.id_split ?? "sp"}-${index}`,
          ...row,
        }))
      );
    } catch (err: any) {
      setError(err.message || "Errore generico");
    } finally {
      setLoadingRows(false);
    }
  };

  return (
    <Box sx={{ height: "89vh", width: "100%", p: 0 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 1.5,
          mb: 1,
          flexWrap: "wrap",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Products</h2>

          <FormControl size="small" sx={{ minWidth: 320 }}>
            <InputLabel id="products-company-label">Company</InputLabel>
            <Select
              labelId="products-company-label"
              label="Company"
              value={selectedCompanyId}
              onChange={(event) => setSelectedCompanyId(event.target.value)}
              disabled={loadingCompanies}
            >
              {companies.map((company) => (
                <MenuItem key={company.id} value={String(company.id)}>
                  {company.company_name}
                  {company.company_code ? ` (${company.company_code})` : ""}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel id="products-role-label">Role</InputLabel>
            <Select
              labelId="products-role-label"
              label="Role"
              value={companyRole}
              onChange={(event) => setCompanyRole(event.target.value as CompanyRole)}
            >
              <MenuItem value="any">Any</MenuItem>
              <MenuItem value="dealer">Dealer</MenuItem>
              <MenuItem value="manufacturer">Manufacturer</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="contained"
            onClick={handleRun}
            disabled={loadingCompanies || loadingRows || !selectedCompanyId}
          >
            {loadingRows ? "Esecuzione..." : "Esegui"}
          </Button>
        </Box>

        <TextField
          size="small"
          placeholder="Find in description..."
          value={search}
          onChange={(event) => handleSearchChange(event.target.value)}
          sx={{ width: 260 }}
        />
      </Box>

      {selectedCompany && (
        <Box sx={{ mb: 1, fontSize: 13, color: "text.secondary" }}>
          Company selezionata: {selectedCompany.company_name}
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}

      <DataGrid
        rows={rows}
        columns={columns}
        loading={loadingRows}
        rowHeight={28}
        pageSizeOptions={[25, 50, 100]}
        filterModel={filterModel}
        onFilterModelChange={setFilterModel}
        checkboxSelection
        disableRowSelectionOnClick
        rowSelectionModel={rowSelectionModel}
        onRowSelectionModelChange={(newSelection) =>
          setRowSelectionModel(newSelection)
        }
        slots={{
          footer: () => (
            <CustomFooter selectedCount={selectedCount} rowCount={rows.length} />
          ),
        }}
      />
    </Box>
  );
}

function CustomFooter({
  selectedCount,
  rowCount,
}: {
  selectedCount: number;
  rowCount: number;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        px: 1,
        py: 0.5,
        borderTop: "1px solid #e0e0e0",
      }}
    >
      <Box sx={{ fontSize: 13, color: "text.secondary" }}>
        {selectedCount > 0
          ? `${selectedCount} righe selezionate`
          : `${rowCount} righe caricate`}
      </Box>

      <GridPagination />
    </Box>
  );
}
