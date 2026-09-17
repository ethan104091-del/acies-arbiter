FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-v2.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-v2.txt
COPY . .
