import React, { useState, useCallback } from "react";
import { AgGridReact } from "ag-grid-react";

import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";
import type { ColDef } from "ag-grid-community";

// CSS legacy (compatibili con v32)
import "ag-grid-community/dist/styles/ag-grid.css";
import "ag-grid-community/dist/styles/ag-theme-alpine.css";

// Registrazione moduli
ModuleRegistry.registerModules([AllCommunityModule]);

interface Product {
  id: number;
  code: string;
  description: string;
  brand: string;
  category: string;
}

const PDBCodifica: React.FC = () => {
  const [rowData, setRowData] = useState<Product[]>([]);
  const [filterText, setFilterText] = useState("");

  const columnDefs: ColDef<Product>[] = [
    { headerName: "ID", field: "id", filter: true },
    { headerName: "Codice", field: "code", filter: true },
    { headerName: "Descrizione", field: "description", filter: true },
    { headerName: "Brand", field: "brand", filter: true },
    { headerName: "Categoria", field: "category", filter: true },
  ];

  const onGridReady = useCallback(() => {
    const url = `${process.env.REACT_APP_BACKEND_URL}/api/products`;
    console.log("Fetching:", url);

    fetch(url)
      .then((res) => res.json())
      .then((data) => {
        console.log("Dati ricevuti:", data);
        setRowData(data);
      })
      .catch((err) => console.error("Errore fetch:", err));
  }, []);

  return (
    <div className="p-4 w-full h-[85vh] overflow-hidden">
      <h1 className="text-xl font-semibold mb-4">Codifica PDB</h1>

      <input
        type="text"
        placeholder="Filtra..."
        className="border rounded px-3 py-1 mb-3"
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
      />

      <div className="ag-theme-alpine" style={{ height: "100%", width: "100%" }}>
        <AgGridReact
          rowData={rowData}
          columnDefs={columnDefs}
          quickFilterText={filterText}
          rowSelection="multiple"
          onGridReady={onGridReady}
          animateRows={true}
        />
      </div>
    </div>
  );
};

export default PDBCodifica;
