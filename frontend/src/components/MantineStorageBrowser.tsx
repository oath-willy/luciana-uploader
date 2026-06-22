import {
  ActionIcon,
  Anchor,
  Breadcrumbs,
  Button,
  Group,
  Loader,
  Paper,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import { notifications } from '@mantine/notifications';
import {
  IconArrowLeft,
  IconChevronRight,
  IconDownload,
  IconFile,
  IconFolder,
  IconPencil,
  IconPlus,
  IconRefresh,
  IconTrash,
} from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

type Entry = {
  name: string;
  type: 'file' | 'folder';
  lastModified?: string;
};

type Props = {
  containerKey: string;
};

const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || '';

function joinPath(...parts: string[]) {
  return parts.filter(Boolean).join('/');
}

function getParentPath(path: string): string {
  const parts = path.split('/').filter(Boolean);
  parts.pop();
  return parts.join('/');
}

function apiUrl(endpoint: string, params: Record<string, string>) {
  const searchParams = new URLSearchParams(params);
  return `${backendBaseUrl}${endpoint}?${searchParams.toString()}`;
}

async function assertOk(response: Response, fallbackMessage: string) {
  if (response.ok) return;

  let message = fallbackMessage;
  try {
    const data = await response.json();
    message = data?.detail || fallbackMessage;
  } catch (error) {
    message = fallbackMessage;
  }
  throw new Error(message);
}

export default function MantineStorageBrowser({ containerKey }: Props) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(true);

  const containerLabel = useMemo(
    () => containerKey.charAt(0).toUpperCase() + containerKey.slice(1),
    [containerKey]
  );

  const fetchContents = useCallback(async () => {
    setLoading(true);

    try {
      const response = await fetch(
        apiUrl('/api/container', { prefix: path, container: containerKey })
      );
      await assertOk(response, 'Impossibile leggere il container');

      const data = await response.json();
      const items: Entry[] = (data.files || [])
        .filter((file: any) => file.name)
        .map((file: any) => ({
          name: file.name,
          type: file.type === 'folder' ? 'folder' : 'file',
          lastModified: file.last_modified,
        }));

      setEntries(items);
    } catch (error: any) {
      setEntries([]);
      notifications.show({
        title: `${containerLabel}: errore browsing`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  }, [containerKey, containerLabel, path]);

  useEffect(() => {
    fetchContents();
  }, [fetchContents]);

  const handleUpload = async (files: File[]) => {
    if (!files.length) return;

    try {
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(
          apiUrl('/api/upload', { path, container: containerKey }),
          {
            method: 'POST',
            body: formData,
          }
        );
        await assertOk(response, `Upload fallito: ${file.name}`);
      }

      notifications.show({
        title: `${containerLabel}: upload completato`,
        message: files.length === 1 ? files[0].name : `${files.length} file caricati`,
        color: 'green',
      });
      fetchContents();
    } catch (error: any) {
      notifications.show({
        title: `${containerLabel}: errore upload`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    }
  };

  const handleCreateFolder = async () => {
    const folderName = prompt('Nome cartella:')?.trim();
    if (!folderName) return;

    try {
      const response = await fetch(
        apiUrl('/api/create-folder', {
          path: joinPath(path, folderName),
          container: containerKey,
        }),
        { method: 'POST' }
      );
      await assertOk(response, 'Creazione cartella fallita');
      fetchContents();
    } catch (error: any) {
      notifications.show({
        title: `${containerLabel}: errore creazione`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    }
  };

  const handleDelete = async (entry: Entry) => {
    const confirmText = prompt(
      `Sei sicuro di voler eliminare "${entry.name}"?\n\nScrivi DELETE per confermare:`
    );
    if (confirmText !== 'DELETE') return;

    try {
      const endpoint = entry.type === 'folder' ? '/api/delete-folder' : '/api/delete';
      const response = await fetch(
        apiUrl(endpoint, {
          path: joinPath(path, entry.name),
          container: containerKey,
        }),
        { method: 'DELETE' }
      );
      await assertOk(response, 'Eliminazione fallita');
      fetchContents();
    } catch (error: any) {
      notifications.show({
        title: `${containerLabel}: errore eliminazione`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    }
  };

  const handleRename = async (entry: Entry) => {
    const extension = entry.type === 'file' && entry.name.includes('.')
      ? entry.name.split('.').pop()
      : '';
    const baseName = extension
      ? entry.name.substring(0, entry.name.lastIndexOf('.'))
      : entry.name;
    const input = prompt(`Nuovo nome per ${entry.name}:`, baseName)?.trim();

    if (!input || input === baseName) return;

    const newName = extension && !input.includes('.') ? `${input}.${extension}` : input;

    try {
      const response = await fetch(
        `${backendBaseUrl}${entry.type === 'folder' ? '/api/rename-folder' : '/api/rename'}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            oldPath: joinPath(path, entry.name),
            newPath: joinPath(path, newName),
            container: containerKey,
          }),
        }
      );
      await assertOk(response, 'Rinomina fallita');
      fetchContents();
    } catch (error: any) {
      notifications.show({
        title: `${containerLabel}: errore rinomina`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    }
  };

  const handleDownload = async (fullPath: string) => {
    try {
      const response = await fetch(
        apiUrl('/api/download', { path: fullPath, container: containerKey })
      );
      await assertOk(response, 'Download fallito');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = fullPath.split('/').pop() || 'file';
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error: any) {
      notifications.show({
        title: `${containerLabel}: errore download`,
        message: error?.message || 'Errore generico',
        color: 'red',
      });
    }
  };

  const breadcrumbs = [
    { label: containerLabel, path: '' },
    ...path.split('/').filter(Boolean).map((segment, index, array) => ({
      label: segment,
      path: array.slice(0, index + 1).join('/'),
    })),
  ];

  return (
    <Stack p="md" gap="sm">
      <Group justify="space-between" align="center">
        <Text fw={700}>{containerLabel} Storage</Text>
        <Group gap="xs">
          <Tooltip label="Aggiorna">
            <ActionIcon variant="subtle" onClick={fetchContents} aria-label="Aggiorna">
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
          <Button
            size="xs"
            variant="default"
            leftSection={<IconPlus size={16} color="orange" />}
            onClick={handleCreateFolder}
          >
            Nuova cartella
          </Button>
        </Group>
      </Group>

      <Dropzone onDrop={handleUpload}>
        <Group justify="center" h={64}>
          <Text size="sm" c="dimmed">
            Trascina i file qui o clicca per caricare
          </Text>
        </Group>
      </Dropzone>

      <Group gap="xs">
        <ActionIcon
          onClick={() => setPath(getParentPath(path))}
          variant="subtle"
          color="gray"
          disabled={!path}
          aria-label="Cartella superiore"
        >
          <IconArrowLeft size={16} />
        </ActionIcon>

        <Breadcrumbs separator={<IconChevronRight size="0.9rem" />}>
          {breadcrumbs.map((bc, index) => (
            <Anchor key={`${bc.path}-${index}`} onClick={() => setPath(bc.path)} size="sm">
              {bc.label}
            </Anchor>
          ))}
        </Breadcrumbs>
      </Group>

      {loading ? (
        <Loader />
      ) : entries.length === 0 ? (
        <Text size="sm" c="dimmed">
          Nessun elemento in questa cartella.
        </Text>
      ) : (
        <Stack gap="xs">
          {entries.map((entry) => {
            const fullPath = joinPath(path, entry.name);

            return (
              <Paper
                key={`${entry.type}-${entry.name}`}
                p="xs"
                radius="sm"
                withBorder
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  minHeight: 40,
                }}
              >
                <Group gap="xs" style={{ flex: 1, overflow: 'hidden' }}>
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
                          ? setPath(fullPath)
                          : handleDownload(fullPath)
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

                  {entry.type === 'file' && (
                    <Tooltip label="Scarica">
                      <ActionIcon
                        size="sm"
                        variant="subtle"
                        onClick={() => handleDownload(fullPath)}
                        aria-label="Scarica"
                      >
                        <IconDownload size={14} />
                      </ActionIcon>
                    </Tooltip>
                  )}

                  <Tooltip label="Rinomina">
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      onClick={() => handleRename(entry)}
                      aria-label="Rinomina"
                    >
                      <IconPencil size={14} />
                    </ActionIcon>
                  </Tooltip>

                  <Tooltip label="Elimina">
                    <ActionIcon
                      size="sm"
                      variant="subtle"
                      color="red"
                      onClick={() => handleDelete(entry)}
                      aria-label="Elimina"
                    >
                      <IconTrash size={14} />
                    </ActionIcon>
                  </Tooltip>
                </Group>
              </Paper>
            );
          })}
        </Stack>
      )}
    </Stack>
  );
}
