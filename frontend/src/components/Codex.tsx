import React, { useCallback, useEffect, useMemo, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { ScanSearch, Sparkles, X } from "lucide-react";
import ServerDataGrid, {
  ServerGridFetchParams,
  ServerGridResult,
} from "./common/ServerDataGrid";

type CodexView = "light" | "full";
type CodexEnvironmentName = "dev" | "prod";

type CodexEnvironment = {
  value: CodexEnvironmentName;
  label: string;
  available: boolean;
  message?: string | null;
};

type CodexCompany = {
  value: string;
  label: string;
  full_view_available: boolean;
  full_view_message?: string | null;
};

type CodexColumn = {
  field: string;
  header_name: string;
  value_type: "string" | "number" | "boolean" | "date";
};

type CodexConfig = {
  default_environment: CodexEnvironmentName;
  environments: CodexEnvironment[];
  dataset_name: string;
  max_extra_columns: number;
  lookup_actions_available: boolean;
  mapping_source?: {
    repository: string;
    branch: string;
    commit: string;
    path: string;
  };
};

type CodexSearchResponse = ServerGridResult & {
  extra_columns?: CodexColumn[];
};

type CodexDetailResponse = {
  record: Record<string, any>;
  extra_columns: CodexColumn[];
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const MAX_EXTRA_COLUMNS = 12;

const lightColumns: GridColDef[] = [
  {
    field: "company_item_code",
    headerName: "Company Item Code",
    minWidth: 210,
    flex: 0.35,
  },
  {
    field: "description",
    headerName: "Description",
    minWidth: 340,
    flex: 1,
  },
  {
    field: "fuzzy_lookup_status",
    headerName: "Fuzzy Lookup",
    width: 180,
    sortable: false,
  },
  {
    field: "ai_lookup_status",
    headerName: "AI Lookup",
    width: 180,
    sortable: false,
  },
];

const emptyConfig: CodexConfig = {
  default_environment: "dev",
  environments: [],
  dataset_name: "",
  max_extra_columns: MAX_EXTRA_COLUMNS,
  lookup_actions_available: false,
};

function toGridColumn(column: CodexColumn): GridColDef {
  return {
    field: column.field,
    headerName: column.header_name,
    minWidth: 160,
    width: 190,
    type:
      column.value_type === "number" || column.value_type === "boolean"
        ? column.value_type
        : "string",
  };
}

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => null);
  return typeof data?.detail === "string" ? data.detail : fallback;
}

