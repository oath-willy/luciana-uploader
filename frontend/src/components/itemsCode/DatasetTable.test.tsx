import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import DatasetTable from "./DatasetTable";
import { fetchDatasetMetadata, fetchDatasetRows, saveItemValues } from "./itemsCodeApi";

jest.mock("./itemsCodeApi");
jest.mock("../common/ServerDataGrid", () => {
  const React = require("react");
  return { __esModule: true, default: (props: any) => {
    const [rows, setRows] = React.useState([]);
    const [selected, setSelected] = React.useState(new Set());
    React.useEffect(() => {
      props.fetchRows({ page: 0, pageSize: 100, search: "", filters: {} }).then((result: any) => {
        setRows(result.rows); props.onRowsChange?.(result.rows);
      });
    }, [props.fetchRows, props.refreshToken, props.onRowsChange]);
    React.useEffect(() => {
      props.onSelectionChange?.(selected, rows.filter((row: any) => selected.has(row.__items_code_row_id)).map((row: any) => props.transformRow ? props.transformRow(row) : row));
    }, [selected, rows, props.transformRow, props.onSelectionChange]);
    return <div>{props.toolbarLeft}{props.toolbarRight}{rows.map((raw: any) => {
      const row = props.transformRow ? props.transformRow(raw) : raw;
      return <div key={row.item_code}>
        <input type="checkbox" aria-label={`Select ${row.item_code}`} checked={selected.has(row.__items_code_row_id)}
          onChange={() => setSelected((current: Set<number>) => {
            const next = new Set(current); next.has(row.__items_code_row_id) ? next.delete(row.__items_code_row_id) : next.add(row.__items_code_row_id); return next;
          })} />
        {props.columns.map((column: any) => <div key={column.field}>{column.renderCell?.({ value: row[column.field], row })}</div>)}
      </div>;
    })}</div>;
  }};
});

test("Reference waits for a selection and FULL PDB sends no company filter", async () => {
  render(<DatasetTable dataset="pdb" title="Reference PDB" requireCompany />);
  const company = await screen.findByRole("combobox", { name: "SELECT COMPANY" });
  await waitFor(() => expect(fetchDatasetMetadata).toHaveBeenCalled());
  expect(fetchDatasetRows).not.toHaveBeenCalled();
  fireEvent.keyDown(company, { key: "ArrowDown" });
  expect(screen.getAllByRole("option")[0]).toHaveTextContent("- FULL PDB -");
  fireEvent.click(screen.getByRole("option", { name: "- FULL PDB -" }));
  await waitFor(() => expect(fetchDatasetRows).toHaveBeenCalledWith("pdb", "", expect.any(Object)));
});

let records: any[];
beforeEach(() => {
  jest.resetAllMocks();
  records = [
    { __items_code_row_id: 0, company: "ACME", item_code: "A", company_item_code: "ACME|A", prefix_code: "P", father_name: "Family", master_code: "02_03_01", pack: "Bottle" },
    { __items_code_row_id: 1, company: "ACME", item_code: "B", company_item_code: "ACME|B", prefix_code: "Q", father_name: null, master_code: null, pack: "Box" },
  ];
  (fetchDatasetMetadata as jest.Mock).mockResolvedValue({ available: true, companies: ["ACME"], columns:
    ["company_item_code", "prefix_code", "father_name", "master_code", "pack"].map((field) => ({ field, header_name: field === "pack" ? "Pack" : field, data_type: "VARCHAR", editable: field !== "company_item_code" })) });
  (fetchDatasetRows as jest.Mock).mockImplementation(async (_dataset, company) => ({ rows: company ? records.map((row) => ({ ...row })) : [], total: company ? 2 : 0 }));
  (saveItemValues as jest.Mock).mockImplementation(async (_company, codes, values) => {
    records.forEach((row) => { if (codes.includes(row.item_code)) Object.assign(row, values); });
    return { values };
  });
});

