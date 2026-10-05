import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import FastTrackDashboard from "./FastTrackDashboard";

// CRA's Jest 27 does not resolve React Router 7's package exports. Routing is checked in the browser.
jest.mock("react-router-dom", () => ({ Link: ({ to, children, ...props }: any) =>
  require("react").createElement("a", { ...props, href: to }, children) }), { virtual: true });

test("shows a settings link until a successful publication exists", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ dashboards: { gold: { label: "Gold monitoring", pending_sources: false, url: null } } }) });
  render(<MantineProvider><FastTrackDashboard dashboard="gold" /></MantineProvider>);
  await screen.findByText(/La dashboard non è ancora pubblicata/);
  expect(screen.getByRole("link", { name: "Fast Track Settings" })).toHaveAttribute("href", "/fast-track/dashboard/settings");
});

test("embeds the immutable publication without surrounding page controls", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ dashboards: { forecast: { label: "Forecast", pending_sources: true,
    url: "/api/fast-track/content/version/forecast_dashboard/index.html", updated_at: "2026-10-05T12:00:00Z" } } }) });
  render(<MantineProvider><FastTrackDashboard dashboard="forecast" /></MantineProvider>);
  const frame = await screen.findByTitle("Fast Track Forecast");
  expect(frame).toHaveAttribute("src", expect.stringContaining("/api/fast-track/content/version/forecast_dashboard/index.html"));
  expect(frame).toHaveAttribute("sandbox", "allow-scripts allow-same-origin allow-downloads");
  expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.queryByText(/Ultimo aggiornamento dati/)).not.toBeInTheDocument();
});
