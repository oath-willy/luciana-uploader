import { useEffect, useState } from 'react';

type FileNode = {
  name: string;
  type: 'folder' | 'file';
  children?: FileNode[];
};

type InternalNode = {
  name: string;
  type: 'folder' | 'file';
  children?: { [key: string]: InternalNode };
};

function buildTree(paths: string[]): FileNode[] {
  const root: { [key: string]: InternalNode } = {};

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
          ...(isFile ? {} : { children: {} }),
        };
      }

      if (!isFile) {
        current = current[key].children!;
      }
    });
  }

  function convert(node: { [key: string]: InternalNode }): FileNode[] {
    return Object.values(node).map((entry) => ({
      name: entry.name,
      type: entry.type,
      children: entry.children ? convert(entry.children) : undefined,
    }));
  }

  return convert(root);
}

export default function FileTree() {
  const [tree, setTree] = useState<FileNode[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/container`)
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
