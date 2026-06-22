import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  DataGrid,
  GridColDef,
  GridPagination,
  GridPaginationModel,
  GridRowParams,
  GridRowSelectionModel,
} from "@mui/x-data-grid";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  FormControl,
  FormControlLabel,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  Typography,
} from "@mui/material";

type Company = {
  id: number;
  company_name: string;
  company_code?: string | null;
};

type CompanyRole = "any" | "dealer" | "manufacturer";
type ColumnFilters = Record<string, string>;
type ProductRow = Record<string, any>;
type LookupOption = {
  id: number;
  label: string;
  code?: string | null;
};
type ProductLookups = Record<string, LookupOption[]>;

type ProductsProps = {
  title?: string;
  enableDetailPanel?: boolean;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const pageSizeOptions = [25, 50, 100, 250, 500, 1000, { value: -1, label: "Full" }];

const baseColumns: GridColDef[] = [
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

const lookupFields: Record<string, string> = {
  id_dealer: "companies",
  id_manufacturer: "companies",
  id_prefix_encoding: "prefix_encodings",
  id_prefix_code: "prefix_codes",
  id_father_name: "father_names",
  id_mc: "master_codes",
  id_pack: "packs",
  id_pack_measure_unit: "pack_measure_units",
  id_feature: "features",
  id_measure: "measures",
  id_parent_prod: "products",
  id_user: "users",
};

const relatedLabelFields: Record<string, string[]> = {
  id_dealer: ["dealer_company_name", "dealer_company_code"],
  id_manufacturer: ["manufacturer_company_name", "manufacturer_company_code"],
  id_prefix_encoding: ["prefix_encoding"],
  id_prefix_code: ["prefix_code"],
  id_father_name: ["father_name"],
  id_pack: ["pack"],
  id_pack_measure_unit: ["pack_measure_unit"],
  id_feature: ["feature"],
  id_measure: ["measure"],
  id_parent_prod: ["parent_company_item_code"],
};

export default function Products({
  title = "Products",
  enableDetailPanel = false,
}: ProductsProps) {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);
  const [companyRole, setCompanyRole] = useState<CompanyRole>("any");
  const [rows, setRows] = useState<any[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [loadingRows, setLoadingRows] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFilters>({});
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [debouncedColumnFilters, setDebouncedColumnFilters] = useState<ColumnFilters>({});
  const [hasExecuted, setHasExecuted] = useState(false);
  const [runToken, setRunToken] = useState(0);
  const [selectedProduct, setSelectedProduct] = useState<ProductRow | null>(null);
  const [draftProduct, setDraftProduct] = useState<ProductRow | null>(null);
  const [productLookups, setProductLookups] = useState<ProductLookups>({});
  const [loadingLookups, setLoadingLookups] = useState(false);
  const [lookupsLoaded, setLookupsLoaded] = useState(false);
  const [paginationModel, setPaginationModel] = useState<GridPaginationModel>({
    page: 0,
    pageSize: 100,
  });
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

  const loadProductLookups = useCallback(async () => {
    if (lookupsLoaded || loadingLookups) {
      return;
    }

    setLoadingLookups(true);
    try {
      const response = await fetch(`${backendBaseUrl}/api/products/lookups`);
      if (!response.ok) {
        throw new Error("Impossibile caricare i valori dei menu a tendina");
      }

      setProductLookups(await response.json());
      setLookupsLoaded(true);
    } catch (err: any) {
      setError(err.message || "Errore caricamento lookup prodotto");
    } finally {
      setLoadingLookups(false);
    }
  }, [lookupsLoaded, loadingLookups]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(search);
      setDebouncedColumnFilters(columnFilters);
    }, 450);

    return () => window.clearTimeout(timeout);
  }, [search, columnFilters]);

  const selectedCount =
    rowSelectionModel.type === "include"
      ? rowSelectionModel.ids.size
      : Math.max(rowCount - rowSelectionModel.ids.size, 0);

  const hasActiveFilters = useMemo(
    () =>
      Boolean(search.trim()) ||
      Object.values(columnFilters).some((value) => value.trim()),
    [search, columnFilters]
  );

  const cleanFilters = useCallback((filters: ColumnFilters) => {
    return Object.fromEntries(
      Object.entries(filters)
        .map(([field, value]) => [field, value.trim()])
        .filter(([, value]) => value)
    );
  }, []);

  const fetchProducts = useCallback(async () => {
    if (!selectedCompany) {
      return;
    }

    setError("");
    setLoadingRows(true);
    setRows([]);

    try {
      const isFull = paginationModel.pageSize === -1;
      const response = await fetch(`${backendBaseUrl}/api/products/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_company: selectedCompany.id,
          company_role: companyRole,
          page: isFull ? 0 : paginationModel.page,
          page_size: isFull ? 1000 : paginationModel.pageSize,
          full: isFull,
          search: debouncedSearch.trim(),
          filters: cleanFilters(debouncedColumnFilters),
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore durante l'esecuzione della query");
      }

      const data = await response.json();
      const responseRows = Array.isArray(data) ? data : data.rows || [];
      const responseTotal = Array.isArray(data) ? responseRows.length : data.total || 0;

      setRows(
        responseRows.map((row: any, index: number) => ({
          id: `${row.id_prod_version ?? "pv"}-${row.id_pack_qty ?? "pq"}-${row.id_split ?? "sp"}-${paginationModel.page}-${index}`,
          ...row,
        }))
      );
      setRowCount(responseTotal);
    } catch (err: any) {
      setError(err.message || "Errore generico");
      setRowCount(0);
    } finally {
      setLoadingRows(false);
    }
  }, [
    selectedCompany,
    companyRole,
    paginationModel,
    debouncedSearch,
    debouncedColumnFilters,
    cleanFilters,
  ]);

  useEffect(() => {
    if (hasExecuted) {
      fetchProducts();
    }
  }, [hasExecuted, fetchProducts, runToken]);

  const handleRun = () => {
    if (!selectedCompany) {
      setError("Seleziona una company prima di eseguire la query.");
      return;
    }

    setHasExecuted(true);
    setPaginationModel((current) => ({ ...current, page: 0 }));
    setRunToken((current) => current + 1);
  };

  const handleRowClick = useCallback(
    (params: GridRowParams) => {
      if (!enableDetailPanel) {
        return;
      }

      setSelectedProduct(params.row);
      setDraftProduct(params.row);
      loadProductLookups();
    },
    [enableDetailPanel, loadProductLookups]
  );

  const closeDetailPanel = () => {
    setSelectedProduct(null);
    setDraftProduct(null);
  };

  const handleDetailChange = (field: string, value: any, option?: LookupOption | null) => {
    setDraftProduct((current) => {
      if (!current) {
        return current;
      }

      const next = {
        ...current,
        [field]: value,
      };

      const labelFields = relatedLabelFields[field] || [];
      if (option && labelFields.length > 0) {
        next[labelFields[0]] = option.label;
        if (labelFields[1]) {
          next[labelFields[1]] = option.code || "";
        }
      }

      return next;
    });
  };

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPaginationModel((current) => ({ ...current, page: 0 }));
  };

  const handleColumnFilterChange = useCallback((field: string, value: string) => {
    setColumnFilters((current) => ({
      ...current,
      [field]: value,
    }));
    setPaginationModel((current) => ({ ...current, page: 0 }));
  }, []);

  const clearColumnFilter = useCallback((field: string) => {
    setColumnFilters((current) => {
      const next = { ...current };
      delete next[field];
      return next;
    });
    setPaginationModel((current) => ({ ...current, page: 0 }));
  }, []);

  const clearAllFilters = () => {
    setSearch("");
    setColumnFilters({});
    setPaginationModel((current) => ({ ...current, page: 0 }));
  };

  const columns = useMemo(
    () =>
      baseColumns.map((column) => ({
        ...column,
        renderHeader: () => {
          const value = columnFilters[column.field] || "";

          return (
            <Box sx={{ width: "100%", py: 0.5 }}>
              <Box
                sx={{
                  fontSize: 12,
                  fontWeight: 700,
                  lineHeight: 1.1,
                  mb: 0.5,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={column.headerName}
              >
                {column.headerName}
              </Box>
              <TextField
                value={value}
                onChange={(event) =>
                  handleColumnFilterChange(column.field, event.target.value)
                }
                onClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                placeholder="Filtro"
                size="small"
                variant="outlined"
                fullWidth
                inputProps={{
                  "aria-label": `Filtro ${column.headerName}`,
                  style: { fontSize: 12, padding: "4px 0 4px 6px" },
                }}
                InputProps={{
                  sx: { height: 28, fontSize: 12, pr: value ? 0.25 : 0 },
                  endAdornment: value ? (
                    <InputAdornment position="end">
                      <IconButton
                        aria-label={`Svuota filtro ${column.headerName}`}
                        size="small"
                        onClick={(event) => {
                          event.stopPropagation();
                          clearColumnFilter(column.field);
                        }}
                        sx={{ width: 20, height: 20, fontSize: 12 }}
                      >
                        x
                      </IconButton>
                    </InputAdornment>
                  ) : undefined,
                }}
              />
            </Box>
          );
        },
      })),
    [columnFilters, handleColumnFilterChange, clearColumnFilter]
  );

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
          <h2 style={{ margin: 0 }}>{title}</h2>

          <Autocomplete
            size="small"
            options={companies}
            value={selectedCompany}
            onChange={(_, value) => {
              setSelectedCompany(value);
              setPaginationModel((current) => ({ ...current, page: 0 }));
            }}
            loading={loadingCompanies}
            disabled={loadingCompanies}
            getOptionLabel={(company) =>
              `${company.company_name}${company.company_code ? ` (${company.company_code})` : ""}`
            }
            isOptionEqualToValue={(option, value) => option.id === value.id}
            renderInput={(params) => (
              <TextField {...params} label="Company" placeholder="Scrivi per filtrare" />
            )}
            sx={{ minWidth: 320 }}
          />

          <FormControl size="small" sx={{ minWidth: 170 }}>
            <InputLabel id="products-role-label">Role</InputLabel>
            <Select
              labelId="products-role-label"
              label="Role"
              value={companyRole}
              onChange={(event) => {
                setCompanyRole(event.target.value as CompanyRole);
                setPaginationModel((current) => ({ ...current, page: 0 }));
              }}
            >
              <MenuItem value="any">Any</MenuItem>
              <MenuItem value="dealer">Dealer</MenuItem>
              <MenuItem value="manufacturer">Manufacturer</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="contained"
            onClick={handleRun}
            disabled={loadingCompanies || loadingRows || !selectedCompany}
          >
            {loadingRows ? "Esecuzione..." : "Esegui"}
          </Button>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <TextField
            size="small"
            placeholder="Find in description..."
            value={search}
            onChange={(event) => handleSearchChange(event.target.value)}
            sx={{ width: 260 }}
            InputProps={{
              endAdornment: search ? (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="Svuota ricerca descrizione"
                    size="small"
                    onClick={() => handleSearchChange("")}
                    sx={{ width: 24, height: 24, fontSize: 12 }}
                  >
                    x
                  </IconButton>
                </InputAdornment>
              ) : undefined,
            }}
          />
          {hasActiveFilters && (
            <Button variant="outlined" onClick={clearAllFilters}>
              Rimuovi filtri
            </Button>
          )}
        </Box>
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

      <Box
        sx={{
          height: enableDetailPanel && selectedProduct ? "45vh" : "calc(89vh - 86px)",
          minHeight: 280,
          transition: "height 180ms ease",
        }}
      >
        <DataGrid
          rows={rows}
          columns={columns}
          loading={loadingRows}
          rowHeight={28}
          columnHeaderHeight={76}
          paginationMode="server"
          rowCount={rowCount}
          paginationModel={paginationModel}
          onPaginationModelChange={(model) => setPaginationModel(model)}
          pageSizeOptions={pageSizeOptions}
          checkboxSelection
          disableRowSelectionOnClick
          rowSelectionModel={rowSelectionModel}
          onRowSelectionModelChange={(newSelection) =>
            setRowSelectionModel(newSelection)
          }
          onRowClick={handleRowClick}
          slots={{
            footer: () => (
              <CustomFooter
                selectedCount={selectedCount}
                loadedCount={rows.length}
                rowCount={rowCount}
              />
            ),
          }}
        />
      </Box>

      {enableDetailPanel && draftProduct && (
        <ProductDetailPanel
          product={draftProduct}
          lookups={productLookups}
          loadingLookups={loadingLookups}
          onChange={handleDetailChange}
          onClose={closeDetailPanel}
        />
      )}
    </Box>
  );
}

function CustomFooter({
  selectedCount,
  loadedCount,
  rowCount,
}: {
  selectedCount: number;
  loadedCount: number;
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
          : `${loadedCount} righe visualizzate su ${rowCount} totali`}
      </Box>

      <GridPagination />
    </Box>
  );
}

function ProductDetailPanel({
  product,
  lookups,
  loadingLookups,
  onChange,
  onClose,
}: {
  product: ProductRow;
  lookups: ProductLookups;
  loadingLookups: boolean;
  onChange: (field: string, value: any, option?: LookupOption | null) => void;
  onClose: () => void;
}) {
  return (
    <Paper
      elevation={1}
      sx={{
        mt: 1,
        height: "34vh",
        minHeight: 230,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        borderRadius: 1,
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          px: 1.5,
          py: 1,
          borderBottom: "1px solid #e0e0e0",
        }}
      >
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            Scheda prodotto
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {product.company_item_code || "Prodotto senza codice"}
          </Typography>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {loadingLookups && <CircularProgress size={18} />}
          <IconButton aria-label="Chiudi scheda prodotto" onClick={onClose} size="small">
            X
          </IconButton>
        </Box>
      </Box>

      <Box
        sx={{
          flex: 1,
          overflow: "auto",
          p: 1.5,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 1.25,
          alignContent: "start",
        }}
      >
        {baseColumns.map((column) => (
          <ProductDetailField
            key={column.field}
            field={column.field}
            label={column.headerName || column.field}
            value={product[column.field]}
            type={column.type}
            lookups={lookups}
            onChange={onChange}
          />
        ))}
      </Box>
    </Paper>
  );
}

function ProductDetailField({
  field,
  label,
  value,
  type,
  lookups,
  onChange,
}: {
  field: string;
  label: string;
  value: any;
  type?: GridColDef["type"];
  lookups: ProductLookups;
  onChange: (field: string, value: any, option?: LookupOption | null) => void;
}) {
  const lookupKey = lookupFields[field];
  const options = lookupKey ? lookups[lookupKey] || [] : [];

  if (lookupKey) {
    const selectedOption =
      options.find((option) => String(option.id) === String(value)) || null;

    return (
      <Autocomplete
        size="small"
        options={options}
        value={selectedOption}
        onChange={(_, option) => onChange(field, option?.id ?? null, option)}
        getOptionLabel={(option) =>
          `${option.label || option.id}${option.code ? ` (${option.code})` : ""}`
        }
        isOptionEqualToValue={(option, selected) => option.id === selected.id}
        renderInput={(params) => (
          <TextField {...params} label={label} placeholder="Cerca..." />
        )}
      />
    );
  }

  if (type === "boolean") {
    return (
      <FormControlLabel
        control={
          <Checkbox
            checked={Boolean(value)}
            onChange={(event) => onChange(field, event.target.checked)}
          />
        }
        label={label}
      />
    );
  }

  return (
    <TextField
      label={label}
      size="small"
      value={value ?? ""}
      onChange={(event) => onChange(field, event.target.value)}
      multiline={field.includes("notes") || field === "description"}
      minRows={field.includes("notes") || field === "description" ? 2 : 1}
    />
  );
}
