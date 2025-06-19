# Usa immagine base leggera
FROM python:3.12-slim

# Crea directory app
WORKDIR /app

# Copia requirements
COPY requirements.txt .

# Installa dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto del codice
COPY . .

# Espone porta
EXPOSE 8000

# Avvia FastAPI con Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]