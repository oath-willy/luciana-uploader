// frontend/src/DragAndDrop.js
import React from "react";

export default function DragAndDrop({ onFileSelected, status }) {
  const handleDrop = (event) => {
    event.preventDefault();
    const file = event.dataTransfer.files[0];
    if (file) onFileSelected(file);
  };

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) onFileSelected(file);
  };

  return (
    <div
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
      style={{
        border: "2px dashed #ccc",
        padding: "2rem",
        textAlign: "center",
        borderRadius: "10px",
      }}
    >
      <p>Trascina qui i file</p>
      <input type="file" onChange={handleFileChange} />
      <p>{status}</p>
    </div>
  );
}