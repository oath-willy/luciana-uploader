// AdminDashboardPage.tsx - stile Mantine UI con avatar e logout (/.auth/me)
import {
  IconHome2,
  IconSettings,
  IconUser,
  IconFileAnalytics,
  IconLock,
  IconDatabaseImport,
  IconLogout,
  IconTestPipe,
  IconCode, 
  IconBrandGithub
} from '@tabler/icons-react';
import {
  AppShell,
  AppShellNavbar,
  NavLink,
  ScrollArea,
  Text,
  Box,
  Stack,
  Group,
  Avatar,
  UnstyledButton,
  Code,
  Loader,
} from '@mantine/core';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Routes, Route } from 'react-router-dom';
import StorageBrowser from '../components/StorageBrowser';
import MantineStorageBrowser from '../components/MantineStorageBrowser';
import { Grid } from '@mantine/core';


type UserData = {
  name: string;
  email: string;
};

export default function AdminDashboardPage() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/.auth/me')
      .then((res) => res.json())
      .then((data) => {
        const info = data.clientPrincipal;
        if (info) {
          setUser({
            name: info.userDetails.split('@')[0],
            email: info.userDetails,
          });
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const handleLogout = () => {
    window.location.href = '/.auth/logout?post_logout_redirect_uri=/login';
  };

  const avatarUrl = user
    ? `https://ui-avatars.com/api/?name=${encodeURIComponent(user.name)}&background=random&size=128`
    : '';

  return (
    <AppShell
      padding="md"
      navbar={{
        width: 300,
        breakpoint: 'sm',
        collapsed: { mobile: false },
      }}
    >
      <AppShellNavbar p="md" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
        {loading ? (
          <Loader />
        ) : (
          <>
            <div>
              <Box mb="md">
                <Group justify="space-between">
                  <Text fw={700}>Luciana Admin</Text>
                  <Code fw={700}>v1.0.0</Code>
                </Group>
              </Box>
              <ScrollArea type="auto">
                <Stack gap="xs">
                  <NavLink label="Home" leftSection={<IconHome2 size={18} />} component={Link} to="/" />
                  <NavLink label="Tests" leftSection={<IconTestPipe size={18} />}>
                    <NavLink label="File Browser" pl="md" component={Link} to="/admin/file-browser" />
                    <NavLink label="File Browser 2" pl="md" component={Link} to="/admin/file-browser-2" />
                  </NavLink>
                  <NavLink label="RStudio" leftSection={<IconCode size={18} />} component={Link} to="http://108.142.241.77:8787/"></NavLink>
                  <NavLink label="GitHub" leftSection={<IconBrandGithub size={18} />} component={Link} to="https://github.com/keystone-dev/luciana-project"></NavLink>
                  <NavLink label="Settings" leftSection={<IconSettings size={18} />} />
                </Stack>
              </ScrollArea>
            </div>

            <Box>
              <UnstyledButton p="xs" w="100%">
                <Group>
                  <Avatar src={avatarUrl} radius="xl" />
                  <Box style={{ flex: 1 }}>
                    <Text size="sm" fw={500} truncate="end">{user?.name}</Text>
                    <Text size="xs" c="dimmed" truncate="end">{user?.email}</Text>
                  </Box>
                </Group>
              </UnstyledButton>

              <NavLink
                label="Logout"
                leftSection={<IconLogout size={18} />}
                color="red"
                variant="light"
                onClick={handleLogout}
                mt="sm"
              />
            </Box>
          </>
        )}
      </AppShellNavbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Text size="lg">Benvenuto nella dashboard amministrativa!</Text>} />
          <Route path="file-browser" element={
            <Grid>
              <Grid.Col span={4}>
                <StorageBrowser />
              </Grid.Col>
            </Grid>
          } />
          <Route path="file-browser-2" element={
            <Grid>
              <Grid.Col span={4}>
                <MantineStorageBrowser />
              </Grid.Col>
            </Grid>
            } />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}