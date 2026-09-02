import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Radio,
  Select,
  Stack,
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
  fuzzy_lookup_actions_available?: boolean;
  ai_lookup_actions_available?: boolean;
  bs25_actions_available?: boolean;
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

type Bs25Proposal = {
  identity_rank: number;
  identity_score: number;
  exact_match: boolean;
  pdb_ref: string;
  pdb_description: string;
  master_code?: string | null;
  manufacturer?: string | null;
  father_name?: string | null;
  pack?: string | null;
  feature?: string | null;
  measure?: string | null;
};

type PendingBs25Selection = {
  environment: CodexEnvironmentName;
  company: string;
  itemCode: string;
  companyItemCode: string;
  rank: number;
  startedAt: number;
  requestId: string;
  lastSubmittedAt?: number;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const MAX_EXTRA_COLUMNS = 12;
const BS25_SELECTION_OUTBOX_KEY = "codex.bs25.selection-outbox.v1";

function bs25SelectionKey(
  environment: CodexEnvironmentName,
  company: string,
  itemCode: string
) {
  return JSON.stringify([environment, company.trim().toUpperCase(), itemCode.trim()]);
}

function createSelectionRequestId() {
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}${Math.random()
    .toString(36)
    .slice(2)}`;
}

function loadPendingBs25Selections(): Record<string, PendingBs25Selection> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const parsed = JSON.parse(
      window.localStorage.getItem(BS25_SELECTION_OUTBOX_KEY) || "{}"
    );
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]: [string, any]) =>
        Boolean(
          value &&
            ["dev", "prod"].includes(value.environment) &&
            typeof value.company === "string" &&
            typeof value.itemCode === "string" &&
            typeof value.companyItemCode === "string" &&
            Number.isInteger(value.rank) &&
            value.rank >= 1 &&
            value.rank <= 3 &&
            typeof value.requestId === "string"
        )
      )
    ) as Record<string, PendingBs25Selection>;
  } catch {
    return {};
  }
}

function persistPendingBs25Selections(
  selections: Record<string, PendingBs25Selection>
) {
  if (typeof window === "undefined") {
    return;
  }
  if (Object.keys(selections).length === 0) {
    window.localStorage.removeItem(BS25_SELECTION_OUTBOX_KEY);
    return;
  }
  window.localStorage.setItem(BS25_SELECTION_OUTBOX_KEY, JSON.stringify(selections));
}

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
    field: "bs25_status",
    headerName: "BS25",
    width: 160,
    sortable: false,
    renderCell: (params) => <Bs25StatusCell row={params.row} />,
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
  fuzzy_lookup_actions_available: false,
  ai_lookup_actions_available: false,
  bs25_actions_available: false,
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
  const [selectedRows, setSelectedRows] = useState<Record<string, any>[]>([]);
  const [visibleRows, setVisibleRows] = useState<Record<string, any>[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);
  const [selectionResetToken, setSelectionResetToken] = useState(0);
  const [bs25Busy, setBs25Busy] = useState(false);
  const [pendingSelections, setPendingSelections] = useState<
    Record<string, PendingBs25Selection>
  >(loadPendingBs25Selections);
  const activeSelectionRequests = useRef<Set<string>>(new Set());
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [detailRow, setDetailRow] = useState<Record<string, any> | null>(null);
  const [detailColumns, setDetailColumns] = useState<CodexColumn[]>([]);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    persistPendingBs25Selections(pendingSelections);
  }, [pendingSelections]);

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
    setSelectedRows([]);
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

  const sendPendingSelection = useCallback(
    async (rowKey: string, pending: PendingBs25Selection) => {
      if (activeSelectionRequests.current.has(pending.requestId)) {
        return;
      }
      const now = Date.now();
      if (
        pending.lastSubmittedAt &&
        now - pending.lastSubmittedAt < 60000
      ) {
        return;
      }

      activeSelectionRequests.current.add(pending.requestId);
      setPendingSelections((current) => {
        if (current[rowKey]?.requestId !== pending.requestId) {
          return current;
        }
        const next = {
          ...current,
          [rowKey]: { ...current[rowKey], lastSubmittedAt: now },
        };
        persistPendingBs25Selections(next);
        return next;
      });

      try {
        const response = await fetch(`${backendBaseUrl}/api/codex/bs25/select`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            environment: pending.environment,
            company: pending.company,
            item_code: pending.itemCode,
            proposal_rank: pending.rank,
            selection_request_id: pending.requestId,
          }),
        });
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Impossibile trasmettere la scelta BS25")
          );
        }
        const result = await response.json();
        if (result.selected) {
          setPendingSelections((current) => {
            if (current[rowKey]?.requestId !== pending.requestId) {
              return current;
            }
            const next = { ...current };
            delete next[rowKey];
            persistPendingBs25Selections(next);
            return next;
          });
          setActionMessage(`Scelta BS25 salvata per ${pending.companyItemCode}`);
          setRefreshToken((current) => current + 1);
          return;
        }
        if (
          result.selection_request_id &&
          result.selection_request_id !== pending.requestId
        ) {
          setPendingSelections((current) => {
            if (current[rowKey]?.requestId !== pending.requestId) {
              return current;
            }
            const next = {
              ...current,
              [rowKey]: {
                ...current[rowKey],
                requestId: result.selection_request_id,
              },
            };
            persistPendingBs25Selections(next);
            return next;
          });
        }
        setRefreshToken((current) => current + 1);
      } catch (error: any) {
        setActionError(
          `${pending.companyItemCode}: ${
            error.message || "errore trasmissione scelta BS25"
          }. La scelta resta memorizzata e verra ritentata.`
        );
      } finally {
        activeSelectionRequests.current.delete(pending.requestId);
      }
    },
    []
  );

  useEffect(() => {
    const dispatchPending = () => {
      Object.entries(pendingSelections).forEach(([rowKey, pending]) => {
        void sendPendingSelection(rowKey, pending);
      });
    };
    dispatchPending();
    const interval = window.setInterval(dispatchPending, 10000);
    return () => window.clearInterval(interval);
  }, [pendingSelections, sendPendingSelection]);

  const handleProposalSelect = useCallback(
    (row: Record<string, any>, proposalRank: number) => {
      if (!selectedCompany) {
        return;
      }
      const rowKey = bs25SelectionKey(
        environment,
        selectedCompany.value,
        row.item_code
      );
      if (
        pendingSelections[rowKey] ||
        Number(row.bs25_selected_proposal_rank) === proposalRank
      ) {
        return;
      }

      const pending: PendingBs25Selection = {
        environment,
        company: selectedCompany.value,
        itemCode: String(row.item_code),
        companyItemCode: String(row.company_item_code),
        rank: proposalRank,
        startedAt: Date.now(),
        requestId: createSelectionRequestId(),
      };
      persistPendingBs25Selections({
        ...pendingSelections,
        [rowKey]: pending,
      });
      setPendingSelections((current) => ({ ...current, [rowKey]: pending }));
      setActionError("");
      setActionMessage("");
    },
    [environment, pendingSelections, selectedCompany]
  );

  const columns = useMemo(() => {
    const proposalColumns: GridColDef[] = [1, 2, 3].map((rank) => ({
      field: `bs25_proposal_${rank}`,
      headerName: `Proposta BS25 ${rank}`,
      width: 330,
      minWidth: 300,
      sortable: false,
      filterable: false,
      renderCell: (params) => {
        const pending = selectedCompany
          ? pendingSelections[
              bs25SelectionKey(
                environment,
                selectedCompany.value,
                params.row.item_code
              )
            ]
          : undefined;
        const serverSaving = params.row.bs25_selection_status === "saving";
        return (
          <ProposalCell
            row={params.row}
            proposal={params.value as Bs25Proposal | null}
            rank={rank}
            saving={Boolean(pending) || serverSaving}
            optimisticRank={
              pending?.rank ??
              (serverSaving
                ? Number(params.row.bs25_pending_proposal_rank)
                : undefined)
            }
            onSelect={handleProposalSelect}
          />
        );
      },
    }));

    const leadingColumns = [lightColumns[0], lightColumns[1]];
    const bs25StatusColumn: GridColDef = {
      ...lightColumns[2],
      renderCell: (params) => {
        const pending = selectedCompany
          ? pendingSelections[
              bs25SelectionKey(
                environment,
                selectedCompany.value,
                params.row.item_code
              )
            ]
          : undefined;
        return (
          <Bs25StatusCell
            row={params.row}
            optimisticRank={pending?.rank}
          />
        );
      },
    };
    const futureLookupColumns = lightColumns.slice(3);
    if (view === "light") {
      return [
        ...leadingColumns,
        bs25StatusColumn,
        ...proposalColumns,
        ...futureLookupColumns,
      ];
    }

    return [
      ...leadingColumns,
      ...extraColumns.slice(0, MAX_EXTRA_COLUMNS).map(toGridColumn),
      bs25StatusColumn,
      ...proposalColumns,
      ...futureLookupColumns,
    ];
  }, [
    environment,
    extraColumns,
    handleProposalSelect,
    pendingSelections,
    selectedCompany,
    view,
  ]);

  const filterFields = useMemo(
    () =>
      columns
        .map((column) => column.field)
        .filter(
          (field) =>
            field !== "fuzzy_lookup_status" &&
            field !== "ai_lookup_status" &&
            field !== "bs25_status" &&
            !field.startsWith("bs25_proposal_")
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
    (ids: Set<string | number>, rows: any[]) => {
      setSelectedRows(
        rows.filter((row) => ids.has(row.id) && !row.bs25_status)
      );
    },
    []
  );

  const handleRowsChange = useCallback((rows: any[]) => {
    setVisibleRows(rows);
  }, []);

  useEffect(() => {
    const hasVisiblePendingSelection =
      Boolean(selectedCompany) &&
      visibleRows.some((row) =>
        Boolean(
          pendingSelections[
            bs25SelectionKey(
              environment,
              selectedCompany!.value,
              row.item_code
            )
          ]
        )
      );
    const hasActiveOperation =
      hasVisiblePendingSelection ||
      visibleRows.some(
        (row) =>
          ["queued", "analyzing"].includes(row.bs25_status) ||
          row.bs25_selection_status === "saving"
      );
    if (!hasActiveOperation) {
      return;
    }
    const interval = window.setInterval(
      () => setRefreshToken((current) => current + 1),
      3000
    );
    return () => window.clearInterval(interval);
  }, [environment, pendingSelections, selectedCompany, visibleRows]);

  useEffect(() => {
    const completed: string[] = [];

    Object.entries(pendingSelections).forEach(([rowKey, pending]) => {
      if (
        pending.environment !== environment ||
        pending.company.trim().toUpperCase() !==
          selectedCompany?.value.trim().toUpperCase()
      ) {
        return;
      }
      const row = visibleRows.find(
        (item) => String(item.item_code) === pending.itemCode
      );
      if (!row) {
        return;
      }
      const completedWithRequestId =
        row.bs25_selection_request_id === pending.requestId &&
        row.bs25_selection_status === "completed" &&
        Number(row.bs25_selected_proposal_rank) === pending.rank;
      const completedByLegacyBackend =
        !row.bs25_selection_request_id &&
        row.bs25_selection_status !== "saving" &&
        Number(row.bs25_selected_proposal_rank) === pending.rank;
      if (completedWithRequestId || completedByLegacyBackend) {
        completed.push(rowKey);
      }
    });

    if (completed.length === 0) {
      return;
    }
    setPendingSelections((current) => {
      const next = { ...current };
      completed.forEach((rowKey) => delete next[rowKey]);
      persistPendingBs25Selections(next);
      return next;
    });
    setActionMessage(
      `${completed.length} ${
        completed.length === 1
          ? "scelta BS25 salvata"
          : "scelte BS25 salvate"
      }`
    );
  }, [environment, pendingSelections, selectedCompany, visibleRows]);

  const handleBs25Lookup = useCallback(async () => {
    if (!selectedCompany || selectedRows.length === 0) {
      return;
    }
    setBs25Busy(true);
    setActionError("");
    setActionMessage("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/codex/bs25`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          item_codes: selectedRows.map((row) => row.item_code),
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Impossibile avviare BS25")
        );
      }
      const result = await response.json();
      const accepted = result.accepted_item_codes?.length || 0;
      const locked = result.locked_item_codes?.length || 0;
      setActionMessage(
        `${accepted} record inviati in analisi${
          locked ? `; ${locked} erano gia bloccati` : ""
        }`
      );
      setSelectedRows([]);
      setSelectionResetToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    } catch (error: any) {
      setActionError(error.message || "Errore avvio BS25");
    } finally {
      setBs25Busy(false);
    }
  }, [environment, selectedCompany, selectedRows]);

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
    setSelectedRows([]);
    setDetailRow(null);
    setDetailError("");
    if (nextView === "light") {
      setExtraColumns([]);
    }
  };

  const bs25Available = config.bs25_actions_available ?? false;
  const bs25Disabled = !bs25Available || selectedRows.length === 0 || bs25Busy;
  const bs25Tooltip = !bs25Available
    ? "BS25 non ancora configurato"
    : selectedRows.length === 0
      ? "Seleziona almeno un record"
      : "";
  const fuzzyLookupAvailable = config.fuzzy_lookup_actions_available ?? false;
  const aiLookupAvailable =
    config.ai_lookup_actions_available ?? config.lookup_actions_available;

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
          setSelectedRows([]);
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

      <Tooltip
        title={fuzzyLookupAvailable ? "" : "Fuzzy Lookup non ancora configurato"}
      >
        <span>
          <Button
            variant="outlined"
            startIcon={<ScanSearch size={17} />}
            disabled={!fuzzyLookupAvailable}
          >
            Fuzzy Lookup
          </Button>
        </span>
      </Tooltip>
      <Tooltip title={bs25Tooltip} disableHoverListener={!bs25Tooltip}>
        <span>
          <Button
            variant="contained"
            startIcon={
              bs25Busy ? <CircularProgress size={16} color="inherit" /> : <ScanSearch size={17} />
            }
            disabled={bs25Disabled}
            onClick={handleBs25Lookup}
          >
            {bs25Busy ? "Invio..." : `BS25${selectedRows.length ? ` (${selectedRows.length})` : ""}`}
          </Button>
        </span>
      </Tooltip>
      <Tooltip
        title={aiLookupAvailable ? "" : "AI Lookup non ancora configurato"}
      >
        <span>
          <Button
            variant="outlined"
            startIcon={<Sparkles size={17} />}
            disabled={!aiLookupAvailable}
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
    <Box
      sx={{
        height: "calc(100dvh - 16px)",
        width: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
      }}
    >
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
        <Alert
          severity="error"
          sx={{ mb: 1, cursor: "pointer" }}
          onClick={() => setSetupError("")}
        >
          {setupError}
        </Alert>
      )}
      {detailError && (
        <Alert
          severity="error"
          sx={{ mb: 1, cursor: "pointer" }}
          onClick={() => setDetailError("")}
        >
          {detailError}
        </Alert>
      )}
      {actionError && (
        <Alert
          severity="error"
          sx={{ mb: 1, cursor: "pointer" }}
          onClick={() => setActionError("")}
          onClose={() => setActionError("")}
        >
          {actionError}
        </Alert>
      )}
      {actionMessage && (
        <Alert
          severity="success"
          sx={{ mb: 1, cursor: "pointer" }}
          onClick={() => setActionMessage("")}
          onClose={() => setActionMessage("")}
        >
          {actionMessage}
        </Alert>
      )}

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: "grid",
          gridTemplateRows:
            detailRow || loadingDetail
              ? "minmax(260px, 3fr) minmax(220px, 2fr)"
              : "minmax(0, 1fr)",
          gap: detailRow || loadingDetail ? 1 : 0,
        }}
      >
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
          onRowsChange={handleRowsChange}
          onRowClick={handleRowClick}
          rowHeight={34}
          getRowHeight={(params) =>
            params.model.bs25_status === "completed" ? "auto" : 52
          }
          getRowClassName={(params) => {
            const lookupRunning = ["queued", "analyzing"].includes(
              params.row.bs25_status
            );
            const localPending = selectedCompany
              ? pendingSelections[
                  bs25SelectionKey(
                    environment,
                    selectedCompany.value,
                    params.row.item_code
                  )
                ]
              : undefined;
            const selectionSaving =
              Boolean(localPending) ||
              params.row.bs25_selection_status === "saving";
            return lookupRunning || selectionSaving ? "codex-row-locked" : "";
          }}
          isRowSelectable={(params) => !params.row.bs25_status}
          refreshToken={refreshToken}
          silentRefresh
          selectionResetToken={selectionResetToken}
          height="100%"
          emptyMessage={emptyMessage}
        />

        {loadingDetail && (
          <Paper
            variant="outlined"
            sx={{ minHeight: 0, display: "grid", placeItems: "center" }}
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
    </Box>
  );
}

