const {
  ShareServiceClient,
  StorageSharedKeyCredential
} = require("@azure/storage-file-share");

const account   = "lucianafilestg01";
const shareName = "luciana-share";
const key       = process.env.STORAGE_KEY;

module.exports = async function (context, req) {
  const filename = (req.query.filename || "").replace(/[^A-Za-z0-9_.-]/g, "");
  if (!filename) {
    context.res = { status: 400, body: "Filename missing" };
    return;
  }

  const fileBuffer = req.body;
  if (!fileBuffer || !fileBuffer.length) {
    context.res = { status: 400, body: "File is empty" };
    return;
  }

  const cred   = new StorageSharedKeyCredential(account, key);
  const svc    = new ShareServiceClient(
       `https://${account}.file.core.windows.net`, cred);
  const fileClient = svc
        .getShareClient(shareName)
        .rootDirectoryClient
        .getFileClient(filename);

  await fileClient.create(fileBuffer.length);
  await fileClient.uploadRange(fileBuffer, 0, fileBuffer.length);

  context.res = { status: 200, body: "OK" };
};
