import { useCallback, useMemo, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import { Box, IconButton, Paper, Typography } from "@mui/material";
import ServerDataGrid from "../common/ServerDataGrid";
import { fetchDatabaseTable, fetchFatherNameProducts } from "./databaseApi";

type FatherNameRow = {
  id_father_name: number;
  father_name: string;
  product_count: number;
};

export default function FatherNames() {
  const [selectedFatherName, setSelectedFatherName] = useState<FatherNameRow | null>(null);

  const fatherColumns = useMemo<GridColDef[]>(
    () => [
      { field: "id_father_name", headerName: "ID", width: 110 },
      { field: "father_name", headerName: "Father Name", width: 280 },
      { field: "product_count", headerName: "Products", width: 120 },
    ],
    []
  );

  const productColumns = useMemo<GridColDef[]>(
    () => [
      { field: "id_product", headerName: "Product ID", width: 110 },
      { field: "company_item_code", headerName: "Item Code", width: 180 },
      { field: "item_description", headerName: "Description", width: 320 },
      { field: "id_company_dealer", headerName: "Dealer ID", width: 110 },
      { field: "id_prefix_encoding", headerName: "Encoding ID", width: 120 },
      { field: "id_prefix_code", headerName: "Prefix Code ID", width: 135 },
      { field: "id_packaging", headerName: "Packaging ID", width: 130 },
      { field: "id_feature", headerName: "Feature ID", width: 110 },
      { field: "id_measure", headerName: "Measure ID", width: 115 },
      { field: "id_user", headerName: "User ID", width: 90 },
      { field: "creation_date", headerName: "Created", width: 170 },
    ],
    []
  );

  const handleFatherClick = useCallback((params: GridRowParams) => {
    setSelectedFatherName(params.row as FatherNameRow);
  }, []);

  return (
    <Box sx={{ height: "89vh", width: "100%", display: "flex", flexDirection: "column" }}>
      <ServerDataGrid
        title="Father Names"
        columns={fatherColumns}
        fetchRows={(params) => fetchDatabaseTable("father-names", params)}
        getRowId={(row) => row.id_father_name}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        height={selectedFatherName ? "43vh" : "89vh"}
        onRowClick={handleFatherClick}
      />

      {selectedFatherName && (
        <Paper
          elevation={1}
          sx={{
            mt: 1,
            height: "44vh",
            minHeight: 260,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            borderRadius: 1,
          }}
        >
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              px: 1.5,
              py: 1,
              borderBottom: "1px solid #e0e0e0",
            }}
          >
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Products linked to father name
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {selectedFatherName.father_name}
              </Typography>
            </Box>
            <IconButton
              aria-label="Chiudi elenco products"
              size="small"
              onClick={() => setSelectedFatherName(null)}
            >
              X
            </IconButton>
          </Box>

          <Box sx={{ flex: 1, overflow: "hidden" }}>
            <ServerDataGrid
              title="Products"
              columns={productColumns}
              fetchRows={(params) =>
                fetchFatherNameProducts(selectedFatherName.id_father_name, params)
              }
              getRowId={(row) => row.id_product}
              defaultPageSize={50}
              pageSizeOptions={[25, 50, 100, 500]}
              height="100%"
              rowHeight={32}
            />
          </Box>
        </Paper>
      )}
    </Box>
  );
}
