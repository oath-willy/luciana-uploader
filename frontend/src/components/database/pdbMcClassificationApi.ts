import {
  ServerGridFetchParams,
  ServerGridResult,
} from "../common/ServerDataGrid";
import { backendBaseUrl } from "./databaseApi";


export type ClassificationColumn = {
  field: string;
  header_name: string;
  data_type: string;
  editable: boolean;
};

export type ClassificationMetadata = {
  available: boolean;
  source_file: string;
  runtime_file: string;
  primary_key?: string;
  columns: ClassificationColumn[];
  families: string[];
  subfamilies: string[];
  subfamilies_by_family: Record<string, string[]>;
  message?: string | null;
};

const endpoint = `${backendBaseUrl}/api/pdb/mc-classification`;

async function responseData<T>(response: Response, fallback: string): Promise<T> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || fallback);
  }
  return data as T;
}

export async function fetchClassificationMetadata(
  signal?: AbortSignal
): Promise<ClassificationMetadata> {
  return responseData(
    await fetch(`${endpoint}/metadata`, { signal }),
    "Impossibile caricare i metadati MC Classification"
  );
}

export async function fetchClassificationRows(
  params: ServerGridFetchParams,
  family: string,
  subfamily: string
): Promise<ServerGridResult> {
  return responseData(
    await fetch(`${endpoint}/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: params.signal,
      body: JSON.stringify({
        page: params.page,
        page_size: params.pageSize,
        search: params.search,
        filters: params.filters,
        family,
        subfamily,
      }),
    }),
    "Impossibile caricare MC Classification"
  );
}

export async function updateClassificationRecord(
  recordKey: string,
  values: Record<string, unknown>
): Promise<{ row: Record<string, unknown>; runtime_file: string }> {
  return responseData(
    await fetch(`${endpoint}/records`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record_key: recordKey, values }),
    }),
    "Impossibile salvare la modifica"
  );
}

export async function createClassificationRecord(
  values: Record<string, unknown>
): Promise<{ row: Record<string, unknown>; runtime_file: string }> {
  return responseData(
    await fetch(`${endpoint}/records`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    }),
    "Impossibile aggiungere la riga"
  );
}
