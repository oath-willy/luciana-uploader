import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import reportWebVitals from "./reportWebVitals";
import { PublicClientApplication } from "@azure/msal-browser";
import { MsalProvider } from "@azure/msal-react";
import { msalConfig } from "./auth/msalConfig";
import "./index.css";

// Inizializza MSAL
const msalInstance = new PublicClientApplication(msalConfig);

// Gestisce il redirect dopo il login Microsoft
msalInstance.handleRedirectPromise().then(() => {
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
});

reportWebVitals();