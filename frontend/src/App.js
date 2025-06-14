// frontend/src/App.js
import React, { useState } from "react";
import DragAndDrop from "./DragAndDrop";
import { useMsal } from "@azure/msal-react";

function App() {
  const { accounts } = useMsal();
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");

  const handleUpload = async () => {
    if (!file) {
      setStatus("❌ Nessun file selezionato.");
      return;
    }

    try {
      setStatus("⏳ Caricamento...");
      const res = await fetch(`/api/getSasToken?filename=${file.name}`);
      const { sasUrl } = await res.json();

      await fetch(sasUrl, {
        method: "PUT",
        headers: { "x-ms-blob-type": "BlockBlob" },
        body: file,
      });

      setStatus("✅ Caricato con successo");
    } catch (err) {
      console.error(err);
      setStatus("❌ Errore: " + err.message);
    }
  };

  const username = accounts[0]?.username;

  return (
    <div style={{ padding: "2rem" }}>
      <h2>Ciao, {username || "utente"} 👋</h2>
      <DragAndDrop onFileSelected={setFile} status={status} />
      <br />
      <button onClick={handleUpload} disabled={!file}>
        🚀 Carica File
      </button>
    </div>
  );
}

export default App;