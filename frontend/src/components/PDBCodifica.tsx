import React, { useEffect, useState, useCallback } from "react";
import { AgGridReact } from "ag-grid-react";
import { ModuleRegistry, AllCommunityModule } from "ag-grid-community";
import type { ColDef } from "ag-grid-community";

// Registrazione moduli AG Grid (obbligatorio v34+)
ModuleRegistry.registerModules([AllCommunityModule]);

import "ag-grid-community/styles/ag-grid.css";
import "ag-grid-community/styles/ag-theme-alpine.css";

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

  // CORREZIONE: tipizzazione corretta di ColDef<Product>
  const columnDefs: ColDef<Product>[] = [
    { headerName: "ID", field: "id", filter: true },
    { headerName: "Codice", field: "code", filter: true },
    { headerName: "Descrizione", field: "description", filter: true },
    { headerName: "Brand", field: "brand", filter: true },
    { headerName: "Categoria", field: "category", filter: true },
  ];

  const onGridReady = useCallback(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/products`)
      .then((response) => response.json())
      .then((data) => setRowData(data))
      .catch((error) => console.error("Errore:", error));
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
        <AgGridReact<Product>
          rowData={rowData}
          columnDefs={columnDefs}
          rowSelection="multiple"
          quickFilterText={filterText}
          onGridReady={onGridReady}
        />
      </div>
    </div>
  );
};

export default PDBCodifica;
