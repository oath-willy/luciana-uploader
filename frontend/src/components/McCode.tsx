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
  FormControlLabel,
  IconButton,
  InputLabel,
  LinearProgress,
  Link,
  MenuItem,
  Paper,
  Radio,
  Select,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  CheckSquare,
  ChevronDown,
  ChevronUp,
  ChevronsDown,
  ChevronsUp,
  RefreshCw,
  ScanSearch,
  Sparkles,
  X,
} from "lucide-react";
import ServerDataGrid, {
  ServerGridFetchParams,
  ServerGridResult,
} from "./common/ServerDataGrid";
import { COMPACT_LAYOUT_SCALE as MC_CODE_LAYOUT_SCALE, compactTypographyStyles as mcCodeTypographyStyles } from "./common/compactWorkspace";
import { pacAiColumns } from "./pacAi/PacAiColumns";

type McCodeView = "light" | "full";
type McCodeEnvironmentName = "dev" | "prod";

type McCodeEnvironment = {
  value: McCodeEnvironmentName;
  label: string;
  available: boolean;
  message?: string | null;
};

type McCodeCompany = {
  value: string;
  label: string;
  full_view_available: boolean;
  full_view_message?: string | null;
};

type McCodeColumn = {
  field: string;
  header_name: string;
  value_type: "string" | "number" | "boolean" | "date";
};

type McCodeConfig = {
  default_environment: McCodeEnvironmentName;
  environments: McCodeEnvironment[];
  dataset_name: string;
  max_extra_columns: number;
  lookup_actions_available: boolean;
  fuzzy_lookup_actions_available?: boolean;
  ai_lookup_actions_available?: boolean;
  bs25_actions_available?: boolean;
  bs23_v2_actions_available?: boolean;
  bs25_v2_actions_available?: boolean;
  bs25ai_actions_available?: boolean;
  pac_ai?: { available: boolean; message?: string | null; max_batch_size: number };
  data_source?: string;
  pdb_available?: Record<McCodeEnvironmentName, boolean>;
  bs25ai_mock_mode?: boolean;
  bs25_source?: string;
  mapping_source?: {
    repository: string;
    branch: string;
    commit: string;
    path: string;
  };
};

type McCodeSearchResponse = ServerGridResult & {
  extra_columns?: McCodeColumn[];
};

type McCodeDetailResponse = {
  record: Record<string, any>;
  extra_columns: McCodeColumn[];
};

type Bs25Proposal = {
  identity_rank: number;
  identity_score: number;
  exact_match: boolean;
  pdb_ref: string;
  pdb_description: string;
  master_code?: string | null;
  manufacturer?: string | null;
  brand?: string | null;
  father_name?: string | null;
  pack?: string | null;
  inner_count?: string | null;
  inner_qty?: string | null;
  pack_measure_unit?: string | null;
  feature?: string | null;
  measure?: string | null;
  extra?: string | null;
  source_evidence?: Array<{
    field: string;
    source_field: string;
    source_span: string;
  }>;
  retriever_version?: string;
};

type Bs25SelectionKind = "proposal" | "clear";

type Bs25Draft = {
  kind: Bs25SelectionKind;
  rank?: number;
  updatedAt: number;
};

type PendingBs25Selection = {
  environment: McCodeEnvironmentName;
  company: string;
  itemCode: string;
  companyItemCode: string;
  kind: Bs25SelectionKind;
  rank?: number;
  startedAt: number;
  requestId: string;
  lastSubmittedAt?: number;
};

type Bs25AiResult = {
  decision: "match" | "ambiguous" | "unresolved";
  selected_candidate_rank?: number | null;
  proposed_master_code?: string | null;
  confidence?: "high" | "medium" | "low" | null;
  rationale?: string;
  components?: Record<string, string | null> | null;
  evidence?: Array<{ url: string; title: string; basis: string }>;
  simulated?: boolean;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const MAX_EXTRA_COLUMNS = 12;
const BS25_SELECTION_OUTBOX_KEY = "mc-code.bs25.selection-outbox.v1";
const BS25_DRAFTS_KEY = "mc-code.bs25.drafts.v1";

function readBs25Storage(key: string): string | null {
  const value = window.localStorage.getItem(key);
  if (value !== null) return value;
  const legacyKey = key.replace(/^mc-code\./, "codex.");
  const legacyValue = window.localStorage.getItem(legacyKey);
  if (legacyValue !== null) {
    window.localStorage.setItem(key, legacyValue);
    window.localStorage.removeItem(legacyKey);
  }
  return legacyValue;
}
const MC_CODE_FROZEN_COLUMNS = [
  { field: "__check__" },
  { field: "company_item_code" },
  { field: "description" },
];

function bs25SelectionKey(
  environment: McCodeEnvironmentName,
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
      readBs25Storage(BS25_SELECTION_OUTBOX_KEY) || "{}"
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
            ["proposal", "clear"].includes(value.kind) &&
            (value.kind !== "proposal" ||
              (Number.isInteger(value.rank) && value.rank >= 1 && value.rank <= 3)) &&
            typeof value.requestId === "string"
        )
      )
    ) as Record<string, PendingBs25Selection>;
  } catch {
    return {};
  }
}

function loadBs25Drafts(): Record<string, Bs25Draft> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const parsed = JSON.parse(readBs25Storage(BS25_DRAFTS_KEY) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]: [string, any]) =>
        Boolean(
          value &&
            ["proposal", "clear"].includes(value.kind) &&
            (value.kind !== "proposal" ||
              (Number.isInteger(value.rank) && value.rank >= 1 && value.rank <= 3))
        )
      )
    ) as Record<string, Bs25Draft>;
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

function persistBs25Drafts(drafts: Record<string, Bs25Draft>) {
  if (typeof window === "undefined") {
    return;
  }
  if (Object.keys(drafts).length === 0) {
    window.localStorage.removeItem(BS25_DRAFTS_KEY);
    return;
  }
  window.localStorage.setItem(BS25_DRAFTS_KEY, JSON.stringify(drafts));
}

