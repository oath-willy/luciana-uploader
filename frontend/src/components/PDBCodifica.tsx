import React, { useEffect, useState } from "react";
import { DataGrid, GridColDef } from "@mui/x-data-grid";
import { Box, TextField, Typography } from "@mui/material";

interface Product {
  id: number;
  code: string;
  description: string;
  brand: string;
  category: string;
}

const PDBCodifica: React.FC = () => {
  const [rows, setRows] = useState<Product[]>([]);
  const [filterText, setFilterText] = useState("");

  const columns: GridColDef[] = [
    { field: "id", headerName: "ID", width: 90 },
    { field: "code", headerName: "Codice", width: 150 },
    { field: "description", headerName: "Descrizione", width: 300 },
    { field: "brand", headerName: "Brand", width: 180 },
    { field: "category", headerName: "Categoria", width: 180 },
  ];

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/products`)
      .then((res) => res.json())
      .then((data) => setRows(data))
      .catch((err) => console.error(err));
  }, []);

  const filteredRows = rows.filter((r) =>
    Object.values(r).some((v) =>
      String(v).toLowerCase().includes(filterText.toLowerCase())
    )
  );

  return (
    <Box sx={{ height: "85vh", width: "100%", p: 2 }}>
      <Typography variant="h5" sx={{ mb: 2 }}>
        Codifica PDB
      </Typography>

      <TextField
        label="Filtra..."
        variant="outlined"
        size="small"
        sx={{ mb: 2 }}
        fullWidth
        value={filterText}
        onChange={(e) => setFilterText(e.target.value)}
      />

      <DataGrid
        rows={filteredRows}
        columns={columns}
        pageSizeOptions={[25, 50, 100]}
        initialState={{
          pagination: { paginationModel: { pageSize: 50 } },
        }}
        checkboxSelection
      />
    </Box>
  );
};

export default PDBCodifica;
