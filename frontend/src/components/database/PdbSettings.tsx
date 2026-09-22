import { Box, Stack, Text, Title } from "@mantine/core";
import ParquetSyncSettings from "./ParquetSyncSettings";
import NewItemsSettings from "./NewItemsSettings";
import McClassificationSettings from "./McClassificationSettings";
import BrandsDictionarySettings from "./BrandsDictionarySettings";

export default function PdbSettings() {
  return <Box p="md">
    <Box mb="md">
      <Title order={2}>PDB Settings</Title>
      <Text c="dimmed" size="sm">Impostazioni e dati di riferimento del Product Database.</Text>
    </Box>

    <Stack gap="lg">
      <ParquetSyncSettings
        title="Reference PDB"
        description="Sorgente unica per il calcolo BS25 su lucianavm04."
        endpoint="/api/pdb/settings/ref-dump"
        actionLabel="Recupera"
        successMessage="Reference PDB copiato nel backend e su lucianavm04; indice BS25 aggiornato."
        stageLabels={{
          queued: "In coda", fetching: "Download su lucianavm04", downloading: "Copia nel backend",
          indexing: "Aggiornamento indice BS25", completed: "Completato", failed: "Errore",
        }}
        progress={{ queued: 8, fetching: 35, downloading: 65, indexing: 85, completed: 100, failed: 100 }}
        metrics={["file", "size", "rows", "documents"]}
        copyTargets={[
          { key: "backend", label: "Copia backend" },
          { key: "vm04", label: "Copia lucianavm04" },
        ]}
      >
        Recupera il Parquet corrente da Databricks su lucianavm04, lo copia nel backend come
        <strong> ref_pdb_dump.parquet</strong> e aggiorna l’indice usato dal servizio BS25.
      </ParquetSyncSettings>
      <NewItemsSettings />
      <McClassificationSettings />
      <BrandsDictionarySettings />
    </Stack>
  </Box>;
}
