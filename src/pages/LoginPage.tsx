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