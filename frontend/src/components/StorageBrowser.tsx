import { useEffect, useState } from 'react';
import {
  Breadcrumbs, Anchor, Table, Text, Button, Group, Loader, Stack, Title
} from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';

type Entry = {
  name: string;
  type: 'file' | 'folder';
};

function joinPath(...parts: string[]) {
  return parts.filter(Boolean).join('/');
}

function getParentPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
}

export default function StorageBrowser() {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchContents = () => {
    setLoading(true);
    fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/container?prefix=${path}`)
      .then(res => res.json())
      .then(data => {
        const files = data.files || [];
        const folders = new Set<string>();
        const items: Entry[] = [];

        for (const fullPath of files) {
          const relative = fullPath.slice(path.length).replace(/^\/+/, '');
          const parts = relative.split('/');
          if (parts.length > 1) {
            folders.add(parts[0]);
          } else if (parts[0]) {
            items.push({ name: parts[0], type: 'file' });
          }
        }

        for (const folder of folders) {
          items.unshift({ name: folder, type: 'folder' });
        }

        setEntries(items);
      })
      .catch(err => console.error('Errore fetch:', err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchContents();
  }, [path]);

  const handleUpload = async (files: File[]) => {
    const formData = new FormData();
    for (const file of files) {
      formData.append('file', file);
    }
    await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/upload?path=${path}`, {
      method: 'POST',
      body: formData,
    });
    fetchContents();
  };

  const rows = entries.map((entry) => (
    <tr key={entry.name}>
      <td>
        {entry.type === 'folder' ? (
          <Anchor onClick={() => setPath(joinPath(path, entry.name))}>
            📁 {entry.name}
          </Anchor>
        ) : (
          <Anchor
            href={`${process.env.REACT_APP_BACKEND_URL || ''}/api/download?path=${joinPath(path, entry.name)}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            📄 {entry.name}
          </Anchor>
        )}
      </td>
    </tr>
  ));

  const breadcrumbs = [
    { label: 'Root', path: '' },
    ...path.split('/').filter(Boolean).map((segment, index, array) => ({
      label: segment,
      path: array.slice(0, index + 1).join('/'),
    })),
  ];

  return (
    <Stack p="md">
      <Title order={3}>📂 Storage Browser</Title>
      <Breadcrumbs>
        {breadcrumbs.map((bc, i) => (
          <Anchor key={i} onClick={() => setPath(bc.path)}>{bc.label}</Anchor>
        ))}
      </Breadcrumbs>

      <Dropzone onDrop={handleUpload}>
        <Group justify="center" h={60}>
          <Text>Trascina i file qui o clicca per caricare</Text>
        </Group>
      </Dropzone>

      {loading ? (
        <Loader />
      ) : (
        <Table>
          <thead>
            <tr><th>Nome</th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </Table>
      )}

      {path && (
        <Button variant="light" onClick={() => setPath(getParentPath(path))}>
          🔙 Torna su
        </Button>
      )}
    </Stack>
  );
}
