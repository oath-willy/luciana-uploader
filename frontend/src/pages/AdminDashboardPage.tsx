// AdminDashboardPage.tsx - con profilo da /.auth/me, senza MSAL
import {
  IconHome2,
  IconSettings,
  IconUser,
  IconFileAnalytics,
  IconLock,
  IconDatabaseImport,
  IconLogout,
} from '@tabler/icons-react';
import {
  AppShell,
  AppShellNavbar,
  NavLink,
  Code,
  ScrollArea,
  Text,
  Box,
  Stack,
  Group,
  Avatar,
  Loader,
} from '@mantine/core';
import { useEffect, useState } from 'react';

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
      <AppShellNavbar p="md">
        {loading ? (
          <Loader />
        ) : (
          <>
            <ScrollArea type="auto" style={{ flex: 1 }}>
              <Stack gap="xs">
                <NavLink label="Home" leftSection={<IconHome2 size={18} />} />
                <NavLink label="Users" leftSection={<IconUser size={18} />} />

                <NavLink label="Reports" leftSection={<IconFileAnalytics size={18} />}>
                  <NavLink label="Monthly" pl="md" />
                  <NavLink label="Annual" pl="md" />
                </NavLink>

                <NavLink label="Database" leftSection={<IconDatabaseImport size={18} />}>
                  <NavLink label="Imports" pl="md" />
                  <NavLink label="Exports" pl="md" />
                </NavLink>

                <NavLink label="Security" leftSection={<IconLock size={18} />} />
                <NavLink label="Settings" leftSection={<IconSettings size={18} />} />
              </Stack>
            </ScrollArea>

            {user && (
              <Box mt="md">
                <Group gap="sm">
                  <Avatar src={avatarUrl} radius="xl" size="md" />
                  <Box>
                    <Text size="sm" fw={600}>{user.name}</Text>
                    <Text size="xs" c="dimmed">{user.email}</Text>
                  </Box>
                </Group>
                <NavLink
                  label="Logout"
                  leftSection={<IconLogout size={18} />}
                  color="red"
                  variant="light"
                  onClick={handleLogout}
                />
                <Code mt="md" fw={700}>v1.0.0</Code>
              </Box>
            )}
          </>
        )}
      </AppShellNavbar>

      <AppShell.Main>
        <Text size="lg">Benvenuto nella dashboard amministrativa!</Text>
      </AppShell.Main>
    </AppShell>
  );
}