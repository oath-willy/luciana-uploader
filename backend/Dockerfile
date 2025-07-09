FROM python:3.11-slim

WORKDIR /app

# Copia requirements e installa
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il codice (incluso backend.main)
COPY . /app/

# Comando di avvio + sleep fallback
ENTRYPOINT ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port 8080 || sleep 60"]
