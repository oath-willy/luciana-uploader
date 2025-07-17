import { useEffect, useState } from 'react';
import FileTreeBase, { FileNode } from './FileTreeBase';

export default function FileTreeExplorer() {
  const [files, setFiles] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

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
      .catch((err) => console.error('Errore caricamento:', err))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (path: string) => {
    setExpanded(prev => {
      const newSet = new Set(prev);
      newSet.has(path) ? newSet.delete(path) : newSet.add(path);
      return newSet;
    });
  };

  const render = (node: FileNode, depth: number, path: string) => {
    const fullPath = path ? `${path}/${node.name}` : node.name;
    const isExpanded = expanded.has(fullPath);
    const isFolder = node.type === 'folder';

    return (
      <div key={fullPath} style={{ paddingLeft: depth * 20 }}>
        {isFolder && (
          <span style={{ cursor: 'pointer' }} onClick={() => toggle(fullPath)}>
            {isExpanded ? '🔽' : '▶️'}
          </span>
        )}{' '}
        {node.name}
        {isExpanded &&
          node.children?.map(child => render(child, depth + 1, fullPath))}
      </div>
    );
  };

  return (
    <div>
      {loading ? <p>Caricamento...</p> : (
        <FileTreeBase files={files} render={render} />
      )}
    </div>
  );
}
