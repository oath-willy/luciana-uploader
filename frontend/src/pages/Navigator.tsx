import {
  IconHome2,
  IconSettings,
  IconLogout,
  IconCode,
  IconBrandGithub,
  IconBrowser,
  IconDatabase,
  IconChevronLeft,
  IconChevronRight,
  IconChartLine,
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
import { Link, Navigate, Routes, Route, useLocation } from 'react-router-dom';
import MantineStorageBrowser from '../components/MantineStorageBrowser';
import PDBCodifica from '../components/PDBCodifica';
import ProductsTest from '../components/ProductsTest';
import ControlPanel from '../components/ControlPanel';
import CountriesDictionary from '../components/CountriesDictionary';
import Companies from '../components/database/Companies';
import FatherNames from '../components/database/FatherNames';
import Brands from '../components/database/Brands';
import McClassification from '../components/database/McClassification';
import Countries from '../components/database/Countries';
import Currencies from '../components/database/Currencies';
import CountriesCurrencies from '../components/database/CountriesCurrencies';
import McCode from '../components/McCode';
import ItemsCode from '../components/ItemsCode';
import PdbSettings from '../components/database/PdbSettings';
import FastTrackDashboard from '../components/fastTrack/FastTrackDashboard';
import FastTrackSettings from '../components/fastTrack/FastTrackSettings';
import fastTrackLayout from '../components/fastTrack/FastTrackLayout.module.css';

type UserData = {
  name: string;
  email: string;
};

const groupNavLinkStyles = {
  label: { fontWeight: 700 },
};

const pdbSettingsStyles = {
  root: {
    backgroundColor: 'var(--mantine-color-blue-light)',
    border: '1px solid var(--mantine-color-blue-light-color)',
    borderRadius: 'var(--mantine-radius-sm)',
  },
  label: { fontWeight: 700 },
};

export default function AdminDashboardPage() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);
  const [standardNavCollapsed, setStandardNavCollapsed] = useState(false);
  const [dashboardNavCollapsed, setDashboardNavCollapsed] = useState(true);
  const { pathname } = useLocation();
  const immersiveDashboard = process.env.REACT_APP_FAST_TRACK_ENABLED !== 'false' &&
    ['/fast-track/dashboard/monitoring', '/fast-track/dashboard/forecast']
      .includes(pathname.replace(/\/$/, ''));
  const navCollapsed = immersiveDashboard ? dashboardNavCollapsed : standardNavCollapsed;

  useEffect(() => {
    setDashboardNavCollapsed(true);
  }, [pathname]);

  useEffect(() => {
    const isLocal =
      window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1';

    if (isLocal) {
      setUser({
        name: 'local',
        email: 'local@dev',
      });
      setLoading(false);
      return;
    }

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
      padding={immersiveDashboard ? 0 : "xs"}
      className={immersiveDashboard ? fastTrackLayout.shell : undefined}
      navbar={{
        width: navCollapsed ? 64 : 300,
        breakpoint: immersiveDashboard ? 0 : 'sm',
        collapsed: { mobile: false },
      }}
    >
      <AppShellNavbar
        p="xs"
        className={immersiveDashboard ? fastTrackLayout.navbar : undefined}
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
                    aria-label={navCollapsed ? "Espandi menu" : "Collassa menu"}
                    onClick={() => immersiveDashboard
                      ? setDashboardNavCollapsed((v) => !v)
                      : setStandardNavCollapsed((v) => !v)}
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

                  <NavLink label={!navCollapsed ? "Storage Browser" : ""} leftSection={<IconBrowser size={18} />} styles={groupNavLinkStyles}>
                    {!navCollapsed && (
                      <>
                        <NavLink label="Bronze" pl="md" component={Link} to="/file-browser-bronze" />
                        <NavLink label="Silver" pl="md" component={Link} to="/file-browser-silver" />
                        <NavLink label="Gold" pl="md" component={Link} to="/file-browser-gold" />
                      </>
                    )}
                  </NavLink>

                  <NavLink label={!navCollapsed ? "Database" : ""} leftSection={<IconDatabase size={18} />} styles={groupNavLinkStyles}>
                    {!navCollapsed && (
                      <>
                        <NavLink label="PDB" pl="md" styles={groupNavLinkStyles}>
                          <NavLink label="Products" pl="lg" component={Link} to="/products" />
                          <NavLink label="Products Test" pl="lg" component={Link} to="/products-test" />
                          <NavLink label="CODE TOOLS" pl="lg" styles={groupNavLinkStyles}>
                            <NavLink label="MC CODE" pl="xl" component={Link} to="/mc-code" />
                            <NavLink label="ITEMS CODE" pl="xl" component={Link} to="/items-code" />
                          </NavLink>
                          <NavLink label="Companies" pl="lg" component={Link} to="/companies" />
                          <NavLink label="Brands" pl="lg" component={Link} to="/brands" />
                          <NavLink label="MC Classification" pl="lg" component={Link} to="/mc-classification" />
                          <NavLink label="Father Names" pl="lg" component={Link} to="/father-names" />
                          <NavLink
                            label="Settings"
                            pl="lg"
                            leftSection={<IconSettings size={16} />}
                            component={Link}
                            to="/pdb-settings"
                            styles={pdbSettingsStyles}
                          />
                        </NavLink>

                        <NavLink label="Domain Tables" pl="md" styles={groupNavLinkStyles}>
                          <NavLink label="Countries" pl="lg" component={Link} to="/countries" />
                          <NavLink label="Currencies" pl="lg" component={Link} to="/currencies" />
                          <NavLink label="Countries Currencies" pl="lg" component={Link} to="/countries-currencies" />
                        </NavLink>

                        <NavLink label="Utilities" pl="md" styles={groupNavLinkStyles}>
                          <NavLink label="Countries Dictionary" pl="lg" component={Link} to="/countries-dictionary" />
                        </NavLink>
                      </>
                    )}
                  </NavLink>

                  {process.env.REACT_APP_FAST_TRACK_ENABLED !== 'false' && (
                    <NavLink label={!navCollapsed ? "Fast Track" : ""} leftSection={<IconChartLine size={18} />} styles={groupNavLinkStyles}>
                      {!navCollapsed && <NavLink label="Dashboard" pl="md" styles={groupNavLinkStyles}>
                        <NavLink label="Gold monitoring" pl="lg" component={Link} to="/fast-track/dashboard/monitoring" />
                        <NavLink label="Forecast" pl="lg" component={Link} to="/fast-track/dashboard/forecast" />
                        <NavLink label="Settings" pl="lg" leftSection={<IconSettings size={16} />} component={Link}
                          to="/fast-track/dashboard/settings" styles={pdbSettingsStyles} />
                      </NavLink>}
                    </NavLink>
                  )}

                  <NavLink
                    label={!navCollapsed ? "RStudio" : ""}
                    leftSection={<IconCode size={18} />}
                    component={Link}
                    to="https://rstudio-ks.westeurope.cloudapp.azure.com/"
                  />

                  <NavLink
                    label={!navCollapsed ? "GitHub" : ""}
                    leftSection={<IconBrandGithub size={18} />}
                    component={Link}
                    to="https://github.com/keystone-dev/luciana-project"
                  />

                  <NavLink label={!navCollapsed ? "Settings" : ""} leftSection={<IconSettings size={18} />} styles={groupNavLinkStyles}>
                    {!navCollapsed && (
                      <NavLink label="Control Panel" pl="md" component={Link} to="/control-panel" />
                    )}
                  </NavLink>
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

      <AppShell.Main className={immersiveDashboard ? fastTrackLayout.main : undefined}>
        <Routes>
          <Route path="/" element={<Text size="lg">Luciana Navigator</Text>} />

          <Route path="file-browser-bronze" element={<MantineStorageBrowser containerKey="bronze" />} />
          <Route path="file-browser-silver" element={<MantineStorageBrowser containerKey="silver" />} />
          <Route path="file-browser-gold" element={<MantineStorageBrowser containerKey="gold" />} />

          <Route path="products" element={<PDBCodifica />} />
          <Route path="products-test" element={<ProductsTest />} />
          <Route path="mc-code" element={<McCode />} />
          <Route path="items-code" element={<ItemsCode />} />
          <Route path="codex" element={<Navigate to="/mc-code" replace />} />
          <Route path="companies" element={<Companies />} />
          <Route path="brands" element={<Brands />} />
          <Route path="mc-classification" element={<McClassification />} />
          <Route path="father-names" element={<FatherNames />} />
          <Route path="pdb-settings" element={<PdbSettings />} />
          {process.env.REACT_APP_FAST_TRACK_ENABLED !== 'false' && <>
            <Route path="fast-track/dashboard/monitoring" element={<FastTrackDashboard dashboard="gold" />} />
            <Route path="fast-track/dashboard/forecast" element={<FastTrackDashboard dashboard="forecast" />} />
            <Route path="fast-track/dashboard/settings" element={<FastTrackSettings />} />
          </>}
          <Route path="countries" element={<Countries />} />
          <Route path="currencies" element={<Currencies />} />
          <Route path="countries-currencies" element={<CountriesCurrencies />} />
          <Route path="pdb-codifica" element={<Navigate to="/products" replace />} />
          <Route path="countries-dictionary" element={<CountriesDictionary />} />
          <Route path="control-panel" element={<ControlPanel />} />
          <Route path="*" element={<Text role="status">Pagina non disponibile.</Text>} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
