import StorageBrowser from '../components/StorageBrowser';
import MantineStorageBrowser from '../components/MantineStorageBrowser';
import { Grid } from '@mantine/core';

export default function Explorer() {
  return (
    <div style={{ padding: '2rem' }}>
      <Grid>
        <Grid.Col span={5}>
          <StorageBrowser />
        </Grid.Col>
        <Grid.Col span={8}></Grid.Col>
        <Grid.Col span={5}>
          <MantineStorageBrowser containerKey="bronze"/>
        </Grid.Col>
        <Grid.Col span={8}></Grid.Col>
      </Grid>
    </div>
  );
}