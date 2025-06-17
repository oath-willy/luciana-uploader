import { Configuration } from "@azure/msal-browser";

export const msalConfig: Configuration = {
  auth: {
    clientId: "<INSERISCI_CLIENT_ID>",
    authority: "https://login.microsoftonline.com/<INSERISCI_TENANT_ID>",
    redirectUri: "http://localhost:3000",
  },
  cache: {
    cacheLocation: "localStorage",
    storeAuthStateInCookie: false,
  },
};

export const loginRequest = {
  scopes: ["https://storage.azure.com/user_impersonation"],
};

// src/pages/LoginPage.tsx
import { useMsal } from "@azure/msal-react";
import { Button, Container, Title } from "@mantine/core";
import { loginRequest } from "../auth/msalConfig";

export const LoginPage = () => {
  const { instance } = useMsal();

  const handleLogin = () => {
    instance.loginRedirect(loginRequest);
  };

  return (
    <Container size="sm" style={{ marginTop: 100 }}>
      <Title align="center" order={2} mb="lg">
        Benvenuto nel progetto Luciana
      </Title>
      <Button fullWidth size="md" onClick={handleLogin}>
        Accedi con account aziendale
      </Button>
    </Container>
  );
};
