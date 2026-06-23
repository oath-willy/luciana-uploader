import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import {
  IconPlayerPlay,
  IconPower,
  IconRefresh,
  IconServer,
  IconUsers,
} from "@tabler/icons-react";

type VmStatus = {
  name: string;
  power_state: string;
  power_label: string;
  is_running: boolean;
  rstudio_url: string;
  rstudio_users: number | null;
  rstudio_users_available: boolean;
  rstudio_users_message: string;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

export default function ControlPanel() {
  const [vms, setVms] = useState<VmStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionVm, setActionVm] = useState<string | null>(null);
  const [error, setError] = useState("");

  const fetchVms = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${backendBaseUrl}/api/control-panel/vms`);
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Impossibile caricare lo stato delle VM");
      }

      setVms(await response.json());
    } catch (err: any) {
      setError(err.message || "Errore caricamento Control Panel");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVms();
  }, [fetchVms]);

  const runAction = async (vmName: string, action: "start" | "stop") => {
    setActionVm(vmName);
    setError("");

    try {
      const response = await fetch(
        `${backendBaseUrl}/api/control-panel/vms/${vmName}/action`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || "Azione VM non riuscita");
      }

      await fetchVms();
    } catch (err: any) {
      setError(err.message || "Errore azione VM");
    } finally {
      setActionVm(null);
    }
  };

  const summary = useMemo(() => {
    const running = vms.filter((vm) => vm.is_running).length;
    const activeUsers = vms.reduce(
      (total, vm) => total + (vm.rstudio_users_available ? vm.rstudio_users || 0 : 0),
      0
    );

    return { running, activeUsers };
  }, [vms]);

  return (
    <Box p="md">
      <Group justify="space-between" align="flex-start" mb="md">
        <Box>
          <Title order={2}>Control Panel</Title>
          <Text c="dimmed" size="sm">
            Stato operativo delle VM RStudio e azioni di accensione/spegnimento.
          </Text>
        </Box>

        <Button
          variant="light"
          leftSection={<IconRefresh size={16} />}
          onClick={fetchVms}
          loading={loading}
        >
          Aggiorna
        </Button>
      </Group>

      {error && (
        <Alert color="red" mb="md">
          {error}
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm" mb="md">
        <MetricBox label="VM accese" value={`${summary.running}/${vms.length || 2}`} />
        <MetricBox label="Utenti RStudio" value={String(summary.activeUsers)} />
        <MetricBox label="Monitorate" value="lucianavm03, lucianavm04" wide />
        <MetricBox label="Ultimo refresh" value={loading ? "in corso" : "completato"} />
      </SimpleGrid>

      {loading && vms.length === 0 ? (
        <Group justify="center" py="xl">
          <Loader />
        </Group>
      ) : (
        <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="md">
          {vms.map((vm) => (
            <VmCard
              key={vm.name}
              vm={vm}
              busy={actionVm === vm.name}
              onStart={() => runAction(vm.name, "start")}
              onStop={() => runAction(vm.name, "stop")}
            />
          ))}
        </SimpleGrid>
      )}
    </Box>
  );
}

function MetricBox({
  label,
  value,
  wide = false,
}: {
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <Card withBorder radius="sm" p="sm" style={{ minHeight: 76 }}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
        {label}
      </Text>
      <Text fw={700} size={wide ? "sm" : "xl"} mt={4}>
        {value}
      </Text>
    </Card>
  );
}

function VmCard({
  vm,
  busy,
  onStart,
  onStop,
}: {
  vm: VmStatus;
  busy: boolean;
  onStart: () => void;
  onStop: () => void;
}) {
  const userText = vm.rstudio_users_available
    ? String(vm.rstudio_users ?? 0)
    : "N/D";

  return (
    <Card withBorder radius="sm" p="md">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <Group gap="sm">
            <Box
              style={{
                width: 42,
                height: 42,
                borderRadius: 8,
                display: "grid",
                placeItems: "center",
                background: "#f1f3f5",
              }}
            >
              <IconServer size={22} />
            </Box>
            <Box>
              <Title order={4}>{vm.name}</Title>
              <Text size="sm" c="dimmed">
                RStudio endpoint
              </Text>
            </Box>
          </Group>

          <Badge color={vm.is_running ? "green" : "gray"} variant="light">
            {vm.is_running ? "Accesa" : "Spenta"}
          </Badge>
        </Group>

        <Divider />

        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          <StatusLine
            icon={<IconPower size={18} />}
            label="Status"
            value={vm.power_label || vm.power_state}
          />
          <StatusLine
            icon={<IconUsers size={18} />}
            label="Utenti RStudio"
            value={userText}
            hint={vm.rstudio_users_message}
          />
        </SimpleGrid>

        <Group justify="space-between" mt="xs">
          <Button
            component="a"
            href={vm.rstudio_url}
            target="_blank"
            rel="noreferrer"
            variant="subtle"
            disabled={!vm.is_running}
          >
            Apri RStudio
          </Button>

          <Group gap="xs">
            <Tooltip label="Avvia la VM" disabled={!vm.is_running}>
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                onClick={onStart}
                disabled={vm.is_running}
                loading={busy}
              >
                Avvia
              </Button>
            </Tooltip>
            <Tooltip label="Spegne e dealloca la VM">
              <Button
                color="red"
                variant="light"
                leftSection={<IconPower size={16} />}
                onClick={onStop}
                disabled={!vm.is_running}
                loading={busy}
              >
                Spegni
              </Button>
            </Tooltip>
          </Group>
        </Group>
      </Stack>
    </Card>
  );
}

function StatusLine({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Group gap="sm" align="flex-start">
      <Box mt={2}>{icon}</Box>
      <Box>
        <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
          {label}
        </Text>
        <Text fw={600}>{value}</Text>
        {hint && (
          <Text size="xs" c="dimmed" lineClamp={2}>
            {hint}
          </Text>
        )}
      </Box>
    </Group>
  );
}
