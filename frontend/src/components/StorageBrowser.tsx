import { useEffect, useState } from 'react';
import {
  Anchor, Table, Text, Button, Group, Loader, Stack, Title
} from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { useCallback } from 'react';

import '../styles/global.css';

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

  const fetchContents = useCallback(() => {
    setLoading(true);
    fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/container?prefix=${path}`)
      .then(res => res.json())
      .then(data => {
        const files = data.files || [];
        const folders = new Set<string>();
        const items: Entry[] = [];

        for (const fullPath of files) {
          const relative = fullPath.replace(path === '' ? '' : `${path}/`, '');
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
  }, [path]);

  useEffect(() => {
    fetchContents();
  }, [fetchContents]);

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
          <Anchor 
            onClick={() => setPath(joinPath(path, entry.name))}
            className="element-link"
          >
            📁 {entry.name}
          </Anchor>
        ) : (
          <Anchor
            href={`${process.env.REACT_APP_BACKEND_URL || ''}/api/download?path=${joinPath(path, entry.name)}`}
            target="_blank"
            rel="noopener noreferrer"
            className="element-link"
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
    <Stack p="md" style={{backgroundColor: '#f9f9f9'}}>

      <Dropzone onDrop={handleUpload}>
        <Group justify="center" h={60}>
          <Text style={{border: '2.5px dotted #ffdf4e', backgroundColor : '#faf6e7', padding: '15px'}}>Trascina i file qui o clicca per caricare</Text>
        </Group>
      </Dropzone>

      {path && (
        <Button variant="light" onClick={() => setPath(getParentPath(path))}>
          🡸 Back
        </Button>
      )}

      <Title order={4}>📂 
        {breadcrumbs.map((bc, i) => (
          <Anchor key={i} onClick={() => setPath(bc.path)}>
            {bc.label + " / "}
          </Anchor>
        ))}
      </Title>

      {loading ? (
        <Loader />
      ) : (
        <Table>
          <thead>
            <tr><th></th></tr>
          </thead>
          <tbody>{rows}</tbody>
        </Table>
      )}

    </Stack>
  );
}
