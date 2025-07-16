import { useSearchParams } from 'react-router-dom';
import FileTreeExplorer from '../components/FileTreeExplorer';
import FileTreeBase from '../components/FileTreeBase';
import { useEffect, useState } from 'react';

export default function Explorer() {
  const [files, setFiles] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [params] = useSearchParams();
  const path = params.get("path"); // es: ?path=clienteA/gennaio
  const mode = params.get("mode") ?? "explorer";

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/container`)
      .then((res) => res.json())
      .then((data) => {
        if (!data.files || !Array.isArray(data.files)) {
          console.error("Dati inattesi dal backend:", data);
          setFiles([]);
          return;
        }
        setFiles(data.files);
      })
      .catch((err) => console.error("Errore caricamento:", err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: '2rem' }}>
      <h2>📂 Esplora contenuti dello storage "bronze"</h2>
      <p>
        Questa pagina mostra i file e le cartelle presenti nel container Azure.
        <br />
        Modalità: <strong>{mode === 'base' ? 'Base con espansione automatica' : 'Navigazione interattiva'}</strong>
      </p>
      <hr style={{ margin: '1rem 0' }} />
      {loading ? (
        <p>Caricamento...</p>
      ) : mode === 'base' ? (
        <FileTreeBase files={files} autoExpandPath={path || ''} />
      ) : (
        <FileTreeExplorer />
      )}
    </div>
  );
}
