FROM python:3.11-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY . .

ENV PORT=5050
ENV WATCHLIST_DATA_PATH=/data/watchlist_data.json

EXPOSE 5050

CMD ["sh", "-c", "gunicorn web_app:app --bind 0.0.0.0:${PORT} --workers 1 --timeout 180"]