function rowHasBs25Candidates(row?: Record<string, any>) {
  if (!row) {
    return false;
  }
  return (
    row.bs25_status === "completed" &&
    [1, 2, 3].every((rank) => Boolean(row[`bs25_proposal_${rank}`]))
  );
}

function rowHasUnsavedBs25(row?: Record<string, any>) {
  if (!row) {
    return false;
  }
  return (
    rowHasBs25Candidates(row) &&
    !row.bs25_selection_status &&
    !row.bs25_selected_source &&
    !row.aibs25_status
  );
}

function rowNeedsBs25(row?: Record<string, any>) {
  if (!row) {
    return false;
  }
  return (
    !rowHasBs25Candidates(row) &&
    !["queued", "analyzing"].includes(row.bs25_status) &&
    !row.aibs25_status &&
    !row.bs25_selection_status
  );
}

function rowNeedsPacAi(row?: Record<string, any>) {
  return Boolean(row?.description?.trim()) && !["queued", "analyzing", "completed"].includes(row?.pac_ai_status);
}

const lightColumns: GridColDef[] = [
  {
    field: "company_item_code",
    headerName: "Company Item Code",
    width: 220,
    minWidth: 220,
    maxWidth: 220,
  },
  {
    field: "description",
    headerName: "Description",
    width: 360,
    minWidth: 360,
    maxWidth: 360,
  },
  {
    field: "bs25_status",
    headerName: "BS25",
    width: 260,
    sortable: false,
  },
];

const brandColumns: GridColDef[] = ["brand_raw", "brand", "brand_prefix"].map((field) => ({
  field, headerName: field, width: 185, sortable: false,
  valueFormatter: (value: unknown) => Array.isArray(value) ? value.join(" | ") : String(value ?? ""),
}));

const emptyConfig: McCodeConfig = {
  default_environment: "dev",
  environments: [],
  dataset_name: "",
  max_extra_columns: MAX_EXTRA_COLUMNS,
  lookup_actions_available: false,
  fuzzy_lookup_actions_available: false,
  ai_lookup_actions_available: false,
  bs25_actions_available: false,
  bs23_v2_actions_available: false,
  bs25ai_actions_available: false,
};

function toGridColumn(column: McCodeColumn): GridColDef {
  return {
    field: column.field,
    headerName: column.header_name,
    minWidth: 160,
    width: 190,
    type:
      column.value_type === "number" || column.value_type === "boolean"
        ? column.value_type
        : "string",
    valueFormatter: (value: unknown) =>
      Array.isArray(value) ? value.join(" | ") : value && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""),
  };
}

function mc_codeRowId(row: Record<string, any>) {
  return row.id;
}

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => null);
  return typeof data?.detail === "string" ? data.detail : fallback;
}

