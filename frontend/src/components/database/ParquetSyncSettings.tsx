import { ReactNode, useCallback, useEffect, useState } from "react";
import {
  ActionIcon, Alert, Badge, Box, Button, Card, Divider, Group, Progress,
  SimpleGrid, Stack, Text, Title, Tooltip,
} from "@mantine/core";
import {
  IconCircleCheck, IconCircleX, IconClock, IconCloudDownload,
  IconDatabase, IconRefresh,
} from "@tabler/icons-react";

export type ParquetSyncStatus = {
  configured?: boolean;
  source: string;
  remote_path?: string;
  copies?: Record<string, boolean | null>;
  file: { available: boolean; name: string; size_bytes?: number | null; modified_at?: string | null };
  job?: {
    status: "queued" | "running" | "completed" | "failed";
    stage: string;
    row_count?: number | null;
    column_count?: number | null;
    document_count?: number | null;
    error_message?: string | null;
  } | null;
};

type MetricName = "file" | "size" | "rows" | "columns" | "documents";

type Props = {
  title: string;
  description: string;
  children: ReactNode;
  endpoint: string;
  actionLabel?: string;
  successMessage: string;
  stageLabels: Record<string, string>;
  progress: Record<string, number>;
  metrics: MetricName[];
  copyTargets: Array<{ key: string; label: string }>;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

export default function ParquetSyncSettings({
  title, description, children, endpoint, actionLabel = "Recupera", successMessage,
  stageLabels, progress, metrics, copyTargets,
}: Props) {
  const [status, setStatus] = useState<ParquetSyncStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const active = status?.job?.status === "queued" || status?.job?.status === "running";

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const response = await fetch(`${backendBaseUrl}${endpoint}`);
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || `Impossibile leggere lo stato ${title}`);
      setStatus(payload);
      setError("");
    } catch (err: any) {
      setError(err.message || `Errore caricamento ${title}`);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [endpoint, title]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => { void load(true); }, 2500);
    return () => window.clearInterval(timer);
  }, [active, load]);

  const refresh = async () => {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${backendBaseUrl}${endpoint}/refresh`, { method: "POST" });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.detail || `Aggiornamento ${title} non avviato`);
      setStatus(payload);
    } catch (err: any) {
      setError(err.message || `Errore aggiornamento ${title}`);
    } finally {
      setSubmitting(false);
    }
  };

  const color = status?.job?.status === "failed" ? "red" : active ? "yellow"
    : status?.job?.status === "completed" ? "green" : "gray";

  return <Card component="section" withBorder radius="md" p="lg">
    <Stack gap="md">
      <Group justify="space-between" align="flex-start">
        <Group gap="sm" align="flex-start">
          <Box style={{ width: 44, height: 44, borderRadius: 8, display: "grid", placeItems: "center",
            background: "var(--mantine-color-gray-1)", flexShrink: 0 }}>
            <IconDatabase size={24} />
          </Box>
          <Box>
            <Title order={4}>{title}</Title>
            <Text c="dimmed" size="sm">{description}</Text>
          </Box>
        </Group>
        <Group gap="xs">
          <Badge color={color} variant="light">
            {status?.job ? stageLabels[status.job.stage] || status.job.status : "Mai eseguito"}
          </Badge>
          <Tooltip label="Aggiorna stato">
            <ActionIcon variant="subtle" aria-label={`Aggiorna stato ${title}`} loading={loading}
              onClick={() => { void load(); }}><IconRefresh size={16} /></ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      <Divider />
      <Text size="sm">{children}</Text>

      <SimpleGrid cols={{ base: 1, sm: 2, lg: metrics.length }} spacing="sm">
        {metrics.map((metric) => <Metric key={metric} name={metric} status={status} />)}
      </SimpleGrid>

      <SimpleGrid cols={{ base: 1, sm: copyTargets.length }} spacing="sm">
        {copyTargets.map((target) => <CopyResult key={target.key} label={target.label}
          value={status?.copies?.[target.key]} active={active} />)}
      </SimpleGrid>

      {active && <Box>
        <Group justify="space-between" mb={5}>
          <Text size="sm" fw={600}>{stageLabels[status?.job?.stage || ""] || "Aggiornamento in corso"}</Text>
          <Text size="xs" c="dimmed">{progress[status?.job?.stage || ""] || 0}%</Text>
        </Group>
        <Progress animated value={progress[status?.job?.stage || ""] || 0} color="yellow" />
      </Box>}

      {(error || status?.job?.error_message) && <Alert color="red">{error || status?.job?.error_message}</Alert>}
      {status?.job?.status === "completed" && <Alert color="green">{successMessage}</Alert>}
      {status && status.configured === false && (
        <Text size="xs" c="red">Connessione SSH a lucianavm04 non configurata nel backend.</Text>
      )}

      <Group justify="space-between" align="center">
        <Text size="xs" c="dimmed">Ultima copia nel backend: {formatDate(status?.file.modified_at)}</Text>
        <Button leftSection={<IconCloudDownload size={17} />} onClick={refresh}
          loading={submitting || active} disabled={status?.configured === false || active}>
          {actionLabel}
        </Button>
      </Group>
    </Stack>
  </Card>;
}

function Metric({ name, status }: { name: MetricName; status: ParquetSyncStatus | null }) {
  const values: Record<MetricName, [string, string]> = {
    file: ["File backend", status?.file.available ? status.file.name : "Non disponibile"],
    size: ["Dimensione", formatBytes(status?.file.size_bytes)],
    rows: ["Righe", formatNumber(status?.job?.row_count)],
    columns: ["Colonne", formatNumber(status?.job?.column_count)],
    documents: ["Documenti BS25", formatNumber(status?.job?.document_count)],
  };
  const [label, value] = values[name];
  return <Box p="sm" style={{ minWidth: 0, border: "1px solid var(--mantine-color-gray-3)", borderRadius: 6 }}>
    <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
    <Text fw={700} size="sm" mt={5} truncate="end" title={value}>{value}</Text>
  </Box>;
}

function CopyResult({ label, value, active }: { label: string; value?: boolean | null; active: boolean }) {
  const pending = value == null;
  const color = pending ? "gray" : value ? "green" : "red";
  const Icon = pending ? IconClock : value ? IconCircleCheck : IconCircleX;
  const result = pending ? (active ? "In corso" : "Non ancora verificata") : value ? "Copia completata" : "Copia non riuscita";
  return <Box p="sm" style={{ border: `1px solid var(--mantine-color-${color}-3)`, borderRadius: 6 }}>
    <Group gap="xs" wrap="nowrap">
      <Icon size={20} color={`var(--mantine-color-${color}-6)`} />
      <Box>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>{label}</Text>
        <Text size="sm" fw={700} c={color}>{result}</Text>
      </Box>
    </Group>
  </Box>;
}

function formatBytes(value?: number | null) {
  if (!value) return "-";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / Math.pow(1024, exponent)).toLocaleString("it-IT", { maximumFractionDigits: 1 })} ${units[exponent]}`;
}

function formatNumber(value?: number | null) {
  return typeof value === "number" ? value.toLocaleString("it-IT") : "-";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("it-IT");
}
