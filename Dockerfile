FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends imagemagick && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=8000
CMD ["gunicorn","--bind","0.0.0.0:8000","--timeout","600","--workers","1","app:app"]
