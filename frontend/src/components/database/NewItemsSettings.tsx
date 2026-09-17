import ParquetSyncSettings from "./ParquetSyncSettings";

export default function NewItemsSettings() {
  return <ParquetSyncSettings
    title="New Items"
    description="Dataset degli item da classificare per MC CODE."
    endpoint="/api/pdb/settings/new-items"
    actionLabel="Recupera"
    successMessage="Dati MC CODE aggiornati."
    stageLabels={{
      queued: "In coda", downloading: "Download da Azure Storage",
      indexing: "Aggiornamento dati MC CODE", completed: "Completato", failed: "Errore",
    }}
    progress={{ queued: 8, downloading: 35, indexing: 80, completed: 100, failed: 100 }}
    metrics={["file", "size", "rows", "columns"]}
    copyTargets={[{ key: "backend", label: "Copia backend" }]}
  >
    Recupera <strong>pdb_new_items.parquet</strong> da stkeystoneresearchdev, lo copia nel backend
    e aggiorna i dati usati da MC CODE.
  </ParquetSyncSettings>;
}
