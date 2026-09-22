import ParquetSyncSettings from "./ParquetSyncSettings";

export default function BrandsDictionarySettings() {
  return <ParquetSyncSettings
    title="Brands Dictionary"
    description="Dizionario dei brand disponibile per le funzioni PDB."
    endpoint="/api/pdb/settings/brands-dictionary"
    actionLabel="Recupera"
    successMessage="Brands Dictionary copiato nel backend."
    stageLabels={{
      queued: "In coda", downloading: "Download da Azure Storage",
      completed: "Completato", failed: "Errore",
    }}
    progress={{ queued: 8, downloading: 45, completed: 100, failed: 100 }}
    metrics={["file", "size", "rows", "columns"]}
    copyTargets={[{ key: "backend", label: "Copia backend" }]}
  >
    Recupera <strong>pdb_brands_dictionary.parquet</strong> da stkeystoneresearchdev e
    pubblica atomicamente la versione corrente nel backend.
  </ParquetSyncSettings>;
}