export default function Codex() {
  const [view, setView] = useState<CodexView>("light");
  const [environment, setEnvironment] =
    useState<CodexEnvironmentName>("dev");
  const [config, setConfig] = useState<CodexConfig>(emptyConfig);
  const [companies, setCompanies] = useState<CodexCompany[]>([]);
  const [selectedCompany, setSelectedCompany] =
    useState<CodexCompany | null>(null);
  const [extraColumns, setExtraColumns] = useState<CodexColumn[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string | number>>(
    new Set()
  );
  const [detailRow, setDetailRow] = useState<Record<string, any> | null>(null);
  const [detailColumns, setDetailColumns] = useState<CodexColumn[]>([]);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    let active = true;
    setLoadingConfig(true);

    fetch(`${backendBaseUrl}/api/codex/config`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await responseError(
              response,
              "Impossibile caricare la configurazione CODEX"
            )
          );
        }
        return response.json();
      })
      .then((data: CodexConfig) => {
        if (active) {
          setConfig(data);
          setEnvironment(data.default_environment || "dev");
        }
      })
      .catch((error) => {
        if (active) {
          setSetupError(error.message || "Errore inizializzazione CODEX");
        }
      })
      .finally(() => {
        if (active) {
          setLoadingConfig(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const selectedEnvironment = useMemo(
    () => config.environments.find((item) => item.value === environment),
    [config.environments, environment]
  );

  useEffect(() => {
    let active = true;
    setCompanies([]);
    setSelectedCompany(null);
    setSelectedIds(new Set());
    setExtraColumns([]);
    setDetailRow(null);
    setDetailError("");
    setSetupError("");

    if (loadingConfig || !selectedEnvironment?.available) {
      return () => {
        active = false;
      };
    }

    setLoadingCompanies(true);
    const params = new URLSearchParams({ environment });
    fetch(`${backendBaseUrl}/api/codex/companies?${params.toString()}`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Impossibile caricare le company")
          );
        }
        return response.json();
      })
      .then((data) => {
        if (active) {
          setCompanies(Array.isArray(data) ? data : []);
        }
      })
      .catch((error) => {
        if (active) {
          setSetupError(error.message || "Errore caricamento company");
        }
      })
      .finally(() => {
        if (active) {
          setLoadingCompanies(false);
        }
      });

    return () => {
      active = false;
    };
  }, [environment, loadingConfig, selectedEnvironment?.available]);

  const columns = useMemo(() => {
    if (view === "light") {
      return lightColumns;
    }

    return [
      lightColumns[0],
      lightColumns[1],
      ...extraColumns.slice(0, MAX_EXTRA_COLUMNS).map(toGridColumn),
      ...lightColumns.slice(-2),
    ];
  }, [extraColumns, view]);

  const filterFields = useMemo(
    () =>
      columns
        .map((column) => column.field)
        .filter(
          (field) =>
            field !== "fuzzy_lookup_status" && field !== "ai_lookup_status"
        ),
    [columns]
  );

  const fetchRows = useCallback(
    async (params: ServerGridFetchParams): Promise<ServerGridResult> => {
      if (!selectedCompany || !selectedEnvironment?.available) {
        return { rows: [], total: 0 };
      }

      const response = await fetch(`${backendBaseUrl}/api/codex/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          view,
          page: params.page,
          page_size: params.pageSize,
          search: params.search,
          filters: params.filters,
        }),
      });

      if (!response.ok) {
        throw new Error(
          await responseError(response, "Impossibile caricare i record CODEX")
        );
      }

      const data: CodexSearchResponse = await response.json();
      setExtraColumns(
        (data.extra_columns || []).slice(
          0,
          Math.min(config.max_extra_columns || MAX_EXTRA_COLUMNS, MAX_EXTRA_COLUMNS)
        )
      );

      return {
        rows: data.rows || [],
        total: data.total || 0,
      };
    },
    [
      config.max_extra_columns,
      environment,
      selectedCompany,
      selectedEnvironment?.available,
      view,
    ]
  );

  const handleSelectionChange = useCallback(
    (ids: Set<string | number>) => setSelectedIds(ids),
    []
  );

  const handleRowClick = useCallback(
    async (params: GridRowParams) => {
      if (view !== "light" || !selectedCompany) {
        return;
      }

      setLoadingDetail(true);
      setDetailError("");
      setDetailRow(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/codex/detail`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            environment,
            company: selectedCompany.value,
            item_code: params.row.item_code,
          }),
        });
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Impossibile caricare il dettaglio")
          );
        }

        const detail: CodexDetailResponse = await response.json();
        setDetailRow(detail.record);
        setDetailColumns(detail.extra_columns || []);
      } catch (error: any) {
        setDetailError(error.message || "Errore caricamento dettaglio");
      } finally {
        setLoadingDetail(false);
      }
    },
    [environment, selectedCompany, view]
  );

  const changeView = (_: React.MouseEvent<HTMLElement>, nextView: CodexView | null) => {
    if (!nextView) {
      return;
    }
    setView(nextView);
    setSelectedIds(new Set());
    setDetailRow(null);
    setDetailError("");
    if (nextView === "light") {
      setExtraColumns([]);
    }
  };

  const lookupDisabled =
    !config.lookup_actions_available || selectedIds.size === 0;
  const lookupTooltip = !config.lookup_actions_available
    ? "API di lookup non ancora configurata"
    : selectedIds.size === 0
      ? "Seleziona almeno un record"
      : "";

  const toolbarLeft = (
    <>
      <FormControl size="small" sx={{ minWidth: 130 }}>
        <InputLabel id="codex-environment-label">Environment</InputLabel>
        <Select
          labelId="codex-environment-label"
          label="Environment"
          value={environment}
          disabled={loadingConfig}
          onChange={(event) =>
            setEnvironment(event.target.value as CodexEnvironmentName)
          }
        >
          {config.environments.map((item) => (
            <MenuItem key={item.value} value={item.value}>
              {item.label}{item.available ? "" : " (non disponibile)"}
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <Autocomplete
        size="small"
        options={companies}
        value={selectedCompany}
        onChange={(_, company) => {
          setSelectedCompany(company);
          setSelectedIds(new Set());
          setExtraColumns([]);
          setDetailRow(null);
          setDetailError("");
        }}
        loading={loadingCompanies}
        disabled={loadingConfig || loadingCompanies || !selectedEnvironment?.available}
        getOptionLabel={(company) => company.label}
        isOptionEqualToValue={(option, value) => option.value === value.value}
        noOptionsText="Nessuna company disponibile"
        renderInput={(params) => (
          <TextField
            {...params}
            label="Company"
            placeholder="Scrivi per filtrare"
            InputProps={{
              ...params.InputProps,
              endAdornment: (
                <>
                  {loadingCompanies ? <CircularProgress size={18} /> : null}
                  {params.InputProps.endAdornment}
                </>
              ),
            }}
          />
        )}
        sx={{ width: 290 }}
      />

      <ToggleButtonGroup
        exclusive
        size="small"
        value={view}
        onChange={changeView}
        aria-label="Visualizzazione CODEX"
      >
        <ToggleButton value="light">Light</ToggleButton>
        <ToggleButton value="full">Full</ToggleButton>
      </ToggleButtonGroup>

      <Tooltip title={lookupTooltip} disableHoverListener={!lookupTooltip}>
        <span>
          <Button
            variant="outlined"
            startIcon={<ScanSearch size={17} />}
            disabled={lookupDisabled}
          >
            Fuzzy Lookup
          </Button>
        </span>
      </Tooltip>
      <Tooltip title={lookupTooltip} disableHoverListener={!lookupTooltip}>
        <span>
          <Button
            variant="contained"
            startIcon={<Sparkles size={17} />}
            disabled={lookupDisabled}
          >
            AI Lookup
          </Button>
        </span>
      </Tooltip>
    </>
  );

  const emptyMessage = !selectedEnvironment?.available
    ? "Ambiente non disponibile"
    : selectedCompany
      ? "Nessun record da classificare"
      : "Seleziona una company";

  return (
    <Box sx={{ height: "89vh", width: "100%" }}>
      <Typography
        component="div"
        sx={{ mb: 0.75, color: "text.secondary", fontSize: 13 }}
      >
        Company selezionata:{" "}
        <Box component="span" sx={{ color: "text.primary", fontWeight: 600 }}>
          {selectedCompany?.label || "Nessuna"}
        </Box>
      </Typography>

      {!selectedEnvironment?.available && selectedEnvironment?.message && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {selectedEnvironment.message}
        </Alert>
      )}
      {view === "full" &&
        selectedCompany &&
        !selectedCompany.full_view_available && (
          <Alert severity="info" sx={{ mb: 1 }}>
            {selectedCompany.full_view_message}
          </Alert>
        )}
      {setupError && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {setupError}
        </Alert>
      )}
      {detailError && (
        <Alert severity="error" sx={{ mb: 1 }}>
          {detailError}
        </Alert>
      )}

      <ServerDataGrid
        key={`${environment}-${selectedCompany?.value || "none"}-${view}`}
        title="CODEX"
        columns={columns}
        fetchRows={fetchRows}
        getRowId={(row) => row.id}
        pageSizeOptions={[25, 50, 100, 250, 500]}
        defaultPageSize={100}
        filterFields={filterFields}
        toolbarLeft={toolbarLeft}
        checkboxSelection
        onSelectionChange={handleSelectionChange}
        onRowClick={handleRowClick}
        rowHeight={34}
        height={detailRow || loadingDetail ? "50vh" : "calc(89vh - 24px)"}
        emptyMessage={emptyMessage}
      />

      {loadingDetail && (
        <Paper
          variant="outlined"
          sx={{ mt: 1, height: "36vh", display: "grid", placeItems: "center" }}
        >
          <CircularProgress size={28} />
        </Paper>
      )}
      {detailRow && !loadingDetail && (
        <CodexDetailPanel
          row={detailRow}
          columns={detailColumns}
          onClose={() => setDetailRow(null)}
        />
      )}
    </Box>
  );
}

