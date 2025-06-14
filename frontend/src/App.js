// frontend/src/App.js
import React, { useState } from "react";
import DragAndDrop from "./DragAndDrop";
import { PublicClientApplication } from "@azure/msal-browser";
import { msalConfig } from "./msalConfig";

const msalInstance = new PublicClientApplication(msalConfig);

function App() {
  const [account, setAccount] = useState(null);
  const [status, setStatus] = useState("");
  const [file, setFile] = useState(null);

  const signIn = async () => {
    try {
      const loginResponse = await msalInstance.loginPopup();
      setAccount(loginResponse.account);
    } catch (err) {
      console.error("Login failed", err);
    }
  };

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
        headers: {
          "x-ms-blob-type": "BlockBlob",
        },
        body: file,
      });

      setStatus("✅ Caricato con successo");
    } catch (err) {
      console.error(err);
      setStatus("❌ Errore: " + err.message);
    }
  };

  if (!account) {
    return (
      <div style={{ padding: "2rem" }}>
        <button onClick={signIn}>🔐 Accedi con Microsoft</button>
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem" }}>
      <h2>Ciao, {account.username} 👋</h2>
      <DragAndDrop onFileSelected={setFile} status={status} />
      <br />
      <button onClick={handleUpload} disabled={!file}>
        🚀 Carica File
      </button>
    </div>
  );
}

export default App;
