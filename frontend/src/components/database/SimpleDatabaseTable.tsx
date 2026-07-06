import { GridColDef } from "@mui/x-data-grid";
import ServerDataGrid from "../common/ServerDataGrid";
import { fetchDatabaseTable } from "./databaseApi";

type SimpleDatabaseTableProps = {
  title: string;
  tableKey: string;
  columns: GridColDef[];
  getRowIdField: string;
};

export default function SimpleDatabaseTable({
  title,
  tableKey,
  columns,
  getRowIdField,
}: SimpleDatabaseTableProps) {
  return (
    <ServerDataGrid
      title={title}
      columns={columns}
      fetchRows={(params) => fetchDatabaseTable(tableKey, params)}
      getRowId={(row) => row[getRowIdField]}
      defaultPageSize={50}
      pageSizeOptions={[25, 50, 100, 500]}
    />
  );
}
