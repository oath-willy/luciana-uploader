import { Button, Group, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import axios from 'axios';
import { useState } from 'react';

const RunRScript = () => {
  const [scriptPath, setScriptPath] = useState("");

  const handleRunScript = async () => {
    if (!scriptPath.trim()) {
      notifications.show({
        title: "Errore",
        message: "Inserisci un percorso valido per lo script R",
        color: "red",
      });
      return;
    }

    try {
      const res = await axios.post(`${process.env.REACT_APP_BACKEND_URL || ''}/api/run-r-script`, {
        script_path: scriptPath.trim(),
      });

      notifications.show({
        title: "Script R completato",
        message: res.data.output,
        color: "green",
      });
    } catch (err: any) {
      notifications.show({
        title: "Errore nell'esecuzione",
        message: err?.response?.data?.detail || "Errore generico",
        color: "red",
      });
    }
  };

  return (
    <Group justify="center" mt="md" style={{ flexDirection: 'column', alignItems: 'center' }}>
      <TextInput
        placeholder="Inserisci percorso script es: ~/timestamp.R"
        value={scriptPath}
        onChange={(e) => setScriptPath(e.currentTarget.value)}
        style={{ width: 400 }}
      />
      <Button onClick={handleRunScript} variant="outline" mt="sm">
        Esegui script R
      </Button>
    </Group>
  );
};

export default RunRScript;