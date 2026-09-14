import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import {
  IconCheck,
  IconCloudDownload,
  IconDatabase,
  IconRefresh,
} from "@tabler/icons-react";
import NewItemsSettings from "./NewItemsSettings";

type SyncJob = {
  request_id: string;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  requested_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  updated_at: string;
  error_message?: string | null;
  remote_size_bytes?: number | null;
  local_size_bytes?: number | null;
  row_count?: number | null;
  column_count?: number | null;
  document_count?: number | null;
  retriever_version?: string | null;
};

type RefDumpStatus = {
  configured: boolean;
  source: string;
  file: {
    available: boolean;
    name: string;
    size_bytes?: number | null;
    modified_at?: string | null;
  };
  job?: SyncJob | null;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

const stageLabels: Record<string, string> = {
  queued: "In coda",
  fetching: "Download da Databricks su lucianavm04",
  downloading: "Copia nel backend",
  indexing: "Aggiornamento indice BS25",
  completed: "Completato",
  failed: "Errore",
};

const stageProgress: Record<string, number> = {
  queued: 8,
  fetching: 35,
  downloading: 65,
  indexing: 85,
  completed: 100,
  failed: 100,
};

export default function PdbSettings() {
  const [status, setStatus] = useState<RefDumpStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const loadStatus = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const response = await fetch(`${backendBaseUrl}/api/pdb/settings/ref-dump`);
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "Impossibile leggere lo stato del Reference PDB");
      }
      setStatus(await response.json());
    } catch (err: any) {
      setError(err.message || "Errore caricamento impostazioni PDB");
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const active = status?.job?.status === "queued" || status?.job?.status === "running";
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => loadStatus(true), 2500);
    return () => window.clearInterval(timer);
  }, [active, loadStatus]);

  const refreshDump = async () => {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(
        `${backendBaseUrl}/api/pdb/settings/ref-dump/refresh`,
        { method: "POST" }
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(payload?.detail || "Avvio aggiornamento Reference PDB non riuscito");
      }
      setStatus(payload);
    } catch (err: any) {
      setError(err.message || "Errore aggiornamento Reference PDB");
    } finally {
      setSubmitting(false);
    }
  };

  const job = status?.job;
  const progress = stageProgress[job?.stage || ""] || 0;
  const statusColor =
    job?.status === "completed"
      ? "green"
      : job?.status === "failed"
        ? "red"
        : active
          ? "yellow"
          : "gray";
  const metrics = useMemo(
    () => [
      {
        label: "File backend",
        value: status?.file.available ? status.file.name : "Non disponibile",
      },
      {
        label: "Dimensione",
        value: formatBytes(status?.file.size_bytes),
      },
      {
        label: "Righe PDB",
        value: formatNumber(job?.row_count),
      },
      {
        label: "Documenti BS25",
        value: formatNumber(job?.document_count),
        note: "Righe del PDB effettivamente indicizzate: hanno un riferimento, una descrizione utilizzabile e un Master Code completo.",
      },
    ],
    [job?.document_count, job?.row_count, status?.file]
  );

  return (
    <Box p="md">
      <Group justify="space-between" align="flex-start" mb="md">
        <Box>
          <Title order={2}>PDB Settings</Title>
          <Text c="dimmed" size="sm">
            Impostazioni e dati di riferimento del Product Database.
          </Text>
        </Box>
        <Button
          variant="light"
          leftSection={<IconRefresh size={16} />}
          onClick={() => loadStatus()}
          loading={loading}
        >
          Aggiorna stato
        </Button>
      </Group>

      {error && (
        <Alert color="red" mb="md" withCloseButton onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      <Card withBorder radius="md" p="lg">
        <Stack gap="md">
          <Group justify="space-between" align="flex-start">
            <Group gap="sm">
              <Box
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 8,
                  display: "grid",
                  placeItems: "center",
                  background: "var(--mantine-color-gray-1)",
                }}
              >
                <IconDatabase size={24} />
              </Box>
              <Box>
                <Title order={4}>Reference PDB</Title>
                <Text c="dimmed" size="sm">
                  Sorgente unica per il calcolo BS25 su lucianavm04.
                </Text>
              </Box>
            </Group>
            <Badge color={statusColor} variant="light">
              {job ? stageLabels[job.stage] || job.status : "Mai eseguito"}
            </Badge>
          </Group>

          <Divider />

          <Text size="sm">
            Avvia il recupero del Parquet corrente da Databricks sulla VM, lo copia nel
            backend come <strong>ref_pdb_dump.parquet</strong> e aggiorna l’indice usato
            dal servizio BS25. Viene mantenuta soltanto la versione corrente.
          </Text>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
            {metrics.map((metric) => (
              <Card key={metric.label} withBorder radius="sm" p="sm">
                <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
                  {metric.label}
                </Text>
                <Text fw={700} size="sm" mt={5} truncate="end">
                  {metric.value}
                </Text>
                {metric.note && (
                  <Text size="xs" c="dimmed" mt={6} lh={1.35}>
                    {metric.note}
                  </Text>
                )}
              </Card>
            ))}
          </SimpleGrid>

          {active && (
            <Box>
              <Group justify="space-between" mb={5}>
                <Text size="sm" fw={600}>
                  {stageLabels[job?.stage || ""] || "Aggiornamento in corso"}
                </Text>
                <Text size="xs" c="dimmed">
                  {progress}%
                </Text>
              </Group>
              <Progress value={progress} animated color="yellow" />
              <Text size="xs" c="dimmed" mt={5}>
                Puoi lasciare questa pagina: lo stato dell’operazione viene conservato.
              </Text>
            </Box>
          )}

          {job?.status === "completed" && (
            <Alert color="green" icon={<IconCheck size={18} />}>
              Aggiornamento completato {formatDate(job.completed_at)}. Il worker BS25 usa
              {job.retriever_version ? ` ${job.retriever_version}` : " il nuovo indice"}.
            </Alert>
          )}

          {job?.status === "failed" && job.error_message && (
            <Alert color="red" title="Aggiornamento non completato">
              {job.error_message}
            </Alert>
          )}

          <Group justify="space-between" align="center">
            <Text size="xs" c="dimmed">
              Ultima copia nel backend: {formatDate(status?.file.modified_at)}
            </Text>
            <Button
              leftSection={<IconCloudDownload size={17} />}
              onClick={refreshDump}
              loading={submitting || active}
              disabled={!status?.configured || active}
            >
              Recupera Reference PDB
            </Button>
          </Group>

          {status && !status.configured && (
            <Text size="xs" c="red">
              Connessione SSH a lucianavm04 non configurata nel backend.
            </Text>
          )}
        </Stack>
      </Card>
      <NewItemsSettings />
    </Box>
  );
}

function formatBytes(value?: number | null) {
  if (!value) return "—";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / Math.pow(1024, exponent)).toLocaleString("it-IT", {
    maximumFractionDigits: 1,
  })} ${units[exponent]}`;
}

function formatNumber(value?: number | null) {
  return typeof value === "number" ? value.toLocaleString("it-IT") : "—";
}

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("it-IT");
}
