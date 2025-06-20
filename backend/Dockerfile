# Usa immagine base
FROM python:3.12-slim

# Installa dipendenze di sistema base (per evitare crash di pip)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set timezone UTC (best practice cloud)
ENV TZ=UTC

# Crea directory app
WORKDIR /app

# Copia requirements e installa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto del codice
COPY . .

# Espone porta FastAPI
EXPOSE 8000

# Avvia FastAPI con Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
