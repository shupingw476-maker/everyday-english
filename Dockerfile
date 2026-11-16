FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py run.sh requirements.txt README.md ./
COPY server ./server
COPY static ./static
COPY data ./data

ENV JINBU_HOST=0.0.0.0 \
    JINBU_PORT=8080 \
    JINBU_DATA=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["python", "app.py"]
