import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Box, Button, Group, Loader, Progress, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconCloudDownload, IconRefresh } from "@tabler/icons-react";

type NewItemsStatus = {
  source: string;
  file: { available: boolean; name: string; size_bytes?: number | null; modified_at?: string | null };
  job?: {
    status: "queued" | "running" | "completed" | "failed";
    stage: string;
    row_count?: number | null;
    error_message?: string | null;
  } | null;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";
const stages: Record<string, string> = {
  queued: "In coda", downloading: "Download da Azure Storage",
  indexing: "Aggiornamento dati MC CODE", completed: "Completato", failed: "Errore",
};

export default function NewItemsSettings() {
  const [status, setStatus] = useState<NewItemsStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const active = status?.job?.status === "queued" || status?.job?.status === "running";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${backendBaseUrl}/api/pdb/settings/new-items`);
      if (!response.ok) throw new Error("Impossibile leggere lo stato New Items");
      setStatus(await response.json());
      setError("");
    } catch (err: any) {
      setError(err.message);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [active, load]);

  const refresh = async () => {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch(`${backendBaseUrl}/api/pdb/settings/new-items/refresh`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Aggiornamento non avviato");
      setStatus(payload);
    } catch (err: any) { setError(err.message); }
    finally { setSubmitting(false); }
  };

  const color = status?.job?.status === "failed" ? "red" : active ? "yellow" : status?.job?.status === "completed" ? "green" : "gray";
  return (
    <Box component="section" mt="xl" pt="lg" style={{ borderTop: "1px solid var(--mantine-color-gray-3)" }}>
      <Stack gap="md">
        <Group justify="space-between">
          <Title order={4}>New Items</Title>
          <Group gap="sm">
            {loading && <Loader size="xs" />}
            <Badge color={color} variant="light">{status?.job ? stages[status.job.stage] || status.job.status : "Mai eseguito"}</Badge>
            <Button variant="subtle" size="xs" leftSection={<IconRefresh size={16} />} onClick={load}>Aggiorna stato</Button>
          </Group>
        </Group>
        <Text size="sm" c="dimmed">{status?.source || "stkeystoneresearchdev/pdb/pdb_new_items.parquet"}</Text>
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Box><Text size="xs" c="dimmed">FILE BACKEND</Text><Text fw={600}>{status?.file.available ? status.file.name : "Non disponibile"}</Text></Box>
          <Box><Text size="xs" c="dimmed">RIGHE</Text><Text fw={600}>{status?.job?.row_count?.toLocaleString("it-IT") ?? "-"}</Text></Box>
          <Box><Text size="xs" c="dimmed">ULTIMA COPIA</Text><Text fw={600}>{status?.file.modified_at ? new Date(status.file.modified_at).toLocaleString("it-IT") : "-"}</Text></Box>
        </SimpleGrid>
        {active && <Progress animated value={status?.job?.stage === "indexing" ? 80 : 35} color="yellow" />}
        {(error || status?.job?.error_message) && <Alert color="red">{error || status?.job?.error_message}</Alert>}
        {status?.job?.status === "completed" && <Alert color="green">Dati MC CODE aggiornati.</Alert>}
        <Group justify="flex-end">
          <Button leftSection={<IconCloudDownload size={17} />} onClick={refresh} loading={submitting || active}>Recupera New Items</Button>
        </Group>
      </Stack>
    </Box>
  );
}
