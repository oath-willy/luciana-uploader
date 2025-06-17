import { useState } from "react";
import { Button, Group, FileInput, Text } from "@mantine/core";
import { useMsal } from "@azure/msal-react";
import { uploadBlobToContainer } from "../services/blobStorage";

export const FileUpload = () => {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<string>("");
  const { instance, accounts } = useMsal();

  const handleUpload = async () => {
    if (!file) return;
    setStatus("Upload in corso...");
    try {
      const account = accounts[0];
      const response = await instance.acquireTokenSilent({
        scopes: ["https://storage.azure.com/user_impersonation"],
        account,
      });
      await uploadBlobToContainer(file, response.accessToken);
      setStatus("File caricato con successo.");
    } catch (err) {
      setStatus("Errore durante l'upload.");
    }
  };

  return (
    <>
      <FileInput
        placeholder="Seleziona file"
        value={file}
        onChange={setFile}
        label="File da caricare"
        withAsterisk
      />
      <Group mt="md">
        <Button onClick={handleUpload} disabled={!file}>Carica</Button>
      </Group>
      {status && <Text mt="sm">{status}</Text>}
    </>
  );
};