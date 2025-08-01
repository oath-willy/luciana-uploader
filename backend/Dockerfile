FROM python:3.11-slim

# Installa dipendenze minime
RUN apt-get update && apt-get install -y gcc libffi-dev libssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*

# Imposta directory di lavoro
WORKDIR /app

# Copia requirements e installa pacchetti Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice
COPY . .

# Espone la porta usata da Azure (sarà sovrascritta con $PORT)
EXPOSE 8080

# Usa la variabile d'ambiente PORT o default 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