export default function McCode() {
  const [view, setView] = useState<McCodeView>("light");
  const [environment, setEnvironment] =
    useState<McCodeEnvironmentName>("dev");
  const [config, setConfig] = useState<McCodeConfig>(emptyConfig);
  const [companies, setCompanies] = useState<McCodeCompany[]>([]);
  const [selectedCompany, setSelectedCompany] =
    useState<McCodeCompany | null>(null);
  const [extraColumns, setExtraColumns] = useState<McCodeColumn[]>([]);
  const [selectedRows, setSelectedRows] = useState<Record<string, any>[]>([]);
  const [visibleRows, setVisibleRows] = useState<Record<string, any>[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);
  const [selectionResetToken, setSelectionResetToken] = useState(0);
  const [bs25AiBusy, setBs25AiBusy] = useState(false);
  const [pacAiBusy, setPacAiBusy] = useState(false);
  const [pacAiActive, setPacAiActive] = useState(false);
  const [pacAiPollToken, setPacAiPollToken] = useState(0);
  const [showBs25Columns, setShowBs25Columns] = useState(true);
  const [showPacAiColumns, setShowPacAiColumns] = useState(true);
  const [bs25Busy, setBs25Busy] = useState(false);
  const [bs23V2Busy, setBs23V2Busy] = useState(false);
  const [selectAllBusy, setSelectAllBusy] = useState(false);
  const [compactRows, setCompactRows] = useState(true);
  const [expandedCompactRows, setExpandedCompactRows] = useState<
    Set<string | number>
  >(new Set());
  const [externalSelection, setExternalSelection] = useState<{
    token: number;
    rows: Record<string, any>[];
  } | undefined>();
  const [currentQuery, setCurrentQuery] = useState<ServerGridFetchParams>({
    page: 0,
    pageSize: 100,
    search: "",
    filters: {},
  });
  const [pendingSelections, setPendingSelections] = useState<
    Record<string, PendingBs25Selection>
  >(loadPendingBs25Selections);
  const [bs25Drafts, setBs25Drafts] = useState<Record<string, Bs25Draft>>(
    loadBs25Drafts
  );
  const activeSelectionRequests = useRef<Set<string>>(new Set());
  const [actionError, setActionError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [detailRow, setDetailRow] = useState<Record<string, any> | null>(null);
  const [detailColumns, setDetailColumns] = useState<McCodeColumn[]>([]);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [setupError, setSetupError] = useState("");
  const [detailError, setDetailError] = useState("");

  useEffect(() => {
    persistPendingBs25Selections(pendingSelections);
  }, [pendingSelections]);

  useEffect(() => {
    persistBs25Drafts(bs25Drafts);
  }, [bs25Drafts]);

  useEffect(() => {
    setExpandedCompactRows(new Set());
  }, [environment, selectedCompany?.value, view]);

  useEffect(() => {
    let active = true;
    setLoadingConfig(true);

    fetch(`${backendBaseUrl}/api/mc-code/config`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await responseError(
              response,
              "Impossibile caricare la configurazione MC CODE"
            )
          );
        }
        return response.json();
      })
      .then((data: McCodeConfig) => {
        if (active) {
          setConfig(data);
          setEnvironment(data.default_environment || "dev");
        }
      })
      .catch((error) => {
        if (active) {
          setSetupError(error.message || "Errore inizializzazione MC CODE");
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
    setExternalSelection(undefined);
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
    fetch(`${backendBaseUrl}/api/mc-code/companies?${params.toString()}`)
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
        const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25/select`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            environment: pending.environment,
            company: pending.company,
            item_code: pending.itemCode,
            proposal_rank: pending.kind === "proposal" ? pending.rank : null,
            clear: pending.kind === "clear",
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
          setBs25Drafts((current) => {
            if (!current[rowKey]) {
              return current;
            }
            const next = { ...current };
            delete next[rowKey];
            persistBs25Drafts(next);
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

  const updateDraft = useCallback(
    (row: Record<string, any>, draft: Bs25Draft) => {
      if (!selectedCompany) {
        return;
      }
      const rowKey = bs25SelectionKey(
        environment,
        selectedCompany.value,
        row.item_code
      );
      setBs25Drafts((current) => ({ ...current, [rowKey]: draft }));
      setActionError("");
      setActionMessage("");
    },
    [environment, selectedCompany]
  );

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
        bs25Drafts[rowKey]?.rank === proposalRank
      ) {
        return;
      }
      updateDraft(row, {
        kind: "proposal",
        rank: proposalRank,
        updatedAt: Date.now(),
      });
    },
    [
      bs25Drafts,
      environment,
      pendingSelections,
      selectedCompany,
      updateDraft,
    ]
  );

  const handleDraftClear = useCallback(
    (row: Record<string, any>) => {
      updateDraft(row, { kind: "clear", updatedAt: Date.now() });
    },
    [updateDraft]
  );

  const handleDraftSave = useCallback(
    (row: Record<string, any>) => {
      if (!selectedCompany) {
        return;
      }
      const rowKey = bs25SelectionKey(
        environment,
        selectedCompany.value,
        row.item_code
      );
      const draft = bs25Drafts[rowKey];
      if (!draft || pendingSelections[rowKey]) {
        return;
      }
      const pending: PendingBs25Selection = {
        environment,
        company: selectedCompany.value,
        itemCode: String(row.item_code),
        companyItemCode: String(row.company_item_code),
        kind: draft.kind,
        rank: draft.rank,
        startedAt: Date.now(),
        requestId: createSelectionRequestId(),
      };
      setPendingSelections((current) => ({ ...current, [rowKey]: pending }));
      setActionError("");
      setActionMessage("");
    },
    [bs25Drafts, environment, pendingSelections, selectedCompany]
  );

  const handleBs25AiRowAction = useCallback(
    async (row: Record<string, any>, action: "escalate" | "decline" | "retry") => {
      if (!selectedCompany) {
        return;
      }
      setActionError("");
      setActionMessage("");
      try {
        const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25ai/${action}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            environment,
            company: selectedCompany.value,
            item_code: row.item_code,
          }),
        });
        if (!response.ok) {
          throw new Error(
            await responseError(response, "Impossibile aggiornare l'analisi BS25AI")
          );
        }
        setActionMessage(
          action === "escalate"
            ? `Analisi Sol xhigh avviata per ${row.company_item_code}`
            : action === "retry"
              ? `Retry BS25AI avviato per ${row.company_item_code}`
              : `${row.company_item_code} assegnato alla revisione umana`
        );
        setRefreshToken((current) => current + 1);
      } catch (error: any) {
        setActionError(error.message || "Errore azione BS25AI");
      }
    },
    [environment, selectedCompany]
  );

  const handlePacAi = useCallback(async (rows: Record<string, any>[]) => {
    if (!selectedCompany || rows.length === 0) return;
    setPacAiBusy(true);
    setActionError("");
    setActionMessage("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/mc-code/pac-ai`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ environment, company: selectedCompany.value, item_codes: rows.map((row) => row.item_code) }),
      });
      if (!response.ok) throw new Error(await responseError(response, "Impossibile avviare PAC-AI"));
      const result = await response.json();
      setActionMessage(`${result.accepted_item_codes?.length || 0} articoli inviati a PAC-AI`);
      setSelectedRows([]);
      setExternalSelection(undefined);
      setSelectionResetToken((value) => value + 1);
      setRefreshToken((value) => value + 1);
      setPacAiPollToken((value) => value + 1);
    } catch (error: any) {
      setActionError(error.message || "Errore avvio PAC-AI");
    } finally {
      setPacAiBusy(false);
    }
  }, [environment, selectedCompany]);

  useEffect(() => {
    if (!selectedCompany) { setPacAiActive(false); return; }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const params = new URLSearchParams({ environment, company: selectedCompany.value });
        const response = await fetch(`${backendBaseUrl}/api/mc-code/pac-ai/status?${params}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Stato PAC-AI non disponibile");
        const status = await response.json();
        if (controller.signal.aborted) return;
        setPacAiActive(Boolean(status.active));
        if (status.updated) setRefreshToken((value) => value + 1);
        // Periodically discover jobs submitted by other operators as well.
        timer = setTimeout(poll, status.active ? 3000 : 15000);
      } catch {
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [environment, selectedCompany, pacAiPollToken]);

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
        const draft = selectedCompany
          ? bs25Drafts[
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
              draft?.kind === "proposal"
                ? draft.rank
                : pending?.rank ??
              (serverSaving
                ? Number(params.row.bs25_pending_proposal_rank)
                : undefined)
            }
            onSelect={handleProposalSelect}
          />
        );
      },
    }));

    const leadingColumns = [lightColumns[0], lightColumns[1], ...brandColumns];
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
        const draft = selectedCompany
          ? bs25Drafts[
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
            draft={draft}
            pending={pending}
            onClear={handleDraftClear}
            onSave={handleDraftSave}
          />
        );
      },
    };
    const aiBs25Column: GridColDef = {
      field: "aibs25_status",
      headerName: "AIBS25",
      width: 390,
      minWidth: 340,
      sortable: false,
      filterable: false,
      renderCell: (params) => (
        <AiBs25Cell
          row={params.row}
          onEscalate={(row) => void handleBs25AiRowAction(row, "escalate")}
          onDecline={(row) => void handleBs25AiRowAction(row, "decline")}
          onRetry={(row) => void handleBs25AiRowAction(row, "retry")}
        />
      ),
    };
    const pacColumns = pacAiColumns((row) => void handlePacAi([row]));
    if (view === "light") {
      return [
        ...leadingColumns,
        bs25StatusColumn,
        ...proposalColumns,
        aiBs25Column,
        ...pacColumns,
      ];
    }

    return [
      ...leadingColumns,
      ...extraColumns.filter((column) => !brandColumns.some((brandColumn) => brandColumn.field === column.field))
        .slice(0, MAX_EXTRA_COLUMNS).map(toGridColumn),
      bs25StatusColumn,
      ...proposalColumns,
      aiBs25Column,
      ...pacColumns,
    ];
  }, [
    environment,
    extraColumns,
    bs25Drafts,
    handleDraftClear,
    handleDraftSave,
    handleProposalSelect,
    handleBs25AiRowAction,
    handlePacAi,
    pendingSelections,
    selectedCompany,
    view,
  ]);

  const columnVisibilityModel = useMemo(() => Object.fromEntries(columns.map(({ field }) => [
    field, field.startsWith("bs25_") || field.startsWith("aibs25_")
      ? showBs25Columns : field.startsWith("pac_ai_") ? showPacAiColumns : true,
  ])), [columns, showBs25Columns, showPacAiColumns]);

  const filterFields = useMemo(
    () =>
      columns
        .map((column) => column.field)
        .filter(
          (field) =>
            field !== "fuzzy_lookup_status" &&
            field !== "ai_lookup_status" &&
            field !== "aibs25_status" &&
            field !== "bs25_status" &&
            !field.startsWith("pac_ai_") &&
            !field.startsWith("bs25_proposal_")
        ),
    [columns]
  );

  const fetchRows = useCallback(
    async (params: ServerGridFetchParams): Promise<ServerGridResult> => {
      if (!selectedCompany || !selectedEnvironment?.available) {
        return { rows: [], total: 0 };
      }

      const response = await fetch(`${backendBaseUrl}/api/mc-code/search`, {
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
          await responseError(response, "Impossibile caricare i record MC CODE")
        );
      }

      const data: McCodeSearchResponse = await response.json();
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
        rows.filter(
          (row) =>
            ids.has(row.id) &&
            (rowHasUnsavedBs25(row) || rowNeedsBs25(row) || rowNeedsPacAi(row))
        )
      );
    },
    []
  );

  const handleRowsChange = useCallback(
    (rows: any[]) => {
      setVisibleRows(rows);
      if (!selectedCompany) {
        return;
      }
      setBs25Drafts((current) => {
        const next = { ...current };
        let changed = false;
        rows.forEach((row) => {
          const rowKey = bs25SelectionKey(
            environment,
            selectedCompany.value,
            row.item_code
          );
          const hasPersistedDecision = Boolean(row.bs25_selection_status);
          const aiResult = row.aibs25_result as Bs25AiResult | undefined;
          if (
            !next[rowKey] &&
            !pendingSelections[rowKey] &&
            !hasPersistedDecision &&
            row.aibs25_status === "completed" &&
            aiResult?.decision === "match" &&
            aiResult.proposed_master_code
          ) {
            if (aiResult.selected_candidate_rank) {
              next[rowKey] = {
                kind: "proposal",
                rank: aiResult.selected_candidate_rank,
                updatedAt: Date.now(),
              };
              changed = true;
            }
          }
        });
        return changed ? next : current;
      });
    },
    [environment, pendingSelections, selectedCompany]
  );

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
          ["queued", "analyzing"].includes(row.aibs25_status) ||
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
      const serverMatchesPending =
        (pending.kind === "proposal" &&
          row.bs25_selected_source === "bs25" &&
          Number(row.bs25_selected_proposal_rank) === pending.rank);
      const completedWithRequestId =
        pending.kind === "proposal" &&
        row.bs25_selection_request_id === pending.requestId &&
        row.bs25_selection_status === "completed" &&
        serverMatchesPending;
      const completedClear =
        pending.kind === "clear" &&
        !row.bs25_selection_status &&
        !row.bs25_selected_source &&
        !row.bs25_selected_master_code;
      const completedByLegacyBackend =
        pending.kind === "proposal" &&
        !row.bs25_selection_request_id &&
        row.bs25_selection_status !== "saving" &&
        Number(row.bs25_selected_proposal_rank) === pending.rank;
      if (completedWithRequestId || completedClear || completedByLegacyBackend) {
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
    setBs25Drafts((current) => {
      const next = { ...current };
      completed.forEach((rowKey) => delete next[rowKey]);
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

  const bs25SelectedRows = useMemo(
    () => selectedRows.filter(rowNeedsBs25),
    [selectedRows]
  );
  const bs25AiSelectedRows = useMemo(
    () => selectedRows.filter(rowHasUnsavedBs25),
    [selectedRows]
  );
  const pacAiSelectedRows = useMemo(() => selectedRows.filter(rowNeedsPacAi), [selectedRows]);

  const handleBs25 = useCallback(async () => {
    if (!selectedCompany || bs25SelectedRows.length === 0) {
      return;
    }
    setBs25Busy(true);
    setActionError("");
    setActionMessage("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          item_codes: bs25SelectedRows.map((row) => row.item_code),
        }),
      });
      if (!response.ok) {
        throw new Error(await responseError(response, "Impossibile avviare BS25"));
      }
      const result = await response.json();
      const accepted = result.accepted_item_codes?.length || 0;
      setActionMessage(`${accepted} record inviati al BS25 su lucianavm04`);
      setSelectedRows([]);
      setExternalSelection(undefined);
      setSelectionResetToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    } catch (error: any) {
      setActionError(error.message || "Errore avvio BS25");
    } finally {
      setBs25Busy(false);
    }
  }, [bs25SelectedRows, environment, selectedCompany]);

  const handleBs23V2 = useCallback(async () => {
    if (!selectedCompany || bs25SelectedRows.length === 0) {
      return;
    }
    setBs23V2Busy(true);
    setActionError("");
    setActionMessage("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25-v2`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          item_codes: bs25SelectedRows.map((row) => row.item_code),
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Impossibile avviare BS25_V2")
        );
      }
      const result = await response.json();
      const accepted = result.accepted_item_codes?.length || 0;
      setActionMessage(`${accepted} record inviati al BS25_V2 su lucianavm04`);
      setSelectedRows([]);
      setExternalSelection(undefined);
      setSelectionResetToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    } catch (error: any) {
      setActionError(error.message || "Errore avvio BS25_V2");
    } finally {
      setBs23V2Busy(false);
    }
  }, [bs25SelectedRows, environment, selectedCompany]);

  const handleBs25Ai = useCallback(async () => {
    if (!selectedCompany || bs25AiSelectedRows.length === 0) {
      return;
    }
    setBs25AiBusy(true);
    setActionError("");
    setActionMessage("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25ai`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          item_codes: bs25AiSelectedRows.map((row) => row.item_code),
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Impossibile avviare BS25AI")
        );
      }
      const result = await response.json();
      const accepted = result.accepted_item_codes?.length || 0;
      const locked = result.locked_item_codes?.length || 0;
      setActionMessage(
        `${accepted} record inviati a BS25AI${
          locked ? `; ${locked} erano gia bloccati` : ""
        }`
      );
      setSelectedRows([]);
      setExternalSelection(undefined);
      setSelectionResetToken((current) => current + 1);
      setRefreshToken((current) => current + 1);
    } catch (error: any) {
      setActionError(error.message || "Errore avvio BS25AI");
    } finally {
      setBs25AiBusy(false);
    }
  }, [bs25AiSelectedRows, environment, selectedCompany]);

  const handleSelectAllBs25 = useCallback(async () => {
    if (!selectedCompany) {
      return;
    }
    setSelectAllBusy(true);
    setActionError("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/mc-code/bs25ai/eligible`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          environment,
          company: selectedCompany.value,
          view,
          search: currentQuery.search,
          filters: currentQuery.filters,
        }),
      });
      if (!response.ok) {
        throw new Error(
          await responseError(response, "Impossibile selezionare i risultati BS25")
        );
      }
      const data = await response.json();
      const rows = Array.isArray(data.rows) ? data.rows : [];
      setSelectedRows(rows);
      setExternalSelection({ token: Date.now(), rows });
      setActionMessage(`${rows.length} risultati BS25 selezionati`);
    } catch (error: any) {
      setActionError(error.message || "Errore selezione risultati BS25");
    } finally {
      setSelectAllBusy(false);
    }
  }, [currentQuery.filters, currentQuery.search, environment, selectedCompany, view]);

  const handleRowClick = useCallback(
    async (params: GridRowParams) => {
      if (view !== "light" || !selectedCompany) {
        return;
      }

      setLoadingDetail(true);
      setDetailError("");
      setDetailRow(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/mc-code/detail`, {
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

        const detail: McCodeDetailResponse = await response.json();
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

  const changeView = (_: React.MouseEvent<HTMLElement>, nextView: McCodeView | null) => {
    if (!nextView) {
      return;
    }
    setView(nextView);
    setSelectedRows([]);
    setExternalSelection(undefined);
    setDetailRow(null);
    setDetailError("");
    if (nextView === "light") {
      setExtraColumns([]);
    }
  };

  const bs25AiAvailable = config.bs25ai_actions_available ?? false;
  const bs25AiDisabled =
    !bs25AiAvailable || bs25AiSelectedRows.length === 0 || bs25AiBusy;
  const bs25AiTooltip = !bs25AiAvailable
    ? "BS25AI non configurato"
    : bs25AiSelectedRows.length === 0
      ? "Seleziona almeno un record con BS25 completato e scelta non salvata"
      : "";
  const bs25Available =
    (config.bs25_actions_available ?? false) &&
    (config.pdb_available?.[environment] ?? true);
  const bs23V2Available =
    (config.bs25_v2_actions_available ?? config.bs23_v2_actions_available ?? false) &&
    (config.pdb_available?.[environment] ?? true);
  const deterministicLookupBusy = bs25Busy || bs23V2Busy;
  const bs25Disabled =
    !bs25Available || bs25SelectedRows.length === 0 || deterministicLookupBusy;
  const bs23V2Disabled =
    !bs23V2Available || bs25SelectedRows.length === 0 || deterministicLookupBusy;
  const bs25Tooltip = !bs25Available
    ? "Servizio BS25 su lucianavm04 non disponibile"
    : bs25SelectedRows.length === 0
      ? "Seleziona almeno un record senza proposte BS25"
      : "";
  const bs23V2Tooltip = !bs23V2Available
    ? "Servizio BS25_V2 su lucianavm04 non disponibile"
    : bs25SelectedRows.length === 0
      ? "Seleziona almeno un record senza proposte BS25"
      : "";
  const pacAiLimit = config.pac_ai?.max_batch_size || 100;
  const pacAiTooltip = !config.pac_ai?.available ? config.pac_ai?.message || "PAC-AI non configurato"
    : pacAiSelectedRows.length > pacAiLimit ? `Seleziona al massimo ${pacAiLimit} articoli`
    : pacAiSelectedRows.length === 0 ? "Seleziona articoli senza PAC-AI completato, anche già analizzati con BS25" : "";

  const toolbarLeft = (
    <>
      <FormControl size="small" sx={{ minWidth: 130 }}>
        <InputLabel id="mc-code-environment-label">Environment</InputLabel>
        <Select
          labelId="mc-code-environment-label"
          label="Environment"
          value={environment}
          disabled={loadingConfig}
          onChange={(event) =>
            setEnvironment(event.target.value as McCodeEnvironmentName)
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
          setExternalSelection(undefined);
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
        aria-label="Visualizzazione MC CODE"
      >
        <ToggleButton value="light">Light</ToggleButton>
        <ToggleButton value="full">Full</ToggleButton>
      </ToggleButtonGroup>

      <Box
        role="group"
        aria-label="Azioni BS25"
        sx={{
          display: "inline-flex",
          alignItems: "center",
          gap: 0.5,
          p: 0.5,
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1.5,
          bgcolor: "action.hover",
        }}
      >
        <Tooltip title={bs25Tooltip} disableHoverListener={!bs25Tooltip}>
          <span>
            <Button
              variant="outlined"
              startIcon={
                bs25Busy ? (
                  <CircularProgress size={16} />
                ) : (
                  <ScanSearch size={17} />
                )
              }
              disabled={bs25Disabled}
              onClick={handleBs25}
            >
              {bs25Busy
                ? "Elaborazione..."
                : `BS25${bs25SelectedRows.length ? ` (${bs25SelectedRows.length})` : ""}`}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title={bs23V2Tooltip} disableHoverListener={!bs23V2Tooltip}>
          <span>
            <Button
              variant="outlined"
              startIcon={
                bs23V2Busy ? (
                  <CircularProgress size={16} />
                ) : (
                  <ScanSearch size={17} />
                )
              }
              disabled={bs23V2Disabled}
              onClick={handleBs23V2}
            >
              {bs23V2Busy
                ? "Elaborazione..."
                : `BS25_V2${bs25SelectedRows.length ? ` (${bs25SelectedRows.length})` : ""}`}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Seleziona tutti i BS25 con scelta non salvata">
          <span>
            <IconButton
              aria-label="Seleziona tutti i BS25 con scelta non salvata"
              disabled={!selectedCompany || selectAllBusy || !bs25AiAvailable}
              onClick={handleSelectAllBs25}
              size="small"
              sx={{
                width: 36,
                height: 36,
                border: "1px solid",
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              {selectAllBusy ? (
                <CircularProgress size={16} />
              ) : (
                <CheckSquare size={17} />
              )}
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title={bs25AiTooltip} disableHoverListener={!bs25AiTooltip}>
          <span>
            <Button
              variant="contained"
              startIcon={
                bs25AiBusy ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <Sparkles size={17} />
                )
              }
              disabled={bs25AiDisabled}
              onClick={handleBs25Ai}
            >
              {bs25AiBusy
                ? "Invio..."
                : `BS25AI${bs25AiSelectedRows.length ? ` (${bs25AiSelectedRows.length})` : ""}`}
            </Button>
          </span>
        </Tooltip>
        <FormControlLabel sx={{ ml: 0.5, mr: 0.5 }} label="Colonne" control={
          <Switch size="small" checked={showBs25Columns}
            onChange={(_, checked) => setShowBs25Columns(checked)}
            slotProps={{ input: { role: "switch", "aria-label": "Mostra colonne BS25 e BS25AI" } }} />
        } />
      </Box>
      <Box role="group" aria-label="Azioni PAC-AI" sx={{ display: "inline-flex", alignItems: "center", gap: 0.5,
        p: 0.5, border: "1px solid", borderColor: "divider", borderRadius: 1.5, bgcolor: "action.hover" }}>
        <Tooltip title={pacAiTooltip}>
          <span><Button variant="contained" startIcon={pacAiBusy ? <CircularProgress size={16} color="inherit" /> : <Sparkles size={17} />}
            disabled={pacAiBusy || !config.pac_ai?.available || !pacAiSelectedRows.length || pacAiSelectedRows.length > pacAiLimit}
            onClick={() => void handlePacAi(pacAiSelectedRows)}>
            {pacAiBusy ? "Invio..." : `PAC-AI${pacAiSelectedRows.length ? ` (${pacAiSelectedRows.length})` : ""}`}
          </Button></span>
        </Tooltip>
        {pacAiActive && <Tooltip title="PAC-AI in elaborazione su lucianavm04"><CircularProgress size={18} sx={{ mx: 1 }} aria-label="PAC-AI in elaborazione" /></Tooltip>}
        <FormControlLabel sx={{ ml: 0.5, mr: 0.5 }} label="Colonne" control={
          <Switch size="small" checked={showPacAiColumns}
            onChange={(_, checked) => setShowPacAiColumns(checked)}
            slotProps={{ input: { role: "switch", "aria-label": "Mostra colonne PAC-AI" } }} />
        } />
      </Box>
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
        maxWidth: "100%",
        minHeight: 0,
        minWidth: 0,
        overflow: "hidden",
      }}
    >
      <Box
        sx={{
        ...mcCodeTypographyStyles,
        zoom: MC_CODE_LAYOUT_SCALE,
        height: `calc((100dvh - 16px) / ${MC_CODE_LAYOUT_SCALE})`,
        width: "100%",
        maxWidth: "100%",
        minHeight: 0,
        minWidth: 0,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {!selectedEnvironment?.available && selectedEnvironment?.message && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          {selectedEnvironment.message}
        </Alert>
      )}
      {config.bs25ai_mock_mode && (
        <Alert severity="info" sx={{ mb: 1 }}>
          BS25AI in modalita simulata: lucianavm04 non viene contattata.
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
          minWidth: 0,
          width: "100%",
          maxWidth: "100%",
          overflow: "hidden",
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
          title="MC CODE"
          columns={columns}
          columnVisibilityModel={columnVisibilityModel}
          fetchRows={fetchRows}
          getRowId={mc_codeRowId}
          pageSizeOptions={[25, 50, 100, 250, 500]}
          defaultPageSize={100}
          filterFields={filterFields}
          toolbarLeft={toolbarLeft}
          checkboxSelection
          frozenColumns={MC_CODE_FROZEN_COLUMNS}
          selectionHeaderAction={
            <Tooltip
              title={compactRows ? "Espandi tutti i record" : "Compatta tutti i record"}
            >
              <IconButton
                size="small"
                color={compactRows ? "primary" : "default"}
                aria-label={
                  compactRows ? "Espandi tutti i record" : "Compatta tutti i record"
                }
                aria-pressed={compactRows}
                onClick={(event) => {
                  event.stopPropagation();
                  setExpandedCompactRows(new Set());
                  setCompactRows((current) => !current);
                }}
                sx={{ width: 24, height: 24 }}
              >
                {compactRows ? <ChevronsDown size={15} /> : <ChevronsUp size={15} />}
              </IconButton>
            </Tooltip>
          }
          selectionCellAction={(params) => {
            const rowExpanded = expandedCompactRows.has(params.id);
            const label = !compactRows
              ? "Riga già espansa"
              : rowExpanded
                ? "Compatta questo record"
                : "Espandi questo record";
            return (
              <Tooltip title={label}>
                <span>
                  <IconButton
                    size="small"
                    disabled={!compactRows}
                    aria-label={label}
                    aria-pressed={compactRows ? rowExpanded : true}
                    onClick={(event) => {
                      event.stopPropagation();
                      setExpandedCompactRows((current) => {
                        const next = new Set(current);
                        if (next.has(params.id)) {
                          next.delete(params.id);
                        } else {
                          next.add(params.id);
                        }
                        return next;
                      });
                    }}
                    sx={{ width: 24, height: 24 }}
                  >
                    {rowExpanded || !compactRows ? (
                      <ChevronUp size={15} />
                    ) : (
                      <ChevronDown size={15} />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
            );
          }}
          onSelectionChange={handleSelectionChange}
          onQueryChange={setCurrentQuery}
          externalSelection={externalSelection}
          onRowsChange={handleRowsChange}
          onRowClick={handleRowClick}
          rowHeight={34}
          getRowHeight={(params) =>
            compactRows && !expandedCompactRows.has(params.id)
              ? 44
              : (showBs25Columns && params.model.bs25_status === "completed") || (showPacAiColumns && Boolean(params.model.pac_ai_status))
                ? "auto"
                : 52
          }
          estimatedRowHeight={compactRows ? 44 : 190}
          getRowClassName={(params) => {
            const lookupRunning = ["queued", "analyzing"].includes(
              params.row.bs25_status
            );
            const aiRunning = ["queued", "analyzing"].includes(
              params.row.aibs25_status
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
            return [
              lookupRunning || aiRunning || selectionSaving
                ? "mc-code-row-locked"
                : "",
              compactRows && !expandedCompactRows.has(params.id)
                ? "mc-code-row-compact"
                : "",
            ]
              .filter(Boolean)
              .join(" ");
          }}
          isRowSelectable={(params) =>
            rowHasUnsavedBs25(params.row) || rowNeedsBs25(params.row) || rowNeedsPacAi(params.row)
          }
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
          <McCodeDetailPanel
            row={detailRow}
            columns={detailColumns}
            onClose={() => setDetailRow(null)}
          />
        )}
      </Box>
      </Box>
    </Box>
  );
}

function Bs25StatusCell({
  row,
  draft,
  pending,
  onClear,
  onSave,
}: {
  row: Record<string, any>;
  draft?: Bs25Draft;
  pending?: PendingBs25Selection;
  onClear: (row: Record<string, any>) => void;
  onSave: (row: Record<string, any>) => void;
}) {
  const status = row.bs25_status;
  if (!status) {
    return <Typography variant="body2" color="text.secondary">-</Typography>;
  }
  if (status === "analyzing" || status === "queued") {
    return <Chip size="small" color="warning" label="Analyzing" />;
  }
  if (status === "failed") {
    return (
      <Stack spacing={0.5} sx={{ width: "100%", py: 0.5 }}>
        <Chip size="small" color="error" label="Errore" sx={{ alignSelf: "flex-start" }} />
        {row.bs25_error_message && (
          <Typography variant="caption" color="error.main">
            {row.bs25_error_message}
          </Typography>
        )}
      </Stack>
    );
  }
  const selectionSaving = Boolean(pending) || row.bs25_selection_status === "saving";
  if (selectionSaving) {
    const pendingLabel = pending?.kind === "proposal"
      ? `proposta ${pending.rank}`
      : "cancellazione";
    return (
      <Stack spacing={0.75} sx={{ width: "100%", pr: 1 }}>
        <Chip
          size="small"
          color="warning"
          label={`Salvataggio ${pendingLabel || "scelta"}`}
        />
        <LinearProgress color="warning" />
      </Stack>
    );
  }
  if (row.bs25_selection_status === "failed") {
    return <Chip size="small" color="error" label="Salvataggio fallito" />;
  }
  const selectedLabel = row.bs25_selected_master_code
    ? `Salvato: ${row.bs25_selected_master_code}`
    : "Scelta non salvata";
  const draftLabel = draft?.kind === "proposal"
    ? `Bozza: proposta ${draft.rank}`
    : draft?.kind === "clear"
        ? "Bozza: cancella"
        : selectedLabel;

  return (
    <Stack
      spacing={0.75}
      sx={{ width: "100%", py: 0.75, pr: 0.75 }}
      onClick={(event) => event.stopPropagation()}
    >
      <Chip
        size="small"
        color={draft ? "warning" : row.bs25_selected_master_code ? "success" : "info"}
        label={draftLabel}
        sx={{ alignSelf: "flex-start" }}
      />
      <Stack direction="row" spacing={0.5}>
        <Button size="small" variant="text" onClick={() => onClear(row)}>
          Cancella
        </Button>
        <Button
          size="small"
          variant="contained"
          disabled={!draft}
          onClick={() => onSave(row)}
        >
          Salva
        </Button>
      </Stack>
    </Stack>
  );
}

function AiBs25Cell({
  row,
  onEscalate,
  onDecline,
  onRetry,
}: {
  row: Record<string, any>;
  onEscalate: (row: Record<string, any>) => void;
  onDecline: (row: Record<string, any>) => void;
  onRetry: (row: Record<string, any>) => void;
}) {
  const status = row.aibs25_status;
  const stage = row.aibs25_stage;
  const result = row.aibs25_result as Bs25AiResult | undefined;
  const components = result?.components
    ? Object.entries(result.components).filter(([, value]) => Boolean(value))
    : [];
  const stageLabel =
    stage === "bs25_exact"
      ? "Exact normalizzato"
      : stage === "sol_xhigh_web"
        ? "Sol xhigh · web"
        : stage === "sol_low"
          ? "Sol low"
          : "BS25AI";

  if (!status) {
    return <Typography variant="body2" color="text.secondary">-</Typography>;
  }
  if (["queued", "analyzing"].includes(status)) {
    return (
      <Stack spacing={0.75} sx={{ width: "100%", py: 1, pr: 1 }}>
        <Chip size="small" color="warning" label={`${stageLabel}: analyzing`} />
        <LinearProgress color="warning" />
        {row.aibs25_flag && (
          <Typography variant="caption" color="warning.dark">
            {row.aibs25_flag}
          </Typography>
        )}
      </Stack>
    );
  }

  return (
    <Stack
      spacing={0.7}
      sx={{ width: "100%", py: 1, pr: 1, whiteSpace: "normal" }}
      onClick={(event) => event.stopPropagation()}
    >
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        <Chip
          size="small"
          color={status === "failed" ? "error" : status === "needs_human_review" ? "warning" : "success"}
          label={stageLabel}
        />
        {result?.decision && (
          <Chip size="small" variant="outlined" label={result.decision} />
        )}
        {result?.simulated && (
          <Chip size="small" color="info" variant="outlined" label="SIMULAZIONE" />
        )}
      </Stack>
      {row.aibs25_flag && (
        <Typography variant="caption" color="warning.dark" fontWeight={700}>
          {row.aibs25_flag}
        </Typography>
      )}
      {result?.proposed_master_code && (
        <Typography variant="subtitle2" fontWeight={800}>
          Proposta: {result.proposed_master_code}
          {result.selected_candidate_rank
            ? ` (candidato ${result.selected_candidate_rank})`
            : " (fuori Top-3)"}
        </Typography>
      )}
      {result?.confidence && (
        <Typography variant="caption" color="text.secondary">
          Affidabilita LLM: {result.confidence}
        </Typography>
      )}
      {result?.rationale && (
        <Typography variant="caption">{result.rationale}</Typography>
      )}
      {components.length > 0 && (
        <Box>
          {components.map(([key, value]) => (
            <Typography key={key} variant="caption" display="block" color="text.secondary">
              {key.replace(/_/g, " ")}: {value}
            </Typography>
          ))}
        </Box>
      )}
      {(result?.evidence || []).map((source) => (
        <Link
          key={source.url}
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          variant="caption"
          title={source.basis}
        >
          {source.title || source.url}
        </Link>
      ))}
      {status === "failed" && (
        <>
          <Typography variant="caption" color="error">
            {row.aibs25_error_message || "Analisi LLM non riuscita. Nessun codice e stato selezionato."}
          </Typography>
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<RefreshCw size={14} />}
            onClick={() => onRetry(row)}
          >
            Riprova
          </Button>
        </>
      )}
      {status === "completed" && stage === "sol_low" && (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="outlined" onClick={() => onEscalate(row)}>
            Sol xhigh con web
          </Button>
          <Button size="small" variant="text" onClick={() => onDecline(row)}>
            Non scalare
          </Button>
        </Stack>
      )}
    </Stack>
  );
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
  const attributes = [
    proposal.pack && `Pack: ${proposal.pack}`,
    proposal.measure && `Misura: ${proposal.measure}`,
  ].filter(Boolean);
  const quantity = [
    proposal.inner_count && `conteggio ${proposal.inner_count}`,
    proposal.inner_qty && `quantita ${proposal.inner_qty}`,
    proposal.pack_measure_unit,
  ].filter(Boolean);
  const evidenceSpans = Array.from(
    new Set(
      (proposal.source_evidence || [])
        .map((item) => item.source_span?.trim())
        .filter(Boolean)
    )
  );
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
        {proposal.brand && (
          <Typography variant="caption" color="text.secondary">
            Brand: {proposal.brand}
          </Typography>
        )}
        {proposal.manufacturer && (
          <Typography variant="caption" color="text.secondary">
            Produttore: {proposal.manufacturer}
          </Typography>
        )}
        {proposal.father_name && (
          <Typography variant="caption" color="text.secondary">
            Father Name: {proposal.father_name}
          </Typography>
        )}
        {attributes.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            {attributes.join(" · ")}
          </Typography>
        )}
        {proposal.feature && (
          <Typography variant="caption" color="text.secondary">
            Feature: {proposal.feature}
          </Typography>
        )}
        {quantity.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            Contenuto: {quantity.join(" · ")}
          </Typography>
        )}
        {proposal.extra && (
          <Typography variant="caption" color="text.secondary">
            Extra: {proposal.extra}
          </Typography>
        )}
        {evidenceSpans.length > 0 && (
          <Typography variant="caption" color="text.secondary">
            Evidenza sorgente: {evidenceSpans.join(" · ")}
          </Typography>
        )}
      </Stack>
    </Box>
  );
}

function McCodeDetailPanel({
  row,
  columns,
  onClose,
}: {
  row: Record<string, any>;
  columns: McCodeColumn[];
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
        minWidth: 0,
        maxWidth: "100%",
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
        <Box sx={{ minWidth: 0, flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={700} noWrap>
            {row.company_item_code || "Dettaglio record"}
          </Typography>
          <Typography variant="caption" color="text.secondary" component="div">
            Dettaglio completo in sola lettura
          </Typography>
        </Box>
        <Tooltip title="Chiudi">
          <IconButton size="small" sx={{ flexShrink: 0 }} onClick={onClose} aria-label="Chiudi dettaglio">
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