async function openTable() {
  render(<DatasetTable dataset="new-items" title="New Items" requireCompany />);
  const company = await screen.findByRole("combobox", { name: "Company" });
  fireEvent.change(company, { target: { value: "ACME" } });
  fireEvent.keyDown(company, { key: "ArrowDown" }); fireEvent.keyDown(company, { key: "Enter" });
  await screen.findByRole("checkbox", { name: "Select A" });
}

test("Enter saves one cell; Ctrl+Enter updates visible rows or the active selection", async () => {
  await openTable();
  const cell = screen.getByRole("textbox", { name: "prefix_code ACME|A" });
  fireEvent.change(cell, { target: { value: "SAVED" } }); fireEvent.keyDown(cell, { key: "Enter" });
  await waitFor(() => expect(saveItemValues).toHaveBeenLastCalledWith("ACME", ["A"], { prefix_code: "SAVED" }));
  await waitFor(() => expect(cell).not.toHaveAttribute("readonly"));
  fireEvent.change(cell, { target: { value: "ALL" } }); fireEvent.keyDown(cell, { key: "Enter", ctrlKey: true });
  await waitFor(() => expect(saveItemValues).toHaveBeenLastCalledWith("ACME", ["A", "B"], { prefix_code: "ALL" }));
  await waitFor(() => expect(cell).not.toHaveAttribute("readonly"));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select A" }));
  fireEvent.change(cell, { target: { value: "SELECTED" } }); fireEvent.keyDown(cell, { key: "Enter", ctrlKey: true });
  await waitFor(() => expect(saveItemValues).toHaveBeenLastCalledWith("ACME", ["A"], { prefix_code: "SELECTED" }));
});

test("upper clipboard copies from Father Name and excludes unchecked paste fields", async () => {
  await openTable();
  fireEvent.click(screen.getByRole("checkbox", { name: "Select A" }));
  const copy = screen.getByRole("button", { name: "Copia caratteristiche" });
  await waitFor(() => expect(copy).not.toBeDisabled()); fireEvent.click(copy);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select A" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select B" }));
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "Campi da incollare" }));
  fireEvent.click(await screen.findByRole("option", { name: "Pack" }));
  fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
  const paste = screen.getByRole("button", { name: "Incolla caratteristiche" });
  await waitFor(() => expect(paste).not.toBeDisabled()); fireEvent.click(paste);
  await waitFor(() => expect(saveItemValues).toHaveBeenCalledWith("ACME", ["B"], { father_name: "Family", master_code: "02_03_01" }));
  expect(records[1].pack).toBe("Box"); expect(records[1].prefix_code).toBe("Q");
});

test("reference copy also saves to runtime and failed saves are reported", async () => {
  render(<DatasetTable dataset="new-items" title="New Items" requireCompany
    referenceSelection={{ row: { father_name: "Reference" }, fields: ["father_name"] }} />);
  const company = await screen.findByRole("combobox", { name: "Company" });
  fireEvent.change(company, { target: { value: "ACME" } }); fireEvent.keyDown(company, { key: "ArrowDown" }); fireEvent.keyDown(company, { key: "Enter" });
  fireEvent.click(await screen.findByRole("checkbox", { name: "Select A" }));
  const copy = screen.getByRole("button", { name: "Copia dal Reference PDB" });
  await waitFor(() => expect(copy).not.toBeDisabled()); fireEvent.click(copy);
  await waitFor(() => expect(saveItemValues).toHaveBeenCalledWith("ACME", ["A"], { father_name: "Reference" }));
  const cell = screen.getByRole("textbox", { name: "prefix_code ACME|A" });
  await waitFor(() => expect(cell).not.toHaveAttribute("readonly"));
  (saveItemValues as jest.Mock).mockRejectedValueOnce(new Error("Database non disponibile"));
  fireEvent.change(cell, { target: { value: "UNSAVED" } }); fireEvent.keyDown(cell, { key: "Enter" });
  await screen.findByText("Database non disponibile"); expect(records[0].prefix_code).toBe("P");
});
