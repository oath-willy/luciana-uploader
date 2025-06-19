import React, { useEffect, useState } from 'react';
import './App.css';

function App() {
  const [backendResponse, setBackendResponse] = useState('');

  useEffect(() => {
    // Cambia questa URL se il backend è su una porta diversa
    fetch('http://localhost:8000/ping')
      .then(response => response.json())
      .then(data => {
        setBackendResponse(data.message);
      })
      .catch(error => {
        console.error('Errore chiamata backend:', error);
        setBackendResponse('Errore chiamata backend');
      });
  }, []);

  return (
    <div className="App">
      <h1>Test comunicazione Frontend - Backend</h1>
      <p>Risposta backend: {backendResponse}</p>
    </div>
  );
}

export default App;
