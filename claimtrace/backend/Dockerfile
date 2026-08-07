FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy parser and engine as editable packages
COPY parser/ /app/parser/
COPY engine/ /app/engine/
COPY backend/ /app/backend/

# Install all packages
RUN pip install --no-cache-dir \
    -e /app/parser/ \
    -e /app/engine/ \
    -e /app/backend/[dev]

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
