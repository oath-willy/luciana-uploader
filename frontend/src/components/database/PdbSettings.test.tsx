import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import PdbSettings from "./PdbSettings";

beforeEach(() => {
  jest.restoreAllMocks();
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      configured: true,
      source: "fixture.parquet",
      copies: {},
      file: { available: false, name: "fixture.parquet" },
      job: null,
    }),
  }) as jest.Mock;
});

test("uses the same recovery action for every PDB dataset", async () => {
  render(<MantineProvider><PdbSettings /></MantineProvider>);

  await screen.findByRole("heading", { name: "Reference PDB" });
  expect(screen.getByRole("heading", { name: "New Items" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "MC Classification" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Brands Dictionary" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Recupera" })).toHaveLength(4);
});
