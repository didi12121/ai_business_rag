FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Copy app
COPY app/ ./app/
COPY sql/ ./sql/

EXPOSE 8105

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8105"]
