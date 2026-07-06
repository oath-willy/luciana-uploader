import SimpleDatabaseTable from "./SimpleDatabaseTable";

export default function Countries() {
  return (
    <SimpleDatabaseTable
      title="Countries"
      tableKey="countries"
      getRowIdField="id_country"
      columns={[
        { field: "id_country", headerName: "ID", width: 100 },
        { field: "country_name", headerName: "Country Name", width: 260 },
      ]}
    />
  );
}
