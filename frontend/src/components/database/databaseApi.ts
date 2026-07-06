import { ServerGridFetchParams, ServerGridResult } from "../common/ServerDataGrid";

export const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

export async function fetchDatabaseTable(
  tableKey: string,
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  const response = await fetch(`${backendBaseUrl}/api/database/${tableKey}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page: params.page,
      page_size: params.pageSize,
      search: params.search,
      filters: params.filters,
    }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Errore caricamento tabella");
  }

  const data = await response.json();
  return {
    rows: data.rows || [],
    total: data.total || 0,
  };
}

export async function fetchFatherNameProducts(
  idFatherName: number,
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  const response = await fetch(
    `${backendBaseUrl}/api/database/father-names/${idFatherName}/products/search`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page: params.page,
        page_size: params.pageSize,
        search: params.search,
        filters: params.filters,
      }),
    }
  );

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail || "Errore caricamento prodotti");
  }

  const data = await response.json();
  return {
    rows: data.rows || [],
    total: data.total || 0,
  };
}
