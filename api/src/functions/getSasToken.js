const {
  generateBlobSASQueryParameters,
  BlobSASPermissions,
  SASProtocol,
  StorageSharedKeyCredential
} = require("@azure/storage-blob");

module.exports = async function (context, req) {
  try {
    const accountName = "lucianafilestg01";
    const accountKey = "FjgCneyrqAKPvvaEVQzjx+YwTJRkrZyu/81pBdB00SCar3N5xoRVXOOJPV0kCM7Sm58zX207livS+ASt2u9p9w=="; // oppure prendi da process.env.AZURE_STORAGE_CONNECTION_STRING
    const containerName = "uploaded-files";
    const blobName = req.query.filename || "file.txt";

    const credential = new StorageSharedKeyCredential(accountName, accountKey);

    const sasToken = generateBlobSASQueryParameters({
      containerName,
      blobName,
      permissions: BlobSASPermissions.parse("cw"),
      startsOn: new Date(Date.now() - 5 * 60 * 1000),
      expiresOn: new Date(Date.now() + 60 * 60 * 1000),
      protocol: SASProtocol.Https,
    }, credential).toString();

    const url = `https://${accountName}.blob.core.windows.net/${containerName}/${blobName}?${sasToken}`;

    context.res = {
      status: 200,
      body: { sasUrl: url }
    };
  } catch (err) {
    context.log.error("❌ ERRORE:", err);
    context.res = {
      status: 500,
      body: `Errore interno: ${err.message || err}`
    };
  }
}
