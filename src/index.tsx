import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import reportWebVitals from "./reportWebVitals";
import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { msalConfig } from "./auth/msalConfig";
import "./index.css";

const msalInstance = new PublicClientApplication(msalConfig);

// Avvia l'app solo dopo aver inizializzato MSAL e gestito il redirect
async function main() {
  await msalInstance.initialize(); // ✅ inizializza correttamente
  await msalInstance.handleRedirectPromise(); // ✅ gestisce eventuale login

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