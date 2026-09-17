import ParquetSyncSettings from "./ParquetSyncSettings";

export default function McClassificationSettings() {
  return <ParquetSyncSettings
    title="MC Classification"
    description="Classificazioni Master Code condivise con lucianavm04."
    endpoint="/api/pdb/settings/mc-classification"
    actionLabel="Recupera"
    successMessage="File MC Classification copiato nel backend e su lucianavm04."
    stageLabels={{
      queued: "In coda", downloading: "Download da Azure Storage",
      uploading: "Copia su lucianavm04", completed: "Completato", failed: "Errore",
    }}
    progress={{ queued: 8, downloading: 40, uploading: 75, completed: 100, failed: 100 }}
    metrics={["file", "size", "rows", "columns"]}
    copyTargets={[
      { key: "backend", label: "Copia backend" },
      { key: "vm04", label: "Copia lucianavm04" },
    ]}
  >
    Recupera <strong>pdb_mc_classification.parquet</strong> da stkeystoneresearchdev e pubblica
    la versione corrente sia nel backend sia nella cartella PDB di lucianavm04.
  </ParquetSyncSettings>;
}
