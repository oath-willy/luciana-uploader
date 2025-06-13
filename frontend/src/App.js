async function handleDrop(e) {
  e.preventDefault();
  const file = e.dataTransfer.files[0];
  setStatus("Caricamento…");

  const res = await fetch(`/api/uploadFile?filename=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });

  if (res.ok) setStatus("✅ Caricato con successo");
  else        setStatus("❌ Errore: " + (await res.text()));
}
