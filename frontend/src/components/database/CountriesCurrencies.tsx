import { useCallback, useEffect, useMemo, useState } from "react";
import { GridColDef, GridRenderCellParams } from "@mui/x-data-grid";
import {
  Alert,
  Autocomplete,
  Box,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
} from "@mui/material";
import { ChevronLeft, ChevronRight } from "lucide-react";
import CrudActionButton from "../common/CrudActionButton";
import ServerDataGrid, {
  ServerGridFetchParams,
  ServerGridResult,
} from "../common/ServerDataGrid";
import { backendBaseUrl } from "./databaseApi";

type CountryOption = {
  id_country: number;
  country_name: string;
};

type CurrencyOption = {
  id_currency: number;
  currency_code: string;
  currency_name: string | null;
  uic_code: string | null;
};

type CountriesCurrencyRow = {
  id: number;
  id_time: number;
  year: number;
  month: number;
  id_country: number;
  country_name: string | null;
  id_currency: number;
  currency_code: string | null;
  currency_name: string | null;
  uic_code: string | null;
};

type RowEdit = {
  year: number;
  month: number;
  country: CountryOption | null;
  currency: CurrencyOption | null;
};

const currentYear = new Date().getFullYear();
const years = Array.from({ length: currentYear - 2015 + 1 }, (_, index) => 2015 + index);
const monthOptions = [
  { value: 1, label: "Gennaio" },
  { value: 2, label: "Febbraio" },
  { value: 3, label: "Marzo" },
  { value: 4, label: "Aprile" },
  { value: 5, label: "Maggio" },
  { value: 6, label: "Giugno" },
  { value: 7, label: "Luglio" },
  { value: 8, label: "Agosto" },
  { value: 9, label: "Settembre" },
  { value: 10, label: "Ottobre" },
  { value: 11, label: "Novembre" },
  { value: 12, label: "Dicembre" },
];

const emptyNewRow = (year: number, month: number): RowEdit => ({
  year,
  month,
  country: null,
  currency: null,
});

function errorMessage(data: any, fallback: string) {
  const detail = data?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || JSON.stringify(item))
      .filter(Boolean)
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return fallback;
}

