import {
  ServerGridFetchParams,
  ServerGridResult,
} from "../common/ServerDataGrid";
import { backendBaseUrl } from "./databaseApi";

export type BrandRow = {
  brand: string;
  prefix: string;
};

export type BrandRawRow = {
  record_key: string;
  brand_raw: string;
  change_status: "original" | "modified" | "added";
};

export type BrandRawSaveResult = {
  row: BrandRawRow;
  edits_file: string;
};

async function responseData<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || "Errore caricamento Brands Dictionary");
  }
  return data as T;
}

export async function fetchBrands(
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  const data = await responseData<ServerGridResult>(
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
  return { rows: data.rows || [], total: data.total || 0 };
}

export async function fetchBrandRaw(
  brand: string,
  params: ServerGridFetchParams
): Promise<ServerGridResult> {
  const data = await responseData<ServerGridResult>(
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
  return { rows: data.rows || [], total: data.total || 0 };
}

export async function updateBrandRaw(
  recordKey: string,
  brand: string,
  brandRaw: string
): Promise<BrandRawSaveResult> {
  return responseData<BrandRawSaveResult>(
    await fetch(`${backendBaseUrl}/api/pdb/brands/raw/records`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        record_key: recordKey,
        brand,
        brand_raw: brandRaw,
      }),
    })
  );
}

export async function createBrandRaw(
  brand: string,
  brandRaw: string
): Promise<BrandRawSaveResult> {
  return responseData<BrandRawSaveResult>(
    await fetch(`${backendBaseUrl}/api/pdb/brands/raw/records`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brand, brand_raw: brandRaw }),
    })
  );
}
