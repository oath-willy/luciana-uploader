import { useCallback, useEffect, useState } from "react";
import { ActionIcon, Alert, Badge, Box, Button, Card, Divider, Group, Loader, Progress, Stack, Text, Title, Tooltip } from "@mantine/core";
import { IconCircleCheck, IconCloudDownload, IconDatabase, IconPlayerPlay, IconRefresh } from "@tabler/icons-react";
import { DashboardKey, FastTrackStatus, Job, ScriptKey, formatUpdate, readFastTrackStatus, refreshFastTrack } from "./fastTrackApi";

const labels: Record<string, string> = { queued: "In coda", downloading: "Recupero dashboard", preparing: "Preparazione",
  gold_links: "Collegamento dati monitoring", gold_status: "Calcolo stato della raccolta", forecast_links: "Collegamento dati forecast",
  validating: "Verifica e pubblicazione", completed: "Completato", failed: "Errore" };
const progress: Record<string, number> = { queued: 5, downloading: 35, preparing: 10, gold_links: 25, gold_status: 50, forecast_links: 75, validating: 90 };
const scripts: Array<{ key: ScriptKey; label: string; description: string }> = [
  { key: "gold_links", label: "Monitoring · link_runs.R", description: "Collega le ultime run complete e compatibili dei clienti." },
  { key: "gold_status", label: "Monitoring · collection_status.R", description: "Ricalcola lo stato della raccolta e gli indicatori della pipeline." },
  { key: "forecast_links", label: "Forecast · link_runs.R", description: "Collega il workbook dell’ultima run forecast completa." },
];