function Bs25StatusCell({
  row,
  optimisticRank,
}: {
  row: Record<string, any>;
  optimisticRank?: number;
}) {
  const status = row.bs25_status;
  if (!status) {
    return <Typography variant="body2" color="text.secondary">-</Typography>;
  }
  if (status === "analyzing" || status === "queued") {
    return <Chip size="small" color="warning" label="Analyzing" />;
  }
  if (status === "failed") {
    return <Chip size="small" color="error" label="Errore" />;
  }
  const selectionSaving =
    optimisticRank !== undefined || row.bs25_selection_status === "saving";
  if (selectionSaving) {
    const pendingRank =
      optimisticRank ?? Number(row.bs25_pending_proposal_rank);
    return (
      <Stack spacing={0.75} sx={{ width: "100%", pr: 1 }}>
        <Chip
          size="small"
          color="warning"
          label={`Salvataggio scelta ${pendingRank || ""}`.trim()}
        />
        <LinearProgress color="warning" />
      </Stack>
    );
  }
  if (row.bs25_selection_status === "failed") {
    return <Chip size="small" color="error" label="Salvataggio fallito" />;
  }
  if (status === "completed" && row.bs25_selected_proposal_rank) {
    return (
      <Stack spacing={0.5} alignItems="flex-start">
        <Chip
          size="small"
          color="success"
          label={`Scelta ${row.bs25_selected_proposal_rank}`}
        />
        {row.bs25_selected_master_code && (
          <Typography variant="caption" fontWeight={700}>
            {row.bs25_selected_master_code}
          </Typography>
        )}
      </Stack>
    );
  }
  return <Chip size="small" color="info" label="Da selezionare" />;
}

