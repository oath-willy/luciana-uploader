import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import McClassificationSettings from "./McClassificationSettings";
import { MantineProvider } from "@mantine/core";

const status = {
  configured: true,
  source: "stkeystoneresearchdev/pdb/pdb_mc_classification.parquet",
  remote_path: "/vm/pdb/pdb_mc_classification.parquet",
  copies: { backend: null, vm04: null },
  file: { available: false, name: "pdb_mc_classification.parquet" },
  job: null,
};

beforeEach(() => {
  jest.restoreAllMocks();
  global.fetch = jest.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => status })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        ...status,
        file: { available: true, name: "pdb_mc_classification.parquet", modified_at: "2026-09-17T10:00:00Z" },
        copies: { backend: true, vm04: true },
        job: { status: "completed", stage: "completed", row_count: 42 },
      }),
    }) as jest.Mock;
});

test("shows both destinations and starts the classification synchronization", async () => {
  render(<MantineProvider><McClassificationSettings /></MantineProvider>);
  await screen.findByText("Copia backend");
  expect(screen.getByText("Copia lucianavm04")).toBeInTheDocument();
  expect(screen.getAllByText("Non ancora verificata")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Recupera" }));
  await screen.findByText("File MC Classification copiato nel backend e su lucianavm04.");
  expect(global.fetch).toHaveBeenLastCalledWith(
    expect.stringMatching(/\/api\/pdb\/settings\/mc-classification\/refresh$/), { method: "POST" },
  );
  expect(screen.getAllByText("Copia completata")).toHaveLength(2);
  await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
});
