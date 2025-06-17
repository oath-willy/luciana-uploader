import {
  BlobServiceClient,
  StorageSharedKeyCredential,
  AnonymousCredential,
  newPipeline,
} from "@azure/storage-blob";
import { TokenCredential } from "@azure/core-auth";

const accountName = "luciana-bronze-stg01";
const containerName = "bronze";

export async function uploadBlobToContainer(file: File, accessToken: string) {
  const credential: TokenCredential = {
    getToken: async () => ({
      token: accessToken,
      expiresOnTimestamp: Date.now() + 3600000,
    }),
  };

  const blobServiceClient = new BlobServiceClient(
    `https://${accountName}.blob.core.windows.net`,
    credential
  );

  const containerClient = blobServiceClient.getContainerClient(containerName);
  const blockBlobClient = containerClient.getBlockBlobClient(file.name);

  await blockBlobClient.uploadBrowserData(file);
}