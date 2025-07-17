import { useEffect, useState } from 'react';
import {
  DetailsList,
  DetailsListLayoutMode,
  IColumn,
  IconButton,
  Stack,
  Text,
  Breadcrumb,
  IBreadcrumbItem
} from '@fluentui/react';

type FileEntry = {
  name: string;
  type: 'folder' | 'file';
};

function getParent(path: string): string {
  const parts = path.split('/');
  parts.pop();
  return parts.join('/');
}

function pathJoin(...parts: string[]): string {
  return parts.filter(Boolean).join('/');
}

function getBreadcrumbItems(path: string, setPath: (p: string) => void): IBreadcrumbItem[] {
  const parts = path.split('/').filter(Boolean);
  const items: IBreadcrumbItem[] = [{ text: 'Root', key: '', onClick: () => setPath('') }];
  let acc = '';
  for (const part of parts) {
    acc = pathJoin(acc, part);
    items.push({ text: part, key: acc, onClick: () => setPath(acc) });
  }
  return items;
}

export default function FileExplorerFluent() {
  const [files, setFiles] = useState<string[]>([]);
  const [currentPath, setCurrentPath] = useState('');
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
      .catch((err) => console.error("Errore caricamento:", err))
      .finally(() => setLoading(false));
  }, []);

  const entries: FileEntry[] = [];

  const normalized = files.map(f => f.replace(/^\/+|\/+$/g, ''));
  const visible = normalized.filter(f => f.startsWith(currentPath));
  const base = currentPath ? currentPath + '/' : '';

  const children = new Set<string>();
  for (const path of visible) {
    const rest = path.slice(base.length);
    if (!rest) continue;
    const next = rest.split('/')[0];
    const full = base + next;
    if (!children.has(full)) {
      children.add(full);
      const isFolder = normalized.some(p => p.startsWith(full + '/'));
      entries.push({ name: next, type: isFolder ? 'folder' : 'file' });
    }
  }

  const columns: IColumn[] = [
    {
      key: 'name',
      name: 'Nome',
      fieldName: 'name',
      minWidth: 100,
      onRender: (item: FileEntry) => (
        <span
          style={{ cursor: item.type === 'folder' ? 'pointer' : 'default' }}
          onDoubleClick={() => {
            if (item.type === 'folder') {
              setCurrentPath(pathJoin(currentPath, item.name));
            }
          }}
        >
          {item.type === 'folder' ? '📁' : '📄'} {item.name}
        </span>
      ),
    },
  ];

  return (
    <Stack tokens={{ childrenGap: 10 }} styles={{ root: { padding: 20 } }}>
      <Text variant="xLarge">📁 Esplora risorse (Fluent UI)</Text>
      <Breadcrumb items={getBreadcrumbItems(currentPath, setCurrentPath)} />
      {loading ? (
        <Text>Caricamento...</Text>
      ) : (
        <DetailsList
          items={entries}
          columns={columns}
          setKey="set"
          layoutMode={DetailsListLayoutMode.justified}
        />
      )}
    </Stack>
  );
}
