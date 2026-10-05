import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import McClassification from "./McClassification";
import {
  createClassificationRecord,
  fetchClassificationMetadata,
  fetchClassificationRows,
  updateClassificationRecord,
} from "./pdbMcClassificationApi";


jest.mock("./pdbMcClassificationApi");
jest.mock("../common/ServerDataGrid", () => {
  const React = require("react");
  return {
    __esModule: true,
    default: (props: any) => {
      const [rows, setRows] = React.useState([]);
      React.useEffect(() => {
        props.fetchRows({ page: 0, pageSize: 100, search: "", filters: {} })
          .then((result: any) => setRows(result.rows));
      }, [props.fetchRows, props.refreshToken]);
      return (
        <section>
          <h2>{props.title}</h2>
          <div>{props.toolbarLeft}</div>
          <div>{props.toolbarRight}</div>
          {rows.map((row: any) => (
            <div key={props.getRowId(row)}>
              {props.columns.map((column: any) => (
                <React.Fragment key={column.field}>
                  {column.renderCell
                    ? column.renderCell({ row, value: row[column.field] })
                    : <span>{String(row[column.field] || "")}</span>}
                </React.Fragment>
              ))}
            </div>
          ))}
        </section>
      );
    },
  };
});


const metadata = {
  available: true,
  source_file: "pdb_mc_classification.parquet",
  runtime_file: "runtime_pdb_mc_classification.sqlite3",
  primary_key: "master_code",
  columns: [
    { field: "master_code", header_name: "Master Code", data_type: "VARCHAR", editable: false },
    { field: "mc_desc", header_name: "Mc Desc", data_type: "VARCHAR", editable: true },
    { field: "family", header_name: "Family", data_type: "VARCHAR", editable: true },
    { field: "subfamily", header_name: "Subfamily", data_type: "VARCHAR", editable: true },
    { field: "product_group", header_name: "Product Group", data_type: "VARCHAR", editable: true },
  ],
  families: ["FAMILY A"],
  subfamilies: ["SUB A"],
  subfamilies_by_family: { "FAMILY A": ["SUB A"] },
};


beforeEach(() => {
  jest.resetAllMocks();
  (fetchClassificationMetadata as jest.Mock).mockResolvedValue(metadata);
  (fetchClassificationRows as jest.Mock).mockResolvedValue({
    rows: [{
      __mc_classification_row_id: "01_01_01",
      __change_status: "original",
      master_code: "01_01_01",
      mc_desc: "Original",
      family: "FAMILY A",
      subfamily: "SUB A",
      product_group: "GROUP A",
    }],
    total: 1,
  });
  (updateClassificationRecord as jest.Mock).mockResolvedValue({
    row: {}, runtime_file: "runtime_pdb_mc_classification.sqlite3",
  });
  (createClassificationRecord as jest.Mock).mockResolvedValue({
    row: {}, runtime_file: "runtime_pdb_mc_classification.sqlite3",
  });
});


test("shows family filters and saves cell edits in the overlay", async () => {
  render(<McClassification />);

  expect(await screen.findByRole("combobox", { name: "Famiglia" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Sottofamiglia" })).toBeInTheDocument();
  const description = await screen.findByRole("textbox", { name: "Mc Desc 01_01_01" });
  fireEvent.change(description, { target: { value: "Edited" } });
  fireEvent.keyDown(description, { key: "Enter" });

  await waitFor(() => expect(updateClassificationRecord).toHaveBeenCalledWith(
    "01_01_01",
    { mc_desc: "Edited" }
  ));
  expect(await screen.findByText(/Modifica salvata in runtime_pdb_mc_classification.sqlite3/)).toBeInTheDocument();
});


test("adds a new row from the table toolbar", async () => {
  render(<McClassification />);
  const addButton = await screen.findByRole("button", { name: /Aggiungi riga/i });
  await waitFor(() => expect(addButton).toBeEnabled());
  fireEvent.click(addButton);

  fireEvent.change(screen.getByRole("textbox", { name: /Master Code/i }), {
    target: { value: "03_03_03" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Family" }), {
    target: { value: "FAMILY C" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Subfamily" }), {
    target: { value: "SUB C" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Salva riga" }));

  await waitFor(() => expect(createClassificationRecord).toHaveBeenCalledWith(
    expect.objectContaining({
      master_code: "03_03_03",
      family: "FAMILY C",
      subfamily: "SUB C",
    })
  ));
  expect(await screen.findByText(/Nuova riga salvata in runtime_pdb_mc_classification.sqlite3/)).toBeInTheDocument();
});