function ProposalCell({
  row,
  proposal,
  rank,
  saving,
  optimisticRank,
  onSelect,
}: {
  row: Record<string, any>;
  proposal: Bs25Proposal | null;
  rank: number;
  saving: boolean;
  optimisticRank?: number;
  onSelect: (row: Record<string, any>, proposalRank: number) => void;
}) {
  if (!proposal) {
    return (
      <Typography variant="caption" color="text.secondary">
        {row.bs25_status === "analyzing" ? "In elaborazione..." : "-"}
      </Typography>
    );
  }

  const selected =
    Number(optimisticRank ?? row.bs25_selected_proposal_rank) === rank;
  const details = [
    proposal.manufacturer,
    proposal.father_name,
    proposal.pack,
    proposal.measure,
  ].filter(Boolean);
  const evidence = proposal.exact_match
    ? "Descrizione normalizzata esatta"
    : proposal.identity_score > 0
      ? "Similarita lessicale BM25"
      : "Nessuna evidenza lessicale";

  return (
    <Box
      sx={{
        width: "100%",
        py: 1,
        pr: 0.75,
        whiteSpace: "normal",
        lineHeight: 1.25,
      }}
      onClick={(event) => event.stopPropagation()}
    >
      <Stack spacing={0.55}>
        <Box sx={{ display: "flex", justifyContent: "space-between", gap: 1 }}>
          <Typography variant="subtitle2" fontWeight={800}>
            {proposal.master_code || "Master Code non disponibile"}
          </Typography>
          <Radio
            size="small"
            checked={selected}
            disabled={saving}
            onChange={() => onSelect(row, rank)}
            inputProps={{ "aria-label": `Seleziona proposta ${rank}` }}
            sx={{ p: 0.25 }}
          />
        </Box>
        <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
          {proposal.pdb_description}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          PDB: {proposal.pdb_ref}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {evidence} · score ordinale {proposal.identity_score.toFixed(4)}
        </Typography>
        {details.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            {details.join(" · ")}
          </Typography>
        )}
        {proposal.feature && (
          <Typography variant="caption" color="text.secondary">
            {proposal.feature}
          </Typography>
        )}
      </Stack>
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
        height: "100%",
        minHeight: 0,
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
