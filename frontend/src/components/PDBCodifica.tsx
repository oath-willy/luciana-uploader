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
type LookupSearchParams = Record<string, string | number | null | undefined>;

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
  id_mc_lvl1: "mc_lvl1",
  id_mc_lvl2: "mc_lvl2",
  id_mc_lvl3: "mc_lvl3",
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
  id_mc_lvl1: ["mc_lvl1_code"],
  id_mc_lvl2: ["mc_lvl2_code"],
  id_mc_lvl3: ["mc_lvl3_code"],
  id_pack: ["pack"],
  id_pack_measure_unit: ["pack_measure_unit"],
  id_feature: ["feature"],
  id_measure: ["measure"],
  id_parent_prod: ["parent_company_item_code"],
};

const staticLookupKeys = [
  "companies",
  "prefix_encodings",
  "prefix_codes",
  "father_names",
  "packs",
  "products",
];

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
  const [loadingLookups, setLoadingLookups] = useState<Record<string, boolean>>({});
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

  const fetchProductLookup = useCallback(async (
    lookupKey: string,
    query = "",
    extraParams: LookupSearchParams = {}
  ) => {
    if (loadingLookups[lookupKey]) {
      return;
    }

    setLoadingLookups((current) => ({ ...current, [lookupKey]: true }));
    try {
      const params = new URLSearchParams({
        q: query,
        limit: "50",
      });
      Object.entries(extraParams).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== "") {
          params.set(key, String(value));
        }
      });
      const response = await fetch(
        `${backendBaseUrl}/api/products/lookups/${lookupKey}?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error("Impossibile caricare i valori dei menu a tendina");
      }

      const data = await response.json();
      setProductLookups((current) => ({
        ...current,
        [lookupKey]: data,
      }));
    } catch (err: any) {
      setError(err.message || "Errore caricamento lookup prodotto");
    } finally {
      setLoadingLookups((current) => ({ ...current, [lookupKey]: false }));
    }
  }, [loadingLookups]);

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
      staticLookupKeys.forEach((lookupKey) => {
        fetchProductLookup(lookupKey);
      });
      fetchProductLookup("mc_lvl1");
      fetchProductLookup("mc_lvl2", "", {
        id_mc_lvl1: params.row.id_mc_lvl1,
      });
      fetchProductLookup("mc_lvl3", "", {
        id_mc_lvl1: params.row.id_mc_lvl1,
        id_mc_lvl2: params.row.id_mc_lvl2,
      });
    },
    [enableDetailPanel, fetchProductLookup]
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
        next[labelFields[0]] = field.startsWith("id_mc_lvl")
          ? formatMcCode(option.code || option.label)
          : option.label;
        if (labelFields[1]) {
          next[labelFields[1]] = option.code || "";
        }
      }

      if (field === "id_mc_lvl1") {
        next.id_mc = null;
        next.id_mc_lvl2 = null;
        next.mc_lvl2_code = "";
        next.mc_lvl2_desc = "";
        next.mc_lvl2_status_code = "";
        next.id_mc_lvl3 = null;
        next.mc_lvl3_code = "";
        next.mc_lvl3_desc = "";
        next.mc_lvl3_status_code = "";
        setProductLookups((currentLookups) => ({
          ...currentLookups,
          mc_lvl2: [],
          mc_lvl3: [],
        }));
        if (value) {
          fetchProductLookup("mc_lvl2", "", { id_mc_lvl1: value });
        }
      }

      if (field === "id_mc_lvl2") {
        next.id_mc = null;
        next.id_mc_lvl3 = null;
        next.mc_lvl3_code = "";
        next.mc_lvl3_desc = "";
        next.mc_lvl3_status_code = "";
        setProductLookups((currentLookups) => ({
          ...currentLookups,
          mc_lvl3: [],
        }));
        if (value) {
          fetchProductLookup("mc_lvl3", "", {
            id_mc_lvl1: next.id_mc_lvl1,
            id_mc_lvl2: value,
          });
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
          onLookupSearch={fetchProductLookup}
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
  onLookupSearch,
  onClose,
}: {
  product: ProductRow;
  lookups: ProductLookups;
  loadingLookups: Record<string, boolean>;
  onChange: (field: string, value: any, option?: LookupOption | null) => void;
  onLookupSearch: (
    lookupKey: string,
    query?: string,
    extraParams?: LookupSearchParams
  ) => void;
  onClose: () => void;
}) {
  const metaItems = [
    ["Prod Version ID", product.id_prod_version],
    ["Prod ID", product.id_prod],
    ["Version", product.version],
    ["Current", product.is_current ? "Yes" : "No"],
    ["Created", product.prod_version_data_creation],
    ["User Name", [product.user_nome, product.user_cognome].filter(Boolean).join(" ")],
  ].filter(([, value]) => value !== null && value !== undefined && value !== "");

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
          gap: 1.5,
          px: 1.5,
          py: 1,
          borderBottom: "1px solid #e0e0e0",
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
            {product.company_item_code || "Prodotto senza codice"}
          </Typography>
          <Box
            sx={{
              display: "flex",
              flexWrap: "wrap",
              gap: 0.75,
              mt: 0.5,
            }}
          >
            {metaItems.map(([label, value]) => (
              <Box
                key={label}
                sx={{
                  fontSize: 12,
                  color: "text.secondary",
                  whiteSpace: "nowrap",
                }}
              >
                <Box component="span" sx={{ fontWeight: 700, color: "text.primary" }}>
                  {label}:
                </Box>{" "}
                {String(value)}
              </Box>
            ))}
          </Box>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {Object.values(loadingLookups).some(Boolean) && <CircularProgress size={18} />}
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
        }}
      >
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", md: "280px minmax(320px, 1fr)" },
            gap: 1.25,
            mb: 1.25,
          }}
        >
          <ProductDetailField
            field="company_item_code"
            label="Item Code"
            value={product.company_item_code}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="description"
            label="Description"
            value={product.description}
            lookups={lookups}
            loadingLookups={loadingLookups}
            multiline
            minRows={2}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </Box>

        <DetailGrid>
          <ProductDetailField
            field="id_dealer"
            label="Dealer"
            value={product.id_dealer}
            lookups={lookups}
            currentDisplayValue={product.dealer_company_name}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_manufacturer"
            label="Manufacturer"
            value={product.id_manufacturer}
            lookups={lookups}
            currentDisplayValue={product.manufacturer_company_name}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </DetailGrid>

        <DetailGrid>
          <ProductDetailField
            field="id_prefix_encoding"
            label="Encoding ID"
            value={product.id_prefix_encoding}
            lookups={lookups}
            currentDisplayValue={product.prefix_encoding}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="prefix_encoding"
            label="Encoding"
            value={product.prefix_encoding}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_prefix_code"
            label="Prefix Code ID"
            value={product.id_prefix_code}
            lookups={lookups}
            currentDisplayValue={product.prefix_code}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_father_name"
            label="Father Name ID"
            value={product.id_father_name}
            lookups={lookups}
            currentDisplayValue={product.father_name}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </DetailGrid>

        <DetailGrid>
          <ProductDetailField
            field="id_mc_lvl1"
            label="MC L1 Code"
            value={product.id_mc_lvl1}
            lookups={lookups}
            currentDisplayValue={formatMcCode(product.mc_lvl1_code)}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_mc_lvl2"
            label="MC L2 Code"
            value={product.id_mc_lvl2}
            lookups={lookups}
            currentDisplayValue={formatMcCode(product.mc_lvl2_code)}
            loadingLookups={loadingLookups}
            lookupParams={{ id_mc_lvl1: product.id_mc_lvl1 }}
            disabled={!product.id_mc_lvl1}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_mc_lvl3"
            label="MC L3 Code"
            value={product.id_mc_lvl3}
            lookups={lookups}
            currentDisplayValue={formatMcCode(product.mc_lvl3_code)}
            loadingLookups={loadingLookups}
            lookupParams={{
              id_mc_lvl1: product.id_mc_lvl1,
              id_mc_lvl2: product.id_mc_lvl2,
            }}
            disabled={!product.id_mc_lvl1 || !product.id_mc_lvl2}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </DetailGrid>

        <DetailGrid>
          <ProductDetailField
            field="id_pack"
            label="Pack ID"
            value={product.id_pack}
            lookups={lookups}
            currentDisplayValue={product.pack}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="inner_count"
            label="Inner Count"
            value={product.inner_count}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="inner_qty"
            label="Inner Qty"
            value={product.inner_qty}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="pack_qty_raw"
            label="Pack Qty raw"
            value={product.pack_qty_raw}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="is_composite_pack"
            label="Composite Pack"
            value={product.is_composite_pack}
            type="boolean"
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </DetailGrid>

        <DetailGrid>
          <ProductDetailField
            field="id_split"
            label="Split ID"
            value={product.id_split}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="id_parent_prod"
            label="Parent Prod ID"
            value={product.id_parent_prod}
            lookups={lookups}
            currentDisplayValue={product.parent_company_item_code}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
          <ProductDetailField
            field="split_percentage"
            label="Split %"
            value={product.split_percentage}
            lookups={lookups}
            loadingLookups={loadingLookups}
            onChange={onChange}
            onLookupSearch={onLookupSearch}
          />
        </DetailGrid>
      </Box>
    </Paper>
  );
}

function DetailGrid({ children }: { children: React.ReactNode }) {
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
        gap: 1.25,
        mb: 1.25,
      }}
    >
      {children}
    </Box>
  );
}

function ProductDetailField({
  field,
  label,
  value,
  type,
  lookups,
  currentDisplayValue,
  loadingLookups,
  lookupParams = {},
  disabled = false,
  multiline = false,
  minRows,
  onChange,
  onLookupSearch,
}: {
  field: string;
  label: string;
  value: any;
  type?: GridColDef["type"];
  lookups: ProductLookups;
  currentDisplayValue?: string;
  loadingLookups: Record<string, boolean>;
  lookupParams?: LookupSearchParams;
  disabled?: boolean;
  multiline?: boolean;
  minRows?: number;
  onChange: (field: string, value: any, option?: LookupOption | null) => void;
  onLookupSearch: (
    lookupKey: string,
    query?: string,
    extraParams?: LookupSearchParams
  ) => void;
}) {
  const lookupKey = lookupFields[field];
  const options = lookupKey ? lookups[lookupKey] || [] : [];

  if (lookupKey) {
    const selectedOption =
      options.find((option) => String(option.id) === String(value)) ||
      (value
        ? {
            id: Number(value),
            label: field.startsWith("id_mc_lvl")
              ? formatMcCode(currentDisplayValue || value)
              : currentDisplayValue || String(value),
            code: null,
          }
        : null);

    return (
      <Autocomplete
        size="small"
        options={options}
        value={selectedOption}
        disabled={disabled}
        loading={Boolean(loadingLookups[lookupKey])}
        onOpen={() => onLookupSearch(lookupKey, "", lookupParams)}
        onInputChange={(_, inputValue, reason) => {
          if (reason === "input") {
            onLookupSearch(lookupKey, inputValue, lookupParams);
          }
        }}
        onChange={(_, option) => onChange(field, option?.id ?? null, option)}
        getOptionLabel={(option) =>
          field.startsWith("id_mc_lvl")
            ? formatMcCode(option.code || option.label || option.id)
            : `${option.label || option.id}${option.code ? ` (${option.code})` : ""}`
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
            disabled={disabled}
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
      disabled={disabled}
      onChange={(event) => onChange(field, event.target.value)}
      multiline={multiline || field.includes("notes") || field === "description"}
      minRows={minRows || (field.includes("notes") || field === "description" ? 2 : 1)}
    />
  );
}

function formatMcCode(value: any) {
  if (value === null || value === undefined || value === "") {
    return "";
  }

  const text = String(value).trim();
  return /^\d+$/.test(text) ? text.padStart(2, "0").slice(-2) : text;
}
