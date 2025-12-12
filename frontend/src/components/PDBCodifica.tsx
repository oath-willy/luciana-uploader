import React, { useEffect, useState } from "react";
import {
  DataGrid,
  GridColDef,
  GridFilterModel,
  GridPagination,
  GridRowSelectionModel,
} from "@mui/x-data-grid";
import { TextField, Box } from "@mui/material";

const PDBFullCodifica = () => {
  const [rows, setRows] = useState<any[]>([]);
  const [filterModel, setFilterModel] = useState<GridFilterModel>({
    items: [],
  });
  const [search, setSearch] = useState("");

  // ✅ CORRETTO per MUI X v7+
  const [rowSelectionModel, setRowSelectionModel] =
    useState<GridRowSelectionModel>({
      type: "include",
      ids: new Set(),
    });

  const columns: GridColDef[] = [
    { field: "company_item_code", headerName: "Item Code", width: 180 },
    { field: "item_description", headerName: "Description", width: 260 },
    { field: "prefix_encoding", headerName: "Encoding", width: 140 },
    { field: "prefix_code", headerName: "Prefix Code", width: 140 },
    { field: "father_name", headerName: "Father Name", width: 160 },
    { field: "dm_code", headerName: "DM", width: 120 },
    { field: "ft_code", headerName: "FT", width: 120 },
    { field: "packaging", headerName: "Packaging", width: 130 },
    { field: "packaging_unit", headerName: "Unit", width: 120 },
    { field: "feature", headerName: "Feature", width: 150 },
    { field: "measure", headerName: "Measure", width: 120 },
    { field: "extra", headerName: "Extra", width: 120 },
    { field: "packaging_quantity", headerName: "Qty", width: 100 },
    { field: "user_nome", headerName: "User Name", width: 140 },
    { field: "user_cognome", headerName: "User Last Name", width: 140 },
    { field: "creation_date", headerName: "Created", width: 180 },
  ];

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/products`)
      .then((res) => res.json())
      .then((data) => {
        const mapped = data.map((row: any, index: number) => ({
          id: index + 1,
          ...row,
        }));
        setRows(mapped);
      })
      .catch((err) => console.error(err));
  }, []);

  const handleSearchChange = (value: string) => {
    setSearch(value);
    setFilterModel({
      items: value
        ? [
            {
              field: "item_description",
              operator: "contains",
              value,
            },
          ]
        : [],
    });
  };

  // ✅ CONTEGGIO CORRETTO
  const selectedCount =
  rowSelectionModel.type === "include"
    ? rowSelectionModel.ids.size
    : rows.length - rowSelectionModel.ids.size;

  return (
    <div style={{ height: "95vh", width: "100%", padding: 0 }}>
      <h2 style={{ margin: 0, padding: 0 }}>PDB - Codifica Completa</h2>

      <DataGrid
        rows={rows}
        columns={columns}
        rowHeight={22}
        pageSizeOptions={[25, 50, 100]}
        filterModel={filterModel}
        onFilterModelChange={setFilterModel}
        checkboxSelection
        disableRowSelectionOnClick
        rowSelectionModel={rowSelectionModel}
        onRowSelectionModelChange={(newSelection) =>
          setRowSelectionModel(newSelection)
        }
        slots={{
          footer: () => (
            <CustomFooter
              search={search}
              onSearchChange={handleSearchChange}
              selectedCount={selectedCount}
            />
          ),
        }}
      />
    </div>
  );
};

function CustomFooter({
  search,
  onSearchChange,
  selectedCount,
}: {
  search: string;
  onSearchChange: (v: string) => void;
  selectedCount: number;
}) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        px: 1,
        py: 0.5,
        borderTop: "1px solid #e0e0e0",
      }}
    >
      <TextField
        size="small"
        placeholder="Find…"
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        sx={{ width: 260 }}
      />

      <Box sx={{ fontSize: 13, color: "text.secondary", paddingLeft: 2 }}>
        {selectedCount > 0
          ? `${selectedCount} righe selezionate`
          : "Nessuna riga selezionata"}
      </Box>

      <GridPagination />
    </Box>
  );
}

export default PDBFullCodifica;
