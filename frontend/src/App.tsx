import React, { useEffect, useState } from 'react';
import './App.css';

function App() {
  const [backendResponse, setBackendResponse] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState('');

  useEffect(() => {
    fetch(`${process.env.REACT_APP_BACKEND_URL}/ping`)
      .then(response => response.json())
      .then(data => {
        setBackendResponse(data.message);
      })
      .catch(error => {
        console.error('Errore chiamata backend:', error);
        setBackendResponse('Errore chiamata backend');
      });
  }, []);

  const handleUpload = () => {
    if (!selectedFile) {
      alert("Seleziona un file prima di caricare");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadStatus("Caricamento in corso...");

    fetch(`${process.env.REACT_APP_BACKEND_URL}/upload`, {
      method: "POST",
      body: formData,
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === "success") {
          setUploadStatus(`✅ File caricato: ${data.url}`);
        } else {
          setUploadStatus(`❌ Errore: ${data.detail || 'upload fallito'}`);
        }
      })
      .catch(err => {
        console.error("Errore upload:", err);
        setUploadStatus("❌ Errore durante l'upload");
      });
  };

  return (
    <div className="App">
      <h1>Test comunicazione Frontend - Backend</h1>
      <p>Risposta backend: {backendResponse}</p>

      <h2>Upload file</h2>
      <input
        type="file"
        onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
      />
      <br /><br />
      <button onClick={handleUpload}>Carica</button>

      <p>{uploadStatus}</p>
    </div>
  );
}

export default App;