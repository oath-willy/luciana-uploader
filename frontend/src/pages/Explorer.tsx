import FileTree from '../components/FileTree';

export default function Explorer() {
  return (
    <div style={{ padding: '2rem' }}>
      <h2>📂 Esplora contenuti dello storage "bronze"</h2>
      <p>Questa pagina mostra i file e le cartelle presenti nel container Azure.</p>
      <hr style={{ margin: '1rem 0' }} />
      <FileTree />
    </div>
  );
}
