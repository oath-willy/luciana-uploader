FROM python:3.11-slim

RUN apt-get update && apt-get install -y gcc libffi-dev libssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

ENTRYPOINT ["python", "main.py"]
