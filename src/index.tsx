import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import reportWebVitals from "./reportWebVitals";
import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { msalConfig } from "./auth/msalConfig";
import "./index.css";

const msalInstance = new PublicClientApplication(msalConfig);

async function main() {
  await msalInstance.initialize();

  // 🔁 Protezione immediata: se nell'URL c'è il codice OAuth, forziamo redirect a /upload
  if (window.location.hash.includes("code=")) {
    console.log("🔁 Intercetto codice OAuth nell'hash, forzo redirect provvisorio...");
    // 👇 Questo redirect riavvia l'app per poi gestire il redirect nel prossimo render
    window.location.replace("/upload");
    return;
  }

  // ✅ MSAL intercetta il codice e lo converte in token
  const response = await msalInstance.handleRedirectPromise();

  if (response) {
    console.log("✅ MSAL ha gestito il redirect");
    msalInstance.setActiveAccount(response.account);
    window.location.replace("/upload");
    return;
  }

  // ✅ Nessun redirect da gestire, si procede con l'app
  const root = ReactDOM.createRoot(
    document.getElementById("root") as HTMLElement
  );

  root.render(
    <React.StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </React.StrictMode>
  );
}

main();
reportWebVitals();