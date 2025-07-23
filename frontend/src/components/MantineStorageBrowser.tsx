import { Group, Stack, Text, Tooltip, ActionIcon, Breadcrumbs, Anchor, Paper, Loader } from '@mantine/core';
import {
  IconFolder,
  IconFile,
  IconTrash,
  IconPencil,
  IconChevronRight,
  IconArrowLeft,
} from '@tabler/icons-react';
import { Dropzone } from '@mantine/dropzone';
import { useEffect, useState, useCallback } from 'react';

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

export default function MantineStorageBrowser() {
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
    for (const file of files) formData.append('file', file);
    await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/upload?path=${path}`, {
      method: 'POST',
      body: formData,
    });
    fetchContents();
  };

  const handleDelete = async (name: string) => {
    const confirmText = prompt(`Sei sicuro di voler eliminare "${name}"?\n\nScrivi DELETE per confermare:`);
    if (confirmText !== 'DELETE') return;

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
    if (!input.includes('.') && extension) newName = `${input}.${extension}`;

    const oldPath = joinPath(path, name);
    const newPath = joinPath(path, newName);

    await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oldPath, newPath }),
    });
    fetchContents();
  };

  const handleDownload = async (fullPath: string) => {
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/download?path=${fullPath}`);
      if (!response.ok) throw new Error('Errore durante il download');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fullPath.split('/').pop() || 'file';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      alert('Impossibile scaricare il file.');
    }
  };

  const breadcrumbs = [
    { label: 'Root', path: '' },
    ...path.split('/').filter(Boolean).map((segment, index, array) => ({
      label: segment,
      path: array.slice(0, index + 1).join('/'),
    })),
  ];

  return (
    <Stack p="md">
      <Dropzone onDrop={handleUpload}>
        <Group justify="center" h={60}>
          <Text style={{ border: '2px dotted #ffdf4e', backgroundColor: '#faf6e7', padding: '15px' }}>
            Trascina i file qui o clicca per caricare
          </Text>
        </Group>
      </Dropzone>

      <Group gap="xs">
        <ActionIcon onClick={() => setPath(getParentPath(path))} variant="subtle" color="gray">
          <IconArrowLeft size={16} />
        </ActionIcon>

        <Breadcrumbs separator={<IconChevronRight size="0.9rem" />}>
          {breadcrumbs.map((bc, i) => (
            <Anchor key={i} onClick={() => setPath(bc.path)}>
              {bc.label}
            </Anchor>
          ))}
        </Breadcrumbs>
      </Group>

      {loading ? (
        <Loader />
      ) : (
        <Stack gap="xs" style={{padding: '0px !important'}}>
          {entries.map((entry) => (
            <Paper
              key={entry.name}
              p="1"
              radius="md"              
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                backgroundColor: entry.type === 'folder' ? 'white' : 'white',
              }}
            >
              <Group gap="xs" style={{ flex: 1, overflow: 'hidden', padding: '0px !important' }}>
                {entry.type === 'folder' ? (
                  <IconFolder size={18} color="orange" />
                ) : (
                  <IconFile size={18} color="gray" />
                )}

                <Tooltip label={entry.name} withArrow>
                  <Text
                    size="sm"
                    fw={400}
                    style={{
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      cursor: 'pointer',
                    }}
                    onClick={() =>
                      entry.type === 'folder'
                        ? setPath(joinPath(path, entry.name))
                        : handleDownload(joinPath(path, entry.name))
                    }
                  >
                    {entry.name}
                  </Text>
                </Tooltip>
              </Group>

              <Group gap={8} style={{ flexShrink: 0 }}>
                <Text size="xs" c="dimmed">
                  {entry.lastModified
                    ? new Date(entry.lastModified).toLocaleString()
                    : ''}
                </Text>
                <ActionIcon size="xs" variant="light" onClick={() => handleRename(entry.name)}>
                  <IconPencil size={12} />
                </ActionIcon>
                <ActionIcon size="xs" variant="light" color="red" onClick={() => handleDelete(entry.name)}>
                  <IconTrash size={12} />
                </ActionIcon>
              </Group>
            </Paper>
          ))}
        </Stack>
      )}
    </Stack>
  );
}