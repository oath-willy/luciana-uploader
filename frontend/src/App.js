import React, { useState } from "react";

function App() {
  const [status, setStatus] = useState("");

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
    else setStatus(`❌ Errore ${res.status}: ${await res.text()}`)
  }

  return (
    <div onDrop={handleDrop} onDragOver={(e) => e.preventDefault()}>
      <h1>Trascina qui i file</h1>
      <p>{status}</p>
    </div>
  );
}

export default App;
