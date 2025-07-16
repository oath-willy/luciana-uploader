import { useEffect, useState } from 'react';

// Tipi
type FileNode = {
  name: string;
  type: 'folder' | 'file';
  children?: FileNode[];
};

function buildTree(paths: string[]): FileNode[] {
  const root: { [key: string]: FileNode } = {};

  for (const path of paths) {
    const parts = path.split('/');
    let current = root;

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1 && !path.endsWith('/');
      const key = part + (isFile ? '' : '/');

      if (!current[key]) {
        current[key] = {
          name: part,
          type: isFile ? 'file' : 'folder',
          children: isFile ? undefined : {},
        };
      }

      if (!isFile) {
        current = current[key].children as { [key: string]: FileNode };
      }
    });
  }

  function flatten(node: { [key: string]: FileNode }): FileNode[] {
    return Object.values(node).map((entry) => ({
      ...entry,
      children: entry.children ? flatten(entry.children) : undefined,
    }));
  }

  return flatten(root);
}

export default function FileTree() {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/container`)
      .then((res) => res.json())
      .then((data) => {
        const structured = buildTree(data.files);
        setTree(structured);
      })
      .catch((err) => console.error('Errore caricamento:', err))
      .finally(() => setLoading(false));
  }, []);

  const renderNode = (node: FileNode, depth = 0) => (
    <div key={node.name + depth} style={{ paddingLeft: depth * 20 }}>
      {node.type === 'folder' ? '📁' : '📄'} {node.name}
      {node.children?.map((child) => renderNode(child, depth + 1))}
    </div>
  );

  return (
    <div>
      {loading ? <p>Caricamento...</p> : tree.map((node) => renderNode(node))}
    </div>
  );
}
