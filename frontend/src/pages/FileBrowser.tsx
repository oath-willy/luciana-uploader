import StorageBrowser from '../components/StorageBrowser';
import MantineStorageBrowser from '../components/MantineStorageBrowser';
import { Grid } from '@mantine/core';

export default function Explorer() {
  return (
    <div style={{ padding: '2rem' }}>
      <Grid>
        <Grid.Col span={4}>
          <StorageBrowser />
        </Grid.Col>
        <Grid.Col span={4}>
          <MantineStorageBrowser />
        </Grid.Col>
      </Grid>
    </div>
  );
}