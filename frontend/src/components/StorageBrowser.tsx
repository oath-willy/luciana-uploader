import { useEffect, useState, useCallback } from 'react';
import { Anchor, Table, Text, Button, Group, Loader, Stack, Title, ActionIcon } from '@mantine/core';
import { ArrowLeft } from 'lucide-react';
import { Dropzone } from '@mantine/dropzone';
import { Pencil, Trash2 } from 'lucide-react';

import '../styles/global.css';

type Entry = {
  name: string;
  type: 'file' | 'folder';
  lastModified?: string;
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
        const rawFiles = data.files || [];
        const folders = new Set<string>();
        const items: Entry[] = [];

        for (const file of rawFiles) {
          const fullPath = file.name;
          const lastModified = file.last_modified;
          const relative = fullPath.replace(path === '' ? '' : `${path}/`, '');
          const parts = relative.split('/');

          if (parts.length > 1) {
            folders.add(parts[0]);
          } else if (parts[0]) {
            items.push({ name: parts[0], type: 'file', lastModified });
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

  const handleDelete = async (name: string) => {
    const confirmText = prompt(`Sei sicuro di voler eliminare "${name}"?\n\nScrivi DELETE per confermare:`);

    if (confirmText !== 'DELETE') {
      alert("Eliminazione annullata.");
      return;
    }

    const fullPath = joinPath(path, name);

    await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/delete?path=${fullPath}`, {
      method: 'DELETE',
    });

    fetchContents();
  };

  const handleRename = async (name: string) => {
    const extension = name.includes('.') ? name.split('.').pop() : '';
    const baseName = name.includes('.') ? name.substring(0, name.lastIndexOf('.')) : name;

    const input = prompt(`Nuovo nome per ${name}:`, baseName);
    if (!input || input === baseName) return;

    let newName = input;
    if (!input.includes('.') && extension) {
      newName = `${input}.${extension}`;
    }

    const oldPath = joinPath(path, name);
    const newPath = joinPath(path, newName);

    await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oldPath, newPath }),
    });

    fetchContents();
  };

  const rows = entries.map((entry) => (
    <tr key={entry.name}>

      <td>
        {
          entry.type === 'folder' ? (
            <Anchor onClick={() => setPath(joinPath(path, entry.name))} className="element-link">
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
          )
        }
      </td>

      <td style={{ paddingLeft: '3px', fontStyle: 'italic', fontSize: '11px' }}>
        {entry.lastModified ? new Date(entry.lastModified).toLocaleString() : '-'}
      </td>

      <td style={{ paddingLeft: '10px' }}>
        <ActionIcon 
          variant="unstyled"
          onClick={() => handleRename(entry.name)} 
          className="action-icon"
        >
          <Pencil size={13} />
        </ActionIcon>
      </td>

      <td>
        <ActionIcon 
          variant="unstyled"
          onClick={() => handleDelete(entry.name)} 
          className="action-icon"
        >
          <Trash2 size={13} />
        </ActionIcon>
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


      <Title order={4}>
        <ActionIcon
          variant="light"
          onClick={() => setPath(getParentPath(path))}
          className="action-icon"
          style = {{paggingRight: '5px'}}
          >
          <ArrowLeft size={13} />
        </ActionIcon>        
        📂 
        {breadcrumbs.map((bc, i) => (
          <Anchor
            key={i}
            onClick={() => setPath(bc.path)}
            className="breadcrumb-link"
          >
            <span className="breadcrumb-label">{bc.label}</span>
            {" / "}
          </Anchor>
        ))}
      </Title>

      {loading ? (
        <Loader />
      ) : (
        <Table className="compact-table">
          <thead>
            <tr>
              <th></th>
              <th></th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </Table>
      )}

    </Stack>
  );
}
