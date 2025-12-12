import {
  IconHome2,
  IconSettings,
  IconLogout,
  IconTestPipe,
  IconCode,
  IconBrandGithub,
  IconBrowser,
  IconDatabase,
  IconChevronLeft,
  IconChevronRight,
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
  ActionIcon,
} from '@mantine/core';
import { useEffect, useState } from 'react';
import { Link, Routes, Route } from 'react-router-dom';
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
  const [navCollapsed, setNavCollapsed] = useState(false);

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
      padding="xs"
      navbar={{
        width: navCollapsed ? 64 : 300,
        breakpoint: 'sm',
        collapsed: { mobile: false },
      }}
    >
      <AppShellNavbar
        p="xs"
        style={{
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
        }}
      >
        {loading ? (
          <Loader />
        ) : (
          <>
            {/* NAVBAR TOP */}
            <div>
              <Box mb="sm">
                <Group justify="space-between" align="center">
                  {!navCollapsed && <Text fw={700}>Luciana Navigator</Text>}
                  {!navCollapsed && <Code fw={700}>v1.0.0</Code>}

                  <ActionIcon
                    variant="subtle"
                    onClick={() => setNavCollapsed((v) => !v)}
                  >
                    {navCollapsed ? (
                      <IconChevronRight size={18} />
                    ) : (
                      <IconChevronLeft size={18} />
                    )}
                  </ActionIcon>
                </Group>
              </Box>

              <ScrollArea type="auto">
                <Stack gap="xs">
                  <NavLink label={!navCollapsed ? "Home" : ""} leftSection={<IconHome2 size={18} />} component={Link} to="/" />

                  <NavLink label={!navCollapsed ? "Storage Browser" : ""} leftSection={<IconBrowser size={18} />}>
                    {!navCollapsed && (
                      <>
                        <NavLink label="Bronze" pl="md" component={Link} to="/navigator/file-browser-bronze" />
                        <NavLink label="Silver" pl="md" component={Link} to="/navigator/file-browser-silver" />
                        <NavLink label="Gold" pl="md" component={Link} to="/navigator/file-browser-gold" />
                      </>
                    )}
                  </NavLink>

                  <NavLink label={!navCollapsed ? "Tests" : ""} leftSection={<IconTestPipe size={18} />}>
                    {!navCollapsed && (
                      <>
                        <NavLink label="Launch R script" pl="md" component={Link} to="/navigator/run-r-script" />
                        <NavLink label="Launch R script - With R Log" pl="md" component={Link} to="/navigator/run-r-script-log" />
                      </>
                    )}
                  </NavLink>

                  <NavLink label={!navCollapsed ? "PDB" : ""} leftSection={<IconDatabase size={18} />}>
                    {!navCollapsed && (
                      <NavLink label="Codifica PDB" pl="md" component={Link} to="/navigator/pdb-codifica" />
                    )}
                  </NavLink>

                  <NavLink
                    label={!navCollapsed ? "RStudio" : ""}
                    leftSection={<IconCode size={18} />}
                    component={Link}
                    to="http://20.160.158.80:8787/"
                  />

                  <NavLink
                    label={!navCollapsed ? "GitHub" : ""}
                    leftSection={<IconBrandGithub size={18} />}
                    component={Link}
                    to="https://github.com/keystone-dev/luciana-project"
                  />

                  <NavLink label={!navCollapsed ? "Settings" : ""} leftSection={<IconSettings size={18} />} />
                </Stack>
              </ScrollArea>
            </div>

            {/* NAVBAR BOTTOM */}
            {!navCollapsed && (
              <Box>
                <UnstyledButton p="xs" w="100%">
                  <Group>
                    <Avatar src={avatarUrl} radius="xl" />
                    <Box style={{ flex: 1 }}>
                      <Text size="sm" fw={500} truncate="end">
                        {user?.name}
                      </Text>
                      <Text size="xs" c="dimmed" truncate="end">
                        {user?.email}
                      </Text>
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
            )}
          </>
        )}
      </AppShellNavbar>

      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Text size="lg">Luciana Navigator</Text>} />

          <Route path="file-browser-bronze" element={<MantineStorageBrowser containerKey="bronze" />} />
          <Route path="file-browser-silver" element={<MantineStorageBrowser containerKey="silver" />} />

          <Route path="pdb-codifica" element={<PDBCodifica />} />
          <Route path="run-r-script" element={<RunRScript />} />
          <Route path="run-r-script-log" element={<RunRScriptLog />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
