# ─────────────────────────────────────────────────────────
#  Hevy Fatigue Monitor — Dockerfile
#  Multi-stage build: keeps the final image lean.
# ─────────────────────────────────────────────────────────

# Stage 1: install dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies into a separate prefix so we can copy
# just the site-packages into the final image
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# Stage 2: final runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY . .

# Create the data directory for the SQLite volume mount point
RUN mkdir -p /data

# Set the DB path to the persistent volume location
ENV DB_PATH=/data/hevy_fatigue.db

# Expose the FastAPI port
EXPOSE 8000

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
