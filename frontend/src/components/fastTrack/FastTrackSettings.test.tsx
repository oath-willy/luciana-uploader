import { fireEvent, render, screen, within } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import FastTrackSettings from "./FastTrackSettings";
import { FastTrackStatus } from "./fastTrackApi";

const initial: FastTrackStatus = {
  enabled: true, configured: true, active: false, source_user: "wilson_sgroi",
  sources: { dashboards: {}, job: null }, data: { scripts: {}, job: null },
  dashboards: { gold: { label: "Gold monitoring", pending_sources: false }, forecast: { label: "Forecast", pending_sources: false } },
};
const available: FastTrackStatus = { ...initial, sources: {
  updated_at: "2026-10-05T12:00:00Z", dashboards: {
    gold: { available: true, updated_at: "2026-10-05T12:00:00Z", sha256: "gold" },
    forecast: { available: true, updated_at: "2026-10-05T12:00:00Z", sha256: "forecast" },
  },
} };
function respond(value: FastTrackStatus) { return { ok: true, json: async () => value }; }
function mount() { return render(<MantineProvider><FastTrackSettings /></MantineProvider>); }
beforeEach(() => { jest.restoreAllMocks(); });

test("has two sections and requires sources before running data scripts", async () => {
  global.fetch = jest.fn().mockResolvedValue(respond(initial));
  mount();
  await screen.findByText(/sorgente wilson_sgroi/);
  expect(screen.getByRole("region", { name: "Aggiornamento dashboard" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Aggiornamento dati" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Aggiorna tutti i dati" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Aggiorna entrambe le dashboard" })).toBeEnabled();
});

test("updates sources and shows completion separately from data", async () => {
  global.fetch = jest.fn().mockResolvedValueOnce(respond(initial)).mockResolvedValueOnce(respond({
    ...available, sources: { ...available.sources, job: { id: "source", kind: "sources", target: "all", status: "completed", stage: "completed", results: {} } },
  }));
  mount();
  await screen.findByText(/sorgente wilson_sgroi/);
  fireEvent.click(screen.getByRole("button", { name: "Aggiorna entrambe le dashboard" }));
  await screen.findByText(/Sorgenti dashboard recuperati/);
  expect(global.fetch).toHaveBeenLastCalledWith(expect.stringMatching(/\/sources\/refresh$/), expect.objectContaining({ body: '{"target":"all"}', method: "POST" }));
  expect(screen.getByRole("button", { name: "Aggiorna tutti i dati" })).toBeEnabled();
  expect(within(screen.getByRole("region", { name: "Aggiornamento dati" })).queryByText("Completato")).not.toBeInTheDocument();
});

test("runs each script independently and preserves last success on failure", async () => {
  const last = "2026-10-05T12:00:00Z";
  const before = { ...available, data: { ...available.data, updated_at: last, scripts: { gold_status: { completed_at: last } } } };
  global.fetch = jest.fn().mockResolvedValueOnce(respond(before)).mockResolvedValueOnce(respond({
    ...before, data: { ...before.data, job: { id: "job", kind: "data", target: "gold_status", status: "failed", stage: "failed", results: {}, error_message: "Script non riuscito" } },
  }));
  mount();
  await screen.findByText(/sorgente wilson_sgroi/);
  fireEvent.click(screen.getByRole("button", { name: "Avvia Monitoring · collection_status.R" }));
  await screen.findByText("Script non riuscito");
  expect(global.fetch).toHaveBeenLastCalledWith(expect.stringMatching(/\/data\/refresh$/), expect.objectContaining({ body: '{"target":"gold_status"}' }));
  expect(screen.getAllByText(/Ultimo aggiornamento completato:/).every(node => !node.textContent?.includes("Mai eseguito"))).toBe(true);
});

test("blocks all actions while either update is active", async () => {
  global.fetch = jest.fn().mockResolvedValue(respond({ ...available, active: true, data: { ...available.data,
    job: { id: "job", kind: "data", target: "all", status: "running", stage: "gold_status", results: {} } } }));
  const view = mount();
  await screen.findAllByText("Calcolo stato della raccolta");
  expect(screen.getByRole("button", { name: "Aggiorna entrambe le dashboard" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Avvia Forecast · link_runs.R" })).toBeDisabled();
  view.unmount();
});
