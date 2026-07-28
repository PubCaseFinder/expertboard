FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8010

CMD ["flask", "--app", "app:create_app", "run", "--host", "0.0.0.0", "--port", "8010", "--debug"]

