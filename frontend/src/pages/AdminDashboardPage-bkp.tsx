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
  IconBrowser
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
                    <NavLink label="File Browser" pl="md" />
                  </NavLink>
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
        <Text size="lg">Benvenuto nella dashboard amministrativa!</Text>
      </AppShell.Main>
    </AppShell>
  );
}