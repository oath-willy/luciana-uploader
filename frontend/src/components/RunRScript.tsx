import { Button, Group, TextInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import axios from 'axios';
import { useState } from 'react';

const RunRScript = () => {
  const [scriptPath, setScriptPath] = useState("");
  const [logLines, setLogLines] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  
  const appendLog = (line: string) => {
    setLogLines((prev) => [...prev, line]);
  };

  const handleRunScript = async () => {
    if (!scriptPath.trim()) {
      notifications.show({
        title: "Errore",
        message: "Inserisci un percorso valido per lo script R",
        color: "red",
      });
      return;
    }

    setIsRunning(true);  // ⛔ Disattiva bottone
    setLogLines([]);     // Pulisci log precedente
    appendLog("📡 Script avviato...");

    const id = notifications.show({
      title: "Esecuzione script",
      message: "Script R in esecuzione...",
      loading: true,
      autoClose: false,
      withCloseButton: false,
    });

    try {
      const res = await axios.post(`${process.env.REACT_APP_BACKEND_URL || ''}/api/run-r-script`, {
        script_path: scriptPath.trim(),
      });

      appendLog("✅ Script completato");
      appendLog("🧾 Output:");
      appendLog(res.data.output || "(Nessun output)");

      notifications.update({
        id,
        title: "Script R completato",
        message: res.data.output || "Esecuzione completata con successo",
        color: "green",
        loading: false,
        autoClose: 5000,
      });
    } catch (err: any) {
      appendLog("❌ Errore durante l'esecuzione:");
      appendLog(err?.response?.data?.detail || "Errore generico");

      notifications.update({
        id,
        title: "Errore nell'esecuzione",
        message: err?.response?.data?.detail || "Errore generico",
        color: "red",
        loading: false,
        autoClose: 5000,
      });
    } finally {
      setIsRunning(false); // ✅ Riattiva bottone
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

      <Button onClick={handleRunScript} variant="outline" mt="sm" disabled={isRunning}>
        {isRunning ? "In esecuzione..." : "Esegui script R"}
      </Button>

      <div style={{ marginTop: '1rem', width: '100%', maxWidth: 600 }}>
        {logLines.map((line, index) => (
          <div key={index} style={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
            {line}
          </div>
        ))}
      </div>

    </Group>
  );
};

export default RunRScript;