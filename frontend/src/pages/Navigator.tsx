// AdminDashboardPage.tsx - stile Mantine UI con avatar e logout (/.auth/me)
import { IconHome2, IconSettings, IconLogout, IconTestPipe, IconCode, IconBrandGithub, IconBrowser, IconDatabase } from '@tabler/icons-react';
import { AppShell, AppShellNavbar, NavLink, ScrollArea, Text, Box, Stack, Group, Avatar, UnstyledButton, Code, Loader } from '@mantine/core';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Routes, Route } from 'react-router-dom';
import { Grid } from '@mantine/core';
import StorageBrowser from '../components/StorageBrowser';
import MantineStorageBrowser from '../components/MantineStorageBrowser';
import RunRScript from '../components/RunRScript';
import RunRScriptLog from '../components/RunRScriptLog';
import PDBCodifica from '../components/PDBCodifica';

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

  // Logout
  const handleLogout = () => {
    window.location.href = '/.auth/logout?post_logout_redirect_uri=/login';
  };

  // Avatar utente
  const avatarUrl = user
    ? `https://ui-avatars.com/api/?name=${encodeURIComponent(user.name)}&background=random&size=128`
    : '';

  // Layout Navigator
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
            <div> {/* DIV NavBar Upper */}
              {/* App name & version */}
              <Box mb="md">
                <Group justify="space-between">
                  <Text fw={700}>Luciana Navigator</Text>
                  <Code fw={700}>v1.0.0</Code>
                </Group>
              </Box>

              {/* NavBar */}
              <Box mb="md">
                <ScrollArea type="auto">
                  <Stack gap="xs">
                    <NavLink label="Home" leftSection={<IconHome2 size={18} />} component={Link} to="/" />
                    <NavLink label="Storage Browser" leftSection={<IconBrowser size={18} />}>
                      <NavLink label="Bronze" pl="md" component={Link} to="/navigator/file-browser-bronze" />
                      <NavLink label="Silver" pl="md" component={Link} to="/navigator/file-browser-silver" />
                    </NavLink>
                    <NavLink label="Tests" leftSection={<IconTestPipe size={18} />}>
                      <NavLink label="File Browser" pl="md" component={Link} to="/navigator/file-browser" />
                      <NavLink label="File Browser 2" pl="md" component={Link} to="/navigator/file-browser-bronze" />
                      <NavLink label="Launch R script" pl="md" component={Link} to="/navigator/run-r-script" />
                      <NavLink label="Launch R script - With R Log" pl="md" component={Link} to="/navigator/run-r-script-log" />
                    </NavLink>
                    <NavLink label="PDB" leftSection={<IconDatabase size={18} />}>
                      <NavLink label="Codifica PDB" pl="md" component={Link} to="/navigator/pdb-codifica" /> 
                    </NavLink>
                    <NavLink label="RStudio" leftSection={<IconCode size={18} />} component={Link} to="http://108.142.241.77:8787/"></NavLink>
                    <NavLink label="GitHub" leftSection={<IconBrandGithub size={18} />} component={Link} to="https://github.com/keystone-dev/luciana-project"></NavLink>
                    <NavLink label="Settings" leftSection={<IconSettings size={18} />} />
                  </Stack>
                </ScrollArea>
              </Box>
            </div>

            <div> {/* DIV NavBar Lower */}
              <Box>                
                {/* User details */}
                <UnstyledButton p="xs" w="100%">
                  <Group>
                    <Avatar src={avatarUrl} radius="xl" />
                    <Box style={{ flex: 1 }}>
                      <Text size="sm" fw={500} truncate="end">{user?.name}</Text>
                      <Text size="xs" c="dimmed" truncate="end">{user?.email}</Text>
                    </Box>
                  </Group>
                </UnstyledButton>

                {/* Logout */}
                <NavLink
                  label="Logout"
                  leftSection={<IconLogout size={18} />}
                  color="red"
                  variant="light"
                  onClick={handleLogout}
                  mt="sm"
                />
              </Box>
            </div>

          </>
        )}
      </AppShellNavbar>

      <AppShell.Main>
        <Routes>

          {/* HOME */}
          <Route path="/" element={<Text size="lg">Luciana Navigator</Text>} />

          <Route path="file-browser" element={
            <Grid>
              <Grid.Col span={4}>
                <StorageBrowser />
              </Grid.Col>
            </Grid>
          } />

          {/* FILE BROWSER - BRONZE */}
          <Route path="file-browser-bronze" element={
            <Grid>
              <Grid.Col span={4}>
                <MantineStorageBrowser containerKey="bronze"/>
              </Grid.Col>
            </Grid>
          } />

          {/* FILE BROWSER - SILVER */}
          <Route path="file-browser-silver" element={
            <Grid>
              <Grid.Col span={4}>
                <MantineStorageBrowser containerKey="silver"/>
              </Grid.Col>
            </Grid>
          } />

          {/* PDB - CODIFICA */}
          <Route path="pdb-codifica" element={
            <Grid>
              <Grid.Col span={12}>
                <PDBCodifica />
              </Grid.Col>
            </Grid>
          } />

          {/* LAUNCH R SCRIPT */}
          <Route path="run-r-script" element={
            <Grid>
              <Grid.Col span={12}>
                <RunRScript />
              </Grid.Col>
            </Grid>
          } />

          {/* LAUNCH R SCRIPT */}
          <Route path="run-r-script-log" element={
            <Grid>
              <Grid.Col span={12}>
                <RunRScriptLog />
              </Grid.Col>
            </Grid>
          } />

        </Routes>
      </AppShell.Main>
      
    </AppShell>
  );
}