const {
  BlobServiceClient,
  generateBlobSASQueryParameters,
  BlobSASPermissions,
  SASProtocol,
  StorageSharedKeyCredential
} = require("@azure/storage-blob");

module.exports = async function (context, req) {
  const accountName = "lucianafilestg01";
  const accountKey = "FjgCneyrqAKPvvaEVQzjx+YwTJRkrZyu/81pBdB00SCar3N5xoRVXOOJPV0kCM7Sm58zX207livS+ASt2u9p9w==";
  const containerName = "uploaded-files";

  const credential = new StorageSharedKeyCredential(accountName, accountKey);
  const blobName = req.query.filename || "file.txt";

  const sasToken = generateBlobSASQueryParameters({
    containerName,
    blobName,
    permissions: BlobSASPermissions.parse("cw"),
    startsOn: new Date(),
    expiresOn: new Date(new Date().valueOf() + 3600 * 1000),
    protocol: SASProtocol.Https,
  }, credential).toString();

  const url = `https://${accountName}.blob.core.windows.net/${containerName}/${blobName}?${sasToken}`;

  context.res = {
    status: 200,
    body: { sasUrl: url }
  };
}
