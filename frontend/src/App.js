import React, { useState } from "react";
import { MsalProvider, AuthenticatedTemplate, UnauthenticatedTemplate,
         useMsal, useMsalAuthentication } from "@azure/msal-react";
import { PublicClientApplication, InteractionType } from "@azure/msal-browser";
import { msalConfig } from "./msalConfig";

const pca = new PublicClientApplication(msalConfig);

function Uploader() {
  const { instance } = useMsal();
  useMsalAuthentication(InteractionType.Redirect);
  const [status, setStatus] = useState("");

  async function handleDrop(e) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    setStatus("Caricamento…");
    // ottieni SAS URL dalla Function
    const res = await fetch(`/api/getSasToken?filename=${encodeURIComponent(file.name)}`);
    const { uploadUrl } = await res.json();
    // carica il file
    await fetch(uploadUrl, {
      method: "PUT",
      headers: { "x-ms-blob-type": "BlockBlob" },
      body: file
    });
    setStatus("✅ Caricato con successo");
  }

  return (
    <>
      <AuthenticatedTemplate>
        <h2>Upload progetto Luciana</h2>
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          style={{
            border: "2px dashed #0078d4",
            padding: "40px",
            width: "300px",
            textAlign: "center"
          }}
        >Trascina qui un file</div>
        <p>{status}</p>
      </AuthenticatedTemplate>

      <UnauthenticatedTemplate>
        <button onClick={() => instance.loginRedirect()}>Accedi con Microsoft 365</button>
      </UnauthenticatedTemplate>
    </>
  );
}

export default function App() {
  return (
    <MsalProvider instance={pca}>
      <Uploader />
    </MsalProvider>
  );
}
