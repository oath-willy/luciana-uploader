import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Brands from "./Brands";
import { fetchBrandRaw, fetchBrands } from "./pdbBrandsApi";


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
      }, [props.fetchRows]);
      return (
        <section>
          <h2>{props.title}</h2>
          {rows.map((row: any) => (
            <button
              key={props.getRowId(row)}
              onClick={() => props.onRowClick?.({ row })}
            >
              {props.columns.map((column: any) => row[column.field]).join(" ")}
            </button>
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
    rows: [{ id: 7, brand_raw: "Acme Incorporated" }],
    total: 1,
  });
});


test("opens the selected brand card and loads its brand_raw occurrences", async () => {
  render(<Brands />);

  fireEvent.click(await screen.findByRole("button", { name: "ACME A2, AC" }));

  expect(screen.getByText("Scheda brand")).toBeInTheDocument();
  expect(screen.getByText("A2")).toBeInTheDocument();
  expect(screen.getByText("AC")).toBeInTheDocument();
  await waitFor(() => expect(fetchBrandRaw).toHaveBeenCalledWith("ACME", expect.any(Object)));
  expect(await screen.findByRole("button", { name: "Acme Incorporated" })).toBeInTheDocument();
});