export default function CountriesCurrencies() {
  const today = new Date();
  const [selectedYear, setSelectedYear] = useState(today.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(today.getMonth() + 1);
  const [edits, setEdits] = useState<Record<number, RowEdit>>({});
  const [selectedIds, setSelectedIds] = useState<Set<number | string>>(new Set());
  const [refreshToken, setRefreshToken] = useState(0);
  const [countryOptions, setCountryOptions] = useState<CountryOption[]>([]);
  const [currencyOptions, setCurrencyOptions] = useState<CurrencyOption[]>([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [loadingCurrencies, setLoadingCurrencies] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [creating, setCreating] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newRow, setNewRow] = useState<RowEdit>(() =>
    emptyNewRow(selectedYear, selectedMonth)
  );
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    setEdits({});
    setSelectedIds(new Set());
  }, [selectedYear, selectedMonth]);

  const fetchCountries = useCallback(async (query = "") => {
    setLoadingCountries(true);
    try {
      const params = new URLSearchParams({ q: query, limit: "100" });
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/countries?${params.toString()}`
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Impossibile caricare countries"));
      }
      setCountryOptions(await response.json());
    } finally {
      setLoadingCountries(false);
    }
  }, []);

  const fetchCurrencies = useCallback(async (query = "") => {
    setLoadingCurrencies(true);
    try {
      const params = new URLSearchParams({ q: query, limit: "100" });
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/currencies?${params.toString()}`
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Impossibile caricare currencies"));
      }
      setCurrencyOptions(await response.json());
    } finally {
      setLoadingCurrencies(false);
    }
  }, []);

  useEffect(() => {
    fetchCountries().catch((err) => setError(err.message));
    fetchCurrencies().catch((err) => setError(err.message));
  }, [fetchCountries, fetchCurrencies]);

  const fetchRows = useCallback(
    async (params: ServerGridFetchParams): Promise<ServerGridResult> => {
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/search`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            page: params.page,
            page_size: params.pageSize,
            search: params.search,
            filters: params.filters,
            year: selectedYear,
            month: selectedMonth,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Errore caricamento countries/currencies"));
      }

      const data = await response.json();
      return {
        rows: data.rows || [],
        total: data.total || 0,
      };
    },
    [selectedYear, selectedMonth]
  );

  const currentCountry = useCallback(
    (row: CountriesCurrencyRow): CountryOption | null =>
      edits[row.id]?.country ??
      (row.id_country
        ? {
            id_country: row.id_country,
            country_name: row.country_name || String(row.id_country),
          }
        : null),
    [edits]
  );

  const currentCurrency = useCallback(
    (row: CountriesCurrencyRow): CurrencyOption | null =>
      edits[row.id]?.currency ??
      (row.id_currency
        ? {
            id_currency: row.id_currency,
            currency_code: row.currency_code || String(row.id_currency),
            currency_name: row.currency_name,
            uic_code: row.uic_code,
          }
        : null),
    [edits]
  );

  const updateEdit = useCallback((row: CountriesCurrencyRow, patch: Partial<RowEdit>) => {
    setEdits((current) => {
      const base = current[row.id] ?? {
        year: row.year,
        month: row.month,
        country: currentCountry(row),
        currency: currentCurrency(row),
      };

      return {
        ...current,
        [row.id]: {
          ...base,
          ...patch,
        },
      };
    });
  }, [currentCountry, currentCurrency]);

  const handleSave = async () => {
    const items = Object.entries(edits).map(([id, edit]) => ({
      id: Number(id),
      year: edit.year,
      month: edit.month,
      id_country: edit.country?.id_country,
      id_currency: edit.currency?.id_currency,
    }));

    if (items.some((item) => !item.id_country || !item.id_currency)) {
      setError("Tutte le righe modificate devono avere country e currency valorizzate.");
      return;
    }

    setSaving(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/update`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items }),
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Errore salvataggio"));
      }
      const data = await response.json();
      setSuccess(`${data.updated} righe aggiornate`);
      setEdits({});
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  };

  const handleCreate = async () => {
    if (!newRow.country || !newRow.currency) {
      setError("Country e currency sono obbligatorie per inserire una nuova riga.");
      return;
    }

    setCreating(true);
    setError("");
    setSuccess("");

    try {
      const createdYear = newRow.year;
      const createdMonth = newRow.month;
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/create`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            item: {
              year: newRow.year,
              month: newRow.month,
              id_country: newRow.country.id_country,
              id_currency: newRow.currency.id_currency,
            },
          }),
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Errore inserimento"));
      }
      setSuccess("Riga inserita");
      setDialogOpen(false);
      setSelectedYear(createdYear);
      setSelectedMonth(createdMonth);
      setNewRow(emptyNewRow(createdYear, createdMonth));
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Errore inserimento");
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async () => {
    const ids = Array.from(selectedIds).map((id) => Number(id));
    if (ids.length === 0) {
      setError("Seleziona almeno una riga da eliminare.");
      return;
    }

    const confirmed = window.confirm(`Eliminare ${ids.length} righe selezionate?`);
    if (!confirmed) {
      return;
    }

    setDeleting(true);
    setError("");
    setSuccess("");

    try {
      const response = await fetch(
        `${backendBaseUrl}/api/database/countries-currencies/delete`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
        }
      );
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(errorMessage(data, "Errore eliminazione"));
      }
      const data = await response.json();
      setSuccess(`${data.deleted} righe eliminate`);
      setSelectedIds(new Set());
      setRefreshToken((current) => current + 1);
    } catch (err: any) {
      setError(err.message || "Errore eliminazione");
    } finally {
      setDeleting(false);
    }
  };

  const moveMonth = (delta: number) => {
    const next = new Date(selectedYear, selectedMonth - 1 + delta, 1);
    const nextYear = next.getFullYear();
    if (nextYear < 2015 || nextYear > currentYear) {
      return;
    }
    setSelectedYear(nextYear);
    setSelectedMonth(next.getMonth() + 1);
  };

  const openCreateDialog = () => {
    setNewRow(emptyNewRow(selectedYear, selectedMonth));
    setDialogOpen(true);
  };

  const columns = useMemo<GridColDef[]>(
    () => [
      { field: "id", headerName: "ID", width: 90 },
      {
        field: "year",
        headerName: "Anno",
        width: 130,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CountriesCurrencyRow>) => {
          const row = params.row;
          const value = edits[row.id]?.year ?? row.year;
          return (
            <Select
              size="small"
              value={value}
              onChange={(event) =>
                updateEdit(row, { year: Number(event.target.value) })
              }
              sx={{ width: "100%" }}
            >
              {years.map((year) => (
                <MenuItem key={year} value={year}>
                  {year}
                </MenuItem>
              ))}
            </Select>
          );
        },
      },
      {
        field: "month",
        headerName: "Mese",
        width: 150,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CountriesCurrencyRow>) => {
          const row = params.row;
          const value = edits[row.id]?.month ?? row.month;
          return (
            <Select
              size="small"
              value={value}
              onChange={(event) =>
                updateEdit(row, { month: Number(event.target.value) })
              }
              sx={{ width: "100%" }}
            >
              {monthOptions.map((month) => (
                <MenuItem key={month.value} value={month.value}>
                  {month.label}
                </MenuItem>
              ))}
            </Select>
          );
        },
      },
      {
        field: "country_name",
        headerName: "Country",
        width: 280,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CountriesCurrencyRow>) => {
          const row = params.row;
          return (
            <Autocomplete
              size="small"
              options={countryOptions}
              value={currentCountry(row)}
              loading={loadingCountries}
              onOpen={() => fetchCountries().catch((err) => setError(err.message))}
              onInputChange={(_, value, reason) => {
                if (reason === "input") {
                  fetchCountries(value).catch((err) => setError(err.message));
                }
              }}
              onChange={(_, value) => updateEdit(row, { country: value })}
              getOptionLabel={(option) => option.country_name}
              isOptionEqualToValue={(option, value) =>
                option.id_country === value.id_country
              }
              renderInput={(inputParams) => (
                <TextField {...inputParams} placeholder="Country" />
              )}
              sx={{ width: "100%" }}
            />
          );
        },
      },
      {
        field: "currency_code",
        headerName: "Currency",
        width: 260,
        sortable: false,
        renderCell: (params: GridRenderCellParams<CountriesCurrencyRow>) => {
          const row = params.row;
          return (
            <Autocomplete
              size="small"
              options={currencyOptions}
              value={currentCurrency(row)}
              loading={loadingCurrencies}
              onOpen={() => fetchCurrencies().catch((err) => setError(err.message))}
              onInputChange={(_, value, reason) => {
                if (reason === "input") {
                  fetchCurrencies(value).catch((err) => setError(err.message));
                }
              }}
              onChange={(_, value) => updateEdit(row, { currency: value })}
              getOptionLabel={(option) =>
                `${option.currency_code}${option.currency_name ? ` - ${option.currency_name}` : ""}`
              }
              isOptionEqualToValue={(option, value) =>
                option.id_currency === value.id_currency
              }
              renderInput={(inputParams) => (
                <TextField {...inputParams} placeholder="Currency" />
              )}
              sx={{ width: "100%" }}
            />
          );
        },
      },
      { field: "id_time", headerName: "id_time", width: 105 },
      { field: "id_country", headerName: "id_country", width: 120 },
      { field: "id_currency", headerName: "id_currency", width: 125 },
      { field: "currency_name", headerName: "Currency name", width: 220 },
      { field: "uic_code", headerName: "UIC", width: 110 },
    ],
    [
      edits,
      countryOptions,
      currencyOptions,
      loadingCountries,
      loadingCurrencies,
      fetchCountries,
      fetchCurrencies,
      currentCountry,
      currentCurrency,
      updateEdit,
    ]
  );

  const toolbarLeft = (
    <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
      <IconButton
        aria-label="Mese precedente"
        onClick={() => moveMonth(-1)}
        disabled={selectedYear === 2015 && selectedMonth === 1}
        size="small"
      >
        <ChevronLeft size={18} />
      </IconButton>

      <FormControl size="small" sx={{ minWidth: 115 }}>
        <InputLabel id="countries-currencies-year-label">Anno</InputLabel>
        <Select
          labelId="countries-currencies-year-label"
          label="Anno"
          value={selectedYear}
          onChange={(event) => setSelectedYear(Number(event.target.value))}
        >
          {years.map((year) => (
            <MenuItem key={year} value={year}>
              {year}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 145 }}>
        <InputLabel id="countries-currencies-month-label">Mese</InputLabel>
        <Select
          labelId="countries-currencies-month-label"
          label="Mese"
          value={selectedMonth}
          onChange={(event) => setSelectedMonth(Number(event.target.value))}
        >
          {monthOptions.map((month) => (
            <MenuItem key={month.value} value={month.value}>
              {month.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <IconButton
        aria-label="Mese successivo"
        onClick={() => moveMonth(1)}
        disabled={selectedYear === currentYear && selectedMonth === 12}
        size="small"
      >
        <ChevronRight size={18} />
      </IconButton>

      <CrudActionButton crudAction="add" onClick={openCreateDialog}>
        Aggiungi
      </CrudActionButton>
      <CrudActionButton
        crudAction="delete"
        onClick={handleDelete}
        disabled={deleting || selectedIds.size === 0}
      >
        {deleting ? "Eliminazione..." : "Elimina"}
      </CrudActionButton>
      <CrudActionButton
        crudAction="save"
        onClick={handleSave}
        disabled={saving || Object.keys(edits).length === 0}
      >
        {saving ? "Salvataggio..." : "Salva modifiche"}
      </CrudActionButton>
    </Stack>
  );

  return (
    <Box sx={{ height: "89vh", width: "100%" }}>
      {error && (
        <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError("")}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 1 }} onClose={() => setSuccess("")}>
          {success}
        </Alert>
      )}

      <ServerDataGrid
        title="Countries Currencies"
        columns={columns}
        fetchRows={fetchRows}
        getRowId={(row) => row.id}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        refreshToken={refreshToken}
        rowHeight={52}
        checkboxSelection
        onSelectionChange={(ids) => setSelectedIds(ids)}
        toolbarLeft={toolbarLeft}
      />

      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Nuova associazione country/currency</DialogTitle>
        <DialogContent>
          <Stack gap={2} sx={{ pt: 1 }}>
            <Stack direction="row" gap={1}>
              <FormControl size="small" fullWidth>
                <InputLabel id="new-country-currency-year-label">Anno</InputLabel>
                <Select
                  labelId="new-country-currency-year-label"
                  label="Anno"
                  value={newRow.year}
                  onChange={(event) =>
                    setNewRow((current) => ({
                      ...current,
                      year: Number(event.target.value),
                    }))
                  }
                >
                  {years.map((year) => (
                    <MenuItem key={year} value={year}>
                      {year}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <FormControl size="small" fullWidth>
                <InputLabel id="new-country-currency-month-label">Mese</InputLabel>
                <Select
                  labelId="new-country-currency-month-label"
                  label="Mese"
                  value={newRow.month}
                  onChange={(event) =>
                    setNewRow((current) => ({
                      ...current,
                      month: Number(event.target.value),
                    }))
                  }
                >
                  {monthOptions.map((month) => (
                    <MenuItem key={month.value} value={month.value}>
                      {month.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>

            <Autocomplete
              size="small"
              options={countryOptions}
              value={newRow.country}
              loading={loadingCountries}
              onOpen={() => fetchCountries().catch((err) => setError(err.message))}
              onInputChange={(_, value, reason) => {
                if (reason === "input") {
                  fetchCountries(value).catch((err) => setError(err.message));
                }
              }}
              onChange={(_, value) =>
                setNewRow((current) => ({ ...current, country: value }))
              }
              getOptionLabel={(option) => option.country_name}
              isOptionEqualToValue={(option, value) =>
                option.id_country === value.id_country
              }
              renderInput={(params) => <TextField {...params} label="Country" />}
            />

            <Autocomplete
              size="small"
              options={currencyOptions}
              value={newRow.currency}
              loading={loadingCurrencies}
              onOpen={() => fetchCurrencies().catch((err) => setError(err.message))}
              onInputChange={(_, value, reason) => {
                if (reason === "input") {
                  fetchCurrencies(value).catch((err) => setError(err.message));
                }
              }}
              onChange={(_, value) =>
                setNewRow((current) => ({ ...current, currency: value }))
              }
              getOptionLabel={(option) =>
                `${option.currency_code}${option.currency_name ? ` - ${option.currency_name}` : ""}`
              }
              isOptionEqualToValue={(option, value) =>
                option.id_currency === value.id_currency
              }
              renderInput={(params) => <TextField {...params} label="Currency" />}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <CrudActionButton
            crudAction="save"
            onClick={handleCreate}
            disabled={creating}
          >
            {creating ? "Inserimento..." : "Inserisci"}
          </CrudActionButton>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
