import { Button, Group, TextInput } from '@mantine/core';
import { useState } from 'react';

const RunRScriptLog = () => {
  const [scriptPath, setScriptPath] = useState("");
  const [logLines, setLogLines] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const appendLog = (line: string) => {
    setLogLines((prev) => [...prev, line]);
  };

  const handleRunScript = async () => {
    if (!scriptPath.trim()) {
      appendLog("❌ Inserisci un percorso valido per lo script R");
      return;
    }

    setIsRunning(true);
    setLogLines([]);
    appendLog("📡 Script avviato...");

    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/run-r-script/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script_path: scriptPath.trim() }),
      });

      if (!res.body) throw new Error("Nessun output ricevuto");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n").filter(Boolean);
        lines.forEach(appendLog);
      }

      appendLog("✅ Script completato");
    } catch (err: any) {
      appendLog("❌ Errore: " + (err.message || "Errore generico"));
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <Group justify="center" mt="md" style={{ flexDirection: 'column', alignItems: 'center' }}>
      <TextInput
        placeholder="Inserisci percorso script es: ~/script.R"
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

export default RunRScriptLog;
