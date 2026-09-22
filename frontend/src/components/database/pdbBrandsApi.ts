import {
  ServerGridFetchParams,
  ServerGridResult,
} from "../common/ServerDataGrid";
import { backendBaseUrl } from "./databaseApi";

export type BrandRow = {
  brand: string;
  prefix: string;
};

async function responseData(response: Response): Promise<ServerGridResult> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || "Errore caricamento Brands Dictionary");
  }
  return {
    rows: data.rows || [],
    total: data.total || 0,
  };
}

export async function fetchBrands(
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  return responseData(
    await fetch(`${backendBaseUrl}/api/pdb/brands/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: params.signal,
      body: JSON.stringify({
        page: params.page,
        page_size: params.pageSize,
        search: params.search,
        filters: params.filters,
      }),
    })
  );
}

export async function fetchBrandRaw(
  brand: string,
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  return responseData(
    await fetch(`${backendBaseUrl}/api/pdb/brands/raw/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: params.signal,
      body: JSON.stringify({
        brand,
        page: params.page,
        page_size: params.pageSize,
        search: params.search,
        filters: params.filters,
      }),
    })
  );
}
