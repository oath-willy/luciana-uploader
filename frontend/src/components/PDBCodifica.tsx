import React, { useEffect, useState } from "react";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { TextField } from "@mui/material";

// Tipo generico per un prodotto
interface Product {
  [key: string]: any;
}

export default function PDBCodifica() {
  const [rows, setRows] = useState<Product[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    fetch("https://luciana-backend.azurewebsites.net/api/products")
      .then((res) => res.json())
      .then((data: Product[]) => {
        const rowsWithId = data.map((item: Product, index: number) => ({
          id: index + 1,  // DataGrid richiede un ID univoco
          ...item,
        }));
        setRows(rowsWithId);
      })
      .catch((error) => console.error("Errore fetch prodotti:", error));
  }, []);

  const filteredRows = rows.filter((row) =>
    Object.values(row).some((val) =>
      val?.toString().toLowerCase().includes(filter.toLowerCase())
    )
  );

  const columns: GridColDef[] = [
    { field: "COMPANY_ITEMCODE", headerName: "Codice", flex: 1 },
    { field: "Item_Description_Cleaned", headerName: "Descrizione", flex: 2 },
    { field: "Sellout_Brand", headerName: "Brand", flex: 1 },
    { field: "Father_Name", headerName: "Categoria", flex: 1 },
    { field: "Avg_Price", headerName: "Prezzo Medio", flex: 1, type: "number" },
  ];

  return (
    <div style={{ height: "80vh", width: "100%" }}>
      <TextField
        fullWidth
        label="Filtra..."
        variant="outlined"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        style={{ marginBottom: 16 }}
      />

      <DataGrid
        rows={filteredRows}
        columns={columns}
        pageSizeOptions={[20, 50, 100]}
      />
    </div>
  );
}
