FROM python:3.12-slim
WORKDIR /app
COPY agent/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY catalog /app/catalog
COPY agent/main.py /app/agent/main.py
WORKDIR /app/agent
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
