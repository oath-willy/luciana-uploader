import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import Brands from "./Brands";
import {
  createBrandRaw,
  fetchBrandRaw,
  fetchBrands,
  updateBrandRaw,
} from "./pdbBrandsApi";


jest.mock("./pdbBrandsApi");
jest.mock("../common/ServerDataGrid", () => {
  const React = require("react");
  return {
    __esModule: true,
    default: (props: any) => {
      const [rows, setRows] = React.useState([]);
      React.useEffect(() => {
        props.fetchRows({ page: 0, pageSize: 50, search: "", filters: {} })
          .then((result: any) => setRows(result.rows));
      }, [props.fetchRows, props.refreshToken]);
      return (
        <section>
          <h2>{props.title}</h2>
          {props.toolbarLeft}
          {rows.map((row: any) => props.onRowClick ? (
            <button key={props.getRowId(row)} onClick={() => props.onRowClick({ row })}>
              {props.columns.map((column: any) => row[column.field]).join(" ")}
            </button>
          ) : (
            <div key={props.getRowId(row)}>
              {props.columns.map((column: any) => (
                <div key={column.field}>
                  {column.renderCell
                    ? column.renderCell({ value: row[column.field], row })
                    : row[column.field]}
                </div>
              ))}
            </div>
          ))}
        </section>
      );
    },
  };
});


beforeEach(() => {
  jest.resetAllMocks();
  (fetchBrands as jest.Mock).mockResolvedValue({
    rows: [{ brand: "ACME", prefix: "A2, AC" }],
    total: 1,
  });
  (fetchBrandRaw as jest.Mock).mockResolvedValue({
    rows: [{ record_key: "id:7", brand_raw: "Acme Incorporated", change_status: "original" }],
    total: 1,
  });
  (updateBrandRaw as jest.Mock).mockResolvedValue({
    row: { record_key: "id:7", brand_raw: "Acme corrected", change_status: "modified" },
    edits_file: "pdb_brands_dictionary_edits.parquet",
  });
  (createBrandRaw as jest.Mock).mockResolvedValue({
    row: { record_key: "new:1", brand_raw: "Acme manual", change_status: "added" },
    edits_file: "pdb_brands_dictionary_edits.parquet",
  });
});


test("opens the selected brand card and loads its brand_raw occurrences", async () => {
  render(<Brands />);

  fireEvent.click(await screen.findByRole("button", { name: "ACME A2, AC" }));

  expect(screen.getByText("Scheda brand")).toBeInTheDocument();
  expect(screen.getByText("A2")).toBeInTheDocument();
  expect(screen.getByText("AC")).toBeInTheDocument();
  await waitFor(() => expect(fetchBrandRaw).toHaveBeenCalledWith("ACME", expect.any(Object)));
  expect(await screen.findByDisplayValue("Acme Incorporated")).toBeInTheDocument();
});


test("modifies and adds brand_raw occurrences in the selected brand", async () => {
  render(<Brands />);
  fireEvent.click(await screen.findByRole("button", { name: "ACME A2, AC" }));

  const cell = await screen.findByRole("textbox", { name: "Brand raw id:7" });
  fireEvent.change(cell, { target: { value: "Acme corrected" } });
  fireEvent.keyDown(cell, { key: "Enter" });
  await waitFor(() =>
    expect(updateBrandRaw).toHaveBeenCalledWith("id:7", "ACME", "Acme corrected")
  );

  const add = screen.getByRole("button", { name: "Aggiungi occorrenza" });
  await waitFor(() => expect(add).not.toBeDisabled());
  fireEvent.click(add);
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByRole("textbox", { name: "Brand raw" }), {
    target: { value: "Acme manual" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Salva occorrenza" }));
  await waitFor(() => expect(createBrandRaw).toHaveBeenCalledWith("ACME", "Acme manual"));
});
