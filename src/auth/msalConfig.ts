import { Configuration } from "@azure/msal-browser";

export const msalConfig: Configuration = {
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
