import React, { useEffect, useState } from "react";
import { DataGrid, GridColDef } from "@mui/x-data-grid";

const PDBFullCodifica = () => {
  const [rows, setRows] = useState<any[]>([]);

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
    { field: "creation_date", headerName: "Created", width: 180 }
  ];

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/products/full`)
      .then((res) => res.json())
      .then((data) => {
        const mapped = data.map((row: any, index: number) => ({
          id: index + 1,
          ...row
        }));
        setRows(mapped);
      })
      .catch((err) => console.error(err));
  }, []);

  return (
    <div style={{ height: "85vh", width: "100%", padding: 20 }}>
      <h2>PDB - Codifica Completa</h2>
      <DataGrid rows={rows} columns={columns} pageSizeOptions={[25, 50, 100]} />
    </div>
  );
};

export default PDBFullCodifica;