function CodexDetailPanel({
  row,
  columns,
  onClose,
}: {
  row: Record<string, any>;
  columns: CodexColumn[];
  onClose: () => void;
}) {
  const labels = useMemo(
    () =>
      Object.fromEntries([
        ["company", "Company"],
        ["item_code", "Item Code"],
        ["company_item_code", "Company Item Code"],
        ["description", "Description"],
        ["first_received_date", "First Received Date"],
        ["source_file", "Product Source File"],
        ["search_type", "Search Type"],
        ["status", "Status"],
        ["created_date", "Created Date"],
        ...columns.map((column) => [column.field, column.header_name]),
      ]),
    [columns]
  );

  const fields = useMemo(() => {
    const preferred = [
      "company",
      "item_code",
      "company_item_code",
      "description",
      "first_received_date",
      "source_file",
      "search_type",
      "status",
      "created_date",
      ...columns.map((column) => column.field),
    ];
    const available = Object.keys(row);
    return [
      ...preferred.filter((field) => available.includes(field)),
      ...available.filter(
        (field) => !preferred.includes(field) && field !== "id"
      ),
    ];
  }, [columns, row]);

  return (
    <Paper
      variant="outlined"
      sx={{
        mt: 1,
        height: "36vh",
        minHeight: 240,
        overflow: "hidden",
        borderRadius: 1,
      }}
    >
      <Box
        sx={{
          height: 48,
          px: 1.5,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid",
          borderColor: "divider",
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" fontWeight={700} noWrap>
            {row.company_item_code || "Dettaglio record"}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            Dettaglio completo in sola lettura
          </Typography>
        </Box>
        <Tooltip title="Chiudi">
          <IconButton size="small" onClick={onClose} aria-label="Chiudi dettaglio">
            <X size={18} />
          </IconButton>
        </Tooltip>
      </Box>

      <Box
        sx={{
          height: "calc(100% - 48px)",
          overflowY: "auto",
          p: 1.5,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          alignContent: "start",
          gap: 1.25,
        }}
      >
        {fields.map((field) => (
          <Box
            key={field}
            sx={{
              minWidth: 0,
              gridColumn:
                field === "description" || field === "landing_item_description"
                  ? "1 / -1"
                  : "auto",
            }}
          >
            <Typography variant="caption" color="text.secondary" component="div">
              {labels[field] || field.replace(/_/g, " ")}
            </Typography>
            <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
              {formatDetailValue(row[field])}
            </Typography>
          </Box>
        ))}
      </Box>
    </Paper>
  );
}

function formatDetailValue(value: any) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "Si" : "No";
  }
  return String(value);
}
