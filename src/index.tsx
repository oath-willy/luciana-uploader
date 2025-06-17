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

  const response = await msalInstance.handleRedirectPromise();

  if (response) {
    console.log("✅ MSAL ha gestito il redirect");
    msalInstance.setActiveAccount(response.account);
    // ✅ Naviga esplicitamente a /upload
    window.location.replace("/upload");
    return; // blocca il render finché non sei su /upload
  } else {
    console.log("ℹ️ Nessun redirect da gestire");
  }

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