export default function FastTrackSettings() {
  const [status, setStatus] = useState<FastTrackStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try { setStatus(await readFastTrackStatus()); setError(""); }
    catch (e: any) { setError(e.message); }
    finally { if (!quiet) setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!status?.active) return;
    const timer = window.setInterval(() => { void load(true); }, 2500);
    return () => window.clearInterval(timer);
  }, [status?.active, load]);
  const refresh = async (kind: "sources" | "data", target: string) => {
    setSubmitting(true); setError("");
    try { setStatus(await refreshFastTrack(kind, target)); }
    catch (e: any) { setError(e.message); }
    finally { setSubmitting(false); }
  };
  const disabled = !status || !status.configured || status.active || submitting;
  const hasSources = Boolean(status?.sources.dashboards.gold?.available && status?.sources.dashboards.forecast?.available);
  return <Box p="md">
    <Group justify="space-between" mb="md">
      <Box><Title order={2}>Fast Track Settings</Title>
        <Text size="sm" c="dimmed">Dashboard e dati Fast Track · sorgente {status?.source_user || "lucianavm04"}</Text></Box>
      <Tooltip label="Aggiorna stato"><ActionIcon aria-label="Aggiorna stato Fast Track" loading={loading} variant="subtle"
        onClick={() => { void load(); }}><IconRefresh size={18} /></ActionIcon></Tooltip>
    </Group>
    {loading && !status && <Loader aria-label="Caricamento impostazioni" />}
    {error && <Alert color="red" mb="md">{error}</Alert>}
    {status && !status.configured && <Alert color="yellow" mb="md">Connessione SSH a lucianavm04 non configurata.</Alert>}
    <Stack gap="lg">
      <Card component="section" withBorder radius="md" p="lg" aria-label="Aggiornamento dashboard">
        <Stack gap="md">
          <Group justify="space-between"><Group><IconCloudDownload size={25} /><Box>
            <Title order={4}>Aggiornamento dashboard</Title><Text c="dimmed" size="sm">Recupera le modifiche delle due dashboard dall’utente sorgente.</Text>
          </Box></Group><JobBadge job={status?.sources.job} /></Group>
          <Divider />
          <Text size="sm">Recupera pagine, risorse e script R. La nuova versione viene pubblicata dopo l’aggiornamento dei dati.</Text>
          {(["gold", "forecast"] as DashboardKey[]).map(key => <Box key={key} p="sm" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 6 }}>
            <Group justify="space-between"><Box><Text fw={700} size="sm">{key === "gold" ? "Gold monitoring" : "Forecast"}</Text>
              <Text size="xs" c="dimmed">Ultimo recupero: {formatUpdate(status?.sources.dashboards[key]?.updated_at)}</Text>
            </Box><Button size="xs" variant="light" disabled={disabled || !hasSources} onClick={() => { void refresh("sources", key); }}>
              {key === "gold" ? "Aggiorna monitoring" : "Aggiorna forecast"}</Button></Group>
          </Box>)}
          <JobFeedback job={status?.sources.job} success="Sorgenti dashboard recuperati. Aggiorna i dati per pubblicare la nuova versione." />
          <Group justify="space-between"><Text size="xs" c="dimmed">Ultimo aggiornamento completato: {formatUpdate(status?.sources.updated_at)}</Text>
            <Button leftSection={<IconCloudDownload size={17} />} disabled={disabled}
              loading={submitting || Boolean(status?.active && ["queued", "running"].includes(status.sources.job?.status || ""))}
              onClick={() => { void refresh("sources", "all"); }}>Aggiorna entrambe le dashboard</Button></Group>
        </Stack>
      </Card>
      <Card component="section" withBorder radius="md" p="lg" aria-label="Aggiornamento dati">
        <Stack gap="md">
          <Group justify="space-between"><Group><IconDatabase size={25} /><Box><Title order={4}>Aggiornamento dati</Title>
            <Text c="dimmed" size="sm">Avvia gli script R e pubblica i nuovi dati per le dashboard.</Text>
          </Box></Group><JobBadge job={status?.data.job} /></Group>
          <Divider />
          <Text size="sm">Avvia uno script oppure tutti e tre in sequenza. Durante il lavoro resta disponibile l’ultima versione completata.</Text>
          {scripts.map(script => <Box key={script.key} p="sm" style={{ border: "1px solid var(--mantine-color-gray-3)", borderRadius: 6 }}>
            <Group justify="space-between"><Box><Text size="sm" fw={700}>{script.label}</Text><Text size="xs" c="dimmed">{script.description}</Text>
              <Text size="xs" c="dimmed" mt={4}>Ultima esecuzione completata: {formatUpdate(status?.data.scripts[script.key]?.completed_at)}</Text></Box>
              <Button size="xs" variant="light" leftSection={<IconPlayerPlay size={14} />} disabled={disabled || !hasSources}
                aria-label={`Avvia ${script.label}`} onClick={() => { void refresh("data", script.key); }}>Avvia</Button></Group>
          </Box>)}
          <JobFeedback job={status?.data.job} success="Esecuzione completata. I dati disponibili sono stati pubblicati nelle dashboard." />
          {!hasSources && <Text size="xs" c="dimmed">Recupera prima entrambe le dashboard.</Text>}
          <Group justify="space-between"><Text size="xs" c="dimmed">Ultimo aggiornamento completato: {formatUpdate(status?.data.updated_at)}</Text>
            <Button leftSection={<IconPlayerPlay size={17} />} disabled={disabled || !hasSources}
              loading={Boolean(status?.active && ["queued", "running"].includes(status.data.job?.status || ""))}
              onClick={() => { void refresh("data", "all"); }}>Aggiorna tutti i dati</Button></Group>
        </Stack>
      </Card>
    </Stack>
  </Box>;
}

function JobBadge({ job }: { job?: Job | null }) {
  return <Badge color={job?.status === "failed" ? "red" : job?.status === "completed" ? "green" : job ? "yellow" : "gray"} variant="light">
    {job ? labels[job.stage] || job.stage : "Mai eseguito"}</Badge>;
}

function JobFeedback({ job, success }: { job?: Job | null; success: string }) {
  if (!job) return null;
  if (job.status === "failed") return <Alert color="red">{job.error_message || "Aggiornamento non riuscito"}</Alert>;
  if (job.status === "completed") return <Alert color="green" icon={<IconCircleCheck size={18} />}>{success}</Alert>;
  return <Box><Text size="sm" fw={600} mb={6}>{labels[job.stage] || "Aggiornamento in corso"}</Text>
    <Progress animated value={progress[job.stage] || 10} color="yellow" aria-label="Avanzamento aggiornamento" /></Box>;
}
