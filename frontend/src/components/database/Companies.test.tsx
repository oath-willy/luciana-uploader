import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Companies from "./Companies";
import { fetchDatabaseTable } from "./databaseApi";


jest.mock("./databaseApi", () => ({
  backendBaseUrl: "",
  fetchDatabaseTable: jest.fn(),
}));

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
          {rows.map((row: any) => (
            <button key={props.getRowId(row)} onClick={() => props.onRowClick({ row })}>
              {row.company}
            </button>
          ))}
        </section>
      );
    },
  };
});


beforeEach(() => {
  jest.resetAllMocks();
  (fetchDatabaseTable as jest.Mock).mockResolvedValue({
    rows: [{
      id_company: 7,
      company: "ACME",
      manufacturer: true,
      dealer: false,
      decription: "Dental manufacturer",
      note: "Priority account",
    }],
    total: 1,
  });
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ updated: 1 }),
  } as Response);
});


test("shows and saves the selected company detail in luciana_db_dev", async () => {
  render(<Companies />);

  fireEvent.click(await screen.findByRole("button", { name: "ACME" }));

  expect(screen.getByRole("textbox", { name: "Company" })).toHaveValue("ACME");
  expect(screen.getByRole("textbox", { name: "Description" })).toHaveValue("Dental manufacturer");
  expect(screen.getByRole("textbox", { name: "Note" })).toHaveValue("Priority account");

  fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
    target: { value: "Updated description" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Note" }), {
    target: { value: "Updated note" },
  });
  fireEvent.click(screen.getByRole("checkbox", { name: "Dealer" }));
  fireEvent.click(screen.getByRole("button", { name: "Salva modifiche" }));

  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  const [url, options] = (global.fetch as jest.Mock).mock.calls[0];
  expect(url).toBe("/api/database/companies/update");
  expect(JSON.parse(options.body)).toEqual({
    items: [{
      id_company: 7,
      company: "ACME",
      manufacturer: true,
      dealer: true,
      decription: "Updated description",
      note: "Updated note",
    }],
  });
  expect(await screen.findByText("Modifiche salvate direttamente in luciana_db_dev."))
    .toBeInTheDocument();
});
