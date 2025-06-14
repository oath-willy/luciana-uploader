module.exports = async function (context, req) {
  context.log("➡️ Triggered uploadFile");

  try {
    const filename = req.query.filename || "default.txt";
    context.log("📄 Requested filename:", filename);
    context.log("📦 Body size:", req.body?.length);

    // qui metti il codice di upload
    // es. const shareServiceClient = ...

    context.res = {
      status: 200,
      body: `✅ File '${filename}' caricato con successo!`
    };
  } catch (err) {
    context.log.error("❌ ERRORE nella function uploadFile:", err);
    context.res = {
      status: 500,
      body: `Errore interno: ${err.message || err.toString()}`
    };
  }
}
