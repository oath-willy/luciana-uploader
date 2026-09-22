import { useCallback, useMemo, useState } from "react";
import { GridColDef, GridRowParams } from "@mui/x-data-grid";
import { Box, Chip, IconButton, Paper, Typography } from "@mui/material";
import ServerDataGrid from "../common/ServerDataGrid";
import { BrandRow, fetchBrandRaw, fetchBrands } from "./pdbBrandsApi";


export default function Brands() {
  const [selectedBrand, setSelectedBrand] = useState<BrandRow | null>(null);

  const brandColumns = useMemo<GridColDef[]>(
    () => [
      { field: "brand", headerName: "Brand", flex: 1, minWidth: 220 },
      { field: "prefix", headerName: "Prefissi", flex: 1, minWidth: 180 },
    ],
    []
  );

  const rawColumns = useMemo<GridColDef[]>(
    () => [
      { field: "brand_raw", headerName: "Brand raw", flex: 1, minWidth: 220 },
    ],
    []
  );

  const handleBrandClick = useCallback((params: GridRowParams) => {
    setSelectedBrand(params.row as BrandRow);
  }, []);

  const fetchSelectedBrandRaw = useCallback(
    (params: Parameters<typeof fetchBrandRaw>[1]) => {
      if (!selectedBrand) {
        return Promise.resolve({ rows: [], total: 0 });
      }
      return fetchBrandRaw(selectedBrand.brand, params);
    },
    [selectedBrand]
  );

  const prefixes = selectedBrand?.prefix
    ? selectedBrand.prefix.split(",").map((prefix) => prefix.trim()).filter(Boolean)
    : [];

  return (
    <Box
      sx={{
        height: "89vh",
        width: "100%",
        minHeight: 0,
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          lg: "minmax(460px, 3fr) minmax(360px, 2fr)",
        },
        gap: 1.5,
      }}
    >
      <ServerDataGrid
        title="Brands"
        columns={brandColumns}
        fetchRows={fetchBrands}
        getRowId={(row) => row.brand}
        filterFields={["brand", "prefix"]}
        defaultPageSize={50}
        pageSizeOptions={[25, 50, 100, 500]}
        height="100%"
        onRowClick={handleBrandClick}
        singleSelection
      />

      <Paper
        elevation={1}
        sx={{
          height: "100%",
          minHeight: 0,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          borderRadius: 1,
        }}
      >
        {selectedBrand ? (
          <>
            <Box
              sx={{
                px: 1.5,
                py: 1,
                borderBottom: "1px solid",
                borderColor: "divider",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="overline" color="text.secondary">
                    Scheda brand
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    {selectedBrand.brand}
                  </Typography>
                </Box>
                <IconButton
                  aria-label="Chiudi scheda brand"
                  size="small"
                  onClick={() => setSelectedBrand(null)}
                >
                  ×
                </IconButton>
              </Box>
              <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 0.75 }}>
                {prefixes.length > 0 ? (
                  prefixes.map((prefix) => (
                    <Chip key={prefix} label={prefix} size="small" variant="outlined" />
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    Nessun prefisso associato
                  </Typography>
                )}
              </Box>
            </Box>

            <Box sx={{ flex: 1, minHeight: 0, p: 1 }}>
              <ServerDataGrid
                title="Occorrenze brand_raw"
                columns={rawColumns}
                fetchRows={fetchSelectedBrandRaw}
                getRowId={(row) => row.id}
                filterFields={["brand_raw"]}
                defaultPageSize={50}
                pageSizeOptions={[25, 50, 100, 500]}
                height="100%"
                emptyMessage="Nessuna occorrenza brand_raw"
              />
            </Box>
          </>
        ) : (
          <Box
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              p: 3,
              textAlign: "center",
            }}
          >
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                Scheda brand
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                Seleziona un brand dalla tabella per visualizzare tutte le occorrenze
                brand_raw associate.
              </Typography>
            </Box>
          </Box>
        )}
      </Paper>
    </Box>
  );
}
