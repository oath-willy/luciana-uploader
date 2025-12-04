import { useState, useMemo } from "react";
import { AgGridReact } from "ag-grid-react";

import type { ColDef, GridReadyEvent } from "ag-grid-community";

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

export default function PDBCodifica() {
  const [rowData, setRowData] = useState<any[]>([]);
  const [filterText, setFilterText] = useState("");

  // Tipizzazione corretta delle colonne
  const columnDefs: ColDef[] = useMemo(
    () => [
      {
        headerName: "Select",
        checkboxSelection: true,
        headerCheckboxSelection: true,
        width: 60,
      },
      { field: "item_code", headerName: "Item Code", filter: true },
      { field: "brand", headerName: "Brand", filter: true },
      { field: "prefix", headerName: "Prefix", filter: true },
      { field: "father_name", headerName: "Father Name", filter: true },
      { field: "created_at", headerName: "Created At", filter: true },
    ],
    []
  );

  const onFilterChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilterText(e.target.value);
  };

  const onGridReady = async (params: GridReadyEvent) => {
    const res = await fetch("https://luciana-backend.azurewebsites.net/api/products");
    const data = await res.json();
    setRowData(data);
  };

  return (
    <div className="p-4 w-full h-full">
      <h1 className="text-xl font-semibold mb-4">Codifica PDB</h1>

      <div className="mb-3 flex gap-3 items-center">
        <input
          type="text"
          placeholder="Filtra..."
          className="border rounded px-3 py-1"
          value={filterText}
          onChange={onFilterChange}
        />
      </div>

      <div
        className="ag-theme-alpine"
        style={{ height: "70vh", width: "100%" }}
      >
        <AgGridReact
          rowData={rowData}
          columnDefs={columnDefs}
          rowSelection="multiple"
          quickFilterText={filterText}
          onGridReady={onGridReady}
        />
      </div>
    </div>
  );
}
