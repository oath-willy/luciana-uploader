import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  DataGrid,
  GridColDef,
  GridPagination,
  GridPaginationModel,
  GridRenderCellParams,
  GridRowSelectionModel,
} from "@mui/x-data-grid";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  FormControl,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  TextField,
} from "@mui/material";

type DictionaryStatus = "all" | "validated" | "non_validated" | "id_country_null";
type ColumnFilters = Record<string, string>;

type CountryOption = {
  id_country: number;
  country_name: string;
};

type DictionaryRow = {
  id: number;
  ID: number;
  "COUNTRY RAW": string | null;
  "COUNTRY ISO": string | null;
  "USER NAME": string | null;
  VALIDATED: boolean | null;
  id_country: number | null;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const pageSizeOptions = [25, 50, 100, 500];

const filterFields = ["ID", "COUNTRY RAW", "COUNTRY ISO", "USER NAME", "VALIDATED"];

export default function CountriesDictionary() {
  const [rows, setRows] = useState<DictionaryRow[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [loadingRows, setLoadingRows] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [search, setSearch] = useState("");
  const [columnFilters, setColumnFilters] = useState<ColumnFilters>({});
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [debouncedColumnFilters, setDebouncedColumnFilters] = useState<ColumnFilters>({});
  const [status, setStatus] = useState<DictionaryStatus>("all");
  const [countryOptions, setCountryOptions] = useState<CountryOption[]>([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [countryEdits, setCountryEdits] = useState<Record<number, CountryOption | null>>({});
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
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(search);
      setDebouncedColumnFilters(columnFilters);
    }, 450);

    return () => window.clearTimeout(timeout);
  }, [search, columnFilters]);

  const cleanFilters = useCallback((filters: ColumnFilters) => {
    return Object.fromEntries(
      Object.entries(filters)
        .map(([field, value]) => [field, value.trim()])
        .filter(([, value]) => value)
    );
  }, []);

  const fetchRows = useCallback(async () => {
    setLoadingRows(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(`${backendBaseUrl}/api/countries-dictionary/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          page: paginationModel.page,
          page_size: paginationModel.pageSize,
          status,
          search: debouncedSearch.trim(),
          filters: cleanFilters(debouncedColumnFilters),
        }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore durante il caricamento del dizionario");
      }

      const data = await response.json();
      const responseRows = (data.rows || []).map((row: any) => ({
        id: row.ID,
        ...row,
      }));

      setRows(responseRows);
      setRowCount(data.total || 0);
    } catch (err: any) {
      setRows([]);
      setRowCount(0);
      setError(err.message || "Errore generico");
    } finally {
      setLoadingRows(false);
    }
  }, [
    paginationModel,
    status,
    debouncedSearch,
    debouncedColumnFilters,
    cleanFilters,
  ]);

  useEffect(() => {
    fetchRows();
  }, [fetchRows]);

  const fetchCountries = useCallback(async (query = "") => {
    setLoadingCountries(true);
    try {
      const params = new URLSearchParams({
        q: query,
        limit: "50",
      });
      const response = await fetch(
        `${backendBaseUrl}/api/countries-dictionary/countries?${params.toString()}`
      );

      if (!response.ok) {
        throw new Error("Impossibile caricare la lista countries");
      }

      setCountryOptions(await response.json());
    } catch (err: any) {
      setError(err.message || "Errore caricamento countries");
    } finally {
      setLoadingCountries(false);
    }
  }, []);

  useEffect(() => {
    fetchCountries();
  }, [fetchCountries]);

  const hasActiveFilters = useMemo(
    () =>
      Boolean(search.trim()) ||
      Object.values(columnFilters).some((value) => value.trim()),
    [search, columnFilters]
  );

  const selectedIds = useMemo(() => {
    if (rowSelectionModel.type !== "include") {
      return new Set<number>();
    }

    return new Set(Array.from(rowSelectionModel.ids).map((id) => Number(id)));
  }, [rowSelectionModel]);

  const selectedCount = selectedIds.size;

  const handleColumnFilterChange = useCallback((field: string, value: string) => {
    setColumnFilters((current) => ({ ...current, [field]: value }));
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

  const updateCountryEdit = (rowId: number, country: CountryOption | null) => {
    setCountryEdits((current) => ({
      ...current,
      [rowId]: country,
    }));
    setRows((current) =>
      current.map((row) =>
        row.ID === rowId
          ? {
              ...row,
              id_country: country?.id_country ?? null,
              "COUNTRY ISO": country?.country_name ?? null,
            }
          : row
      )
    );
  };

  const handleValidate = async () => {
    const items = rows
      .filter((row) => selectedIds.has(row.ID))
      .map((row) => ({
        id_country_dictionary: row.ID,
        id_country: countryEdits[row.ID]?.id_country ?? row.id_country,
      }))
      .filter((item) => item.id_country);

    if (items.length === 0) {
      setError("Seleziona almeno una riga con COUNTRY ISO valorizzato.");
      return;
    }

    if (items.length !== selectedCount) {
      setError("Tutte le righe selezionate devono avere COUNTRY ISO valorizzato.");
      return;
    }

    setValidating(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(`${backendBaseUrl}/api/countries-dictionary/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Errore durante la validazione");
      }

      const data = await response.json();
      setSuccess(`${data.updated} righe validate`);
      setCountryEdits({});
      setRowSelectionModel({ type: "include", ids: new Set() });
      await fetchRows();
    } catch (err: any) {
      setError(err.message || "Errore validazione");
    } finally {
      setValidating(false);
    }
  };

  const columns = useMemo<GridColDef[]>(
    () =>
      [
        { field: "ID", headerName: "ID", width: 90 },
        { field: "COUNTRY RAW", headerName: "COUNTRY RAW", width: 220 },
        {
          field: "COUNTRY ISO",
          headerName: "COUNTRY ISO",
          width: 260,
          sortable: false,
          renderCell: (params: GridRenderCellParams<DictionaryRow>) => {
            const row = params.row as DictionaryRow;
            const currentValue =
              countryEdits[row.ID] ||
              (row.id_country
                ? {
                    id_country: row.id_country,
                    country_name: row["COUNTRY ISO"] || String(row.id_country),
                  }
                : null);

            return (
              <Autocomplete
                size="small"
                options={countryOptions}
                value={currentValue}
                loading={loadingCountries}
                onOpen={() => fetchCountries()}
                onInputChange={(_, value, reason) => {
                  if (reason === "input") {
                    fetchCountries(value);
                  }
                }}
                onChange={(_, value) => updateCountryEdit(row.ID, value)}
                getOptionLabel={(option) => option.country_name}
                isOptionEqualToValue={(option, value) =>
                  option.id_country === value.id_country
                }
                renderInput={(inputParams) => (
                  <TextField {...inputParams} placeholder="Seleziona country" />
                )}
                sx={{ width: "100%" }}
              />
            );
          },
        },
        { field: "USER NAME", headerName: "USER NAME", width: 180 },
        {
          field: "VALIDATED",
          headerName: "VALIDATED",
          width: 135,
          renderCell: (params: GridRenderCellParams<DictionaryRow>) => (
            <Chip
              size="small"
              color={params.value ? "success" : "default"}
              label={params.value ? "Validated" : "Non validated"}
            />
          ),
        },
      ].map((column) => ({
        ...column,
        renderHeader: () => {
          const value = columnFilters[column.field] || "";
          const canFilter = filterFields.includes(column.field);

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
              {canFilter && (
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
              )}
            </Box>
          );
        },
      })),
    [
      columnFilters,
      countryEdits,
      countryOptions,
      loadingCountries,
      fetchCountries,
      handleColumnFilterChange,
      clearColumnFilter,
    ]
  );

  return (
    <Box sx={{ height: "89vh", width: "100%", p: 0 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 1.5,
          mb: 1,
          flexWrap: "wrap",
        }}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Countries Dictionary</h2>

          <FormControl size="small" sx={{ minWidth: 190 }}>
            <InputLabel id="countries-dictionary-status-label">View</InputLabel>
            <Select
              labelId="countries-dictionary-status-label"
              label="View"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as DictionaryStatus);
                setPaginationModel((current) => ({ ...current, page: 0 }));
              }}
            >
              <MenuItem value="all">All</MenuItem>
              <MenuItem value="validated">Validated</MenuItem>
              <MenuItem value="non_validated">Non validated</MenuItem>
              <MenuItem value="id_country_null">id_country NULL</MenuItem>
            </Select>
          </FormControl>

          <Button
            variant="contained"
            onClick={handleValidate}
            disabled={validating || selectedCount === 0}
          >
            {validating ? "VALIDATING..." : "VALIDATE"}
          </Button>
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
          <TextField
            size="small"
            placeholder="Find..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPaginationModel((current) => ({ ...current, page: 0 }));
            }}
            sx={{ width: 260 }}
            InputProps={{
              endAdornment: search ? (
                <InputAdornment position="end">
                  <IconButton
                    aria-label="Svuota filtro generale"
                    size="small"
                    onClick={() => setSearch("")}
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

      {error && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 1 }}>
          {success}
        </Alert>
      )}

      <DataGrid
        rows={rows}
        columns={columns}
        loading={loadingRows}
        rowHeight={44}
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
