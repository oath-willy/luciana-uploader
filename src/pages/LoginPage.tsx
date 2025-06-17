import { useMsal } from "@azure/msal-react";
import { Button, Container, Title } from "@mantine/core";
import { loginRequest } from "../auth/msalConfig";

export const LoginPage = () => {
  const { instance } = useMsal();

  const handleLogin = () => {
    instance.loginRedirect(loginRequest);
  };

  console.log("LoginPage rendering");

  return (
    <Container size="sm" style={{ marginTop: 100 }}>
      <Title order={2} style={{ textAlign: "center" }} mb="lg">
        Benvenuto nel progetto Luciana
      </Title>
      <Button fullWidth size="md" onClick={handleLogin}>
        Accedi con account aziendale
      </Button>
    </Container>
  );
};