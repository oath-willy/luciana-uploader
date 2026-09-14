import { ServerGridFetchParams, ServerGridResult } from "../common/ServerDataGrid";

export type DatasetName = "new-items" | "pdb";
export type DatasetColumn = { field: string; header_name: string; data_type: string };
export type DatasetMetadata = {
  available: boolean;
  source_file: string;
  columns: DatasetColumn[];
  companies: string[];
  message?: string | null;
};
const backendBaseUrl = process.env.REACT_APP_BACKEND_URL || "";

async function responseData(response: Response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Impossibile caricare il dataset");
  return data;
}

export async function fetchDatasetMetadata(dataset: DatasetName, company: string, signal: AbortSignal): Promise<DatasetMetadata> {
  const query = new URLSearchParams({ company });
  return responseData(await fetch(`${backendBaseUrl}/api/items-code/${dataset}/metadata?${query}`, { signal }));
}

export async function fetchDatasetRows(dataset: DatasetName, company: string, params: ServerGridFetchParams): Promise<ServerGridResult> {
  return responseData(await fetch(`${backendBaseUrl}/api/items-code/${dataset}/search`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ company, page: params.page, page_size: params.pageSize, search: params.search, filters: params.filters }),
  }));
}
