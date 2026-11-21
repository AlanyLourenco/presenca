# Servidor de permanência do Presença (Marco 4) em contêiner.
# Use pelo docker-compose.yml da pasta marco-04 (perfil "tudo").
FROM python:3.12-slim
WORKDIR /app/servidor
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py config.exemplo.json ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "servidor.py"]
