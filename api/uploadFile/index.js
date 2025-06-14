const { BlobServiceClient } = require('@azure/storage-blob');

module.exports = async function (context, req) {
  context.log("➡️ Triggered uploadFile");

  try {
    const filename = req.query.filename || "default.txt";
    const fileContent = req.body;

    if (!fileContent) {
      context.res = {
        status: 400,
        body: "❌ Nessun contenuto del file fornito."
      };
      return;
    }

    const AZURE_STORAGE_CONNECTION_STRING = process.env.AZURE_STORAGE_CONNECTION_STRING;
    if (!AZURE_STORAGE_CONNECTION_STRING) {
      throw new Error("❌ Variabile AZURE_STORAGE_CONNECTION_STRING mancante");
    }

    const blobServiceClient = BlobServiceClient.fromConnectionString(AZURE_STORAGE_CONNECTION_STRING);
    const containerName = "uploaded-files";
    const containerClient = blobServiceClient.getContainerClient(containerName);

    if (!(await containerClient.exists())) {
      await containerClient.create();
      context.log(`🪣 Contenitore '${containerName}' creato`);
    }

    const blockBlobClient = containerClient.getBlockBlobClient(filename);
    await blockBlobClient.upload(fileContent, Buffer.byteLength(fileContent));

    context.res = {
      status: 200,
      body: `✅ File '${filename}' caricato nel container '${containerName}'`
    };
  } catch (err) {
    context.log.error("❌ ERRORE uploadFile:", err);
    context.res = {
      status: 500,
      body: `Errore interno: ${err.message || err.toString()}`
    };
  }
};
