import { FileUpload } from "../components/FileUpload";
import { Container, Title } from "@mantine/core";

export const UploadPage = () => {
  return (
    <Container size="sm" style={{ marginTop: 50 }}>
      <Title order={3} mb="lg">
        Carica file bronze
      </Title>
      <FileUpload />
    </Container>
  );
};