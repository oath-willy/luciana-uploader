import SimpleDatabaseTable from "./SimpleDatabaseTable";

export default function Currencies() {
  return (
    <SimpleDatabaseTable
      title="Currencies"
      tableKey="currencies"
      getRowIdField="id_currency"
      columns={[
        { field: "id_currency", headerName: "ID", width: 100 },
        { field: "currency_code", headerName: "Currency Code", width: 160 },
        { field: "currency_name", headerName: "Currency Name", width: 240 },
        { field: "uic_code", headerName: "UIC Code", width: 150 },
      ]}
    />
  );
}
