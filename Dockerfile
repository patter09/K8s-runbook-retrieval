FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (separate layer) so code changes don't force
# a full reinstall of everything, including the heavy torch/transformers
# stack sentence-transformers pulls in.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]