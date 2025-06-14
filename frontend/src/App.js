import React from "react";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { PublicClientApplication } from "@azure/msal-browser";
import DragAndDrop from "./DragAndDrop";

const msalConfig = {
  auth: {
    clientId: "95622910-72b1-4eeb-98ea-fa20efbc5673",
    authority: "https://login.microsoftonline.com/3630ff06-11ea-4763-960a-fc74e8780220",
    redirectUri: "https://mango-ocean-06166b203.6.azurestaticapps.net",
  },
  cache: {
    cacheLocation: "localStorage",
    storeAuthStateInCookie: false,
  },
};

const msalInstance = new PublicClientApplication(msalConfig);

const AppContent = () => {
  const { instance, accounts } = useMsal();

  const handleLogin = async () => {
    try {
      await instance.loginRedirect();
    } catch (error) {
      console.error("Login error:", error);
    }
  };

  if (accounts.length === 0) {
    return (
      <div style={{ padding: "2rem", textAlign: "center" }}>
        <h2>🔐 Accesso richiesto</h2>
        <button onClick={handleLogin}>Accedi con Microsoft</button>
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem" }}>
      <p>✅ Benvenuto, {accounts[0].username}</p>
      <DragAndDrop />
    </div>
  );
};

function App() {
  return (
    <MsalProvider instance={msalInstance}>
      <AppContent />
    </MsalProvider>
  );
}

export default App;
