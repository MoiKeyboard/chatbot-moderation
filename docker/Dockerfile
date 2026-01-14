# ==========================================
# 1. Base Stage: Shared OS & System Deps
# ==========================================
FROM python:3.14-slim AS base

WORKDIR /app

# Set environment variables common to both
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies (Common to Dev and Prod)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ==========================================
# 2. Builder Stage (Prod Dependency Setup)
# ==========================================
# We use this stage to build/install prod-only dependencies cleanly
FROM base AS builder

COPY requirements.txt .
# Install dependencies into the user directory to keep system clean and make copying easier
RUN pip install --no-cache-dir --user -r requirements.txt

# ==========================================
# 3. Development Stage
# ==========================================
# Extends base, adds dev tooling.
FROM base AS dev

# Install ALL dependencies (Prod + Dev)
COPY requirements.txt .
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# Copy source (Note: Docker Compose volume will likely override this)
COPY src/ src/
COPY tests/ tests/

# Default command for dev (can be overridden in compose)
CMD ["python", "src/main.py"]

# ==========================================
# 4. Production Stage
# ==========================================
# Extends base -> Minimal & Secure
FROM base AS prod

# Add user bin to PATH (to find the packages installed in builder)
ENV PATH="/root/.local/bin:$PATH"

# Copy verified dependencies from builder stage
COPY --from=builder /root/.local /root/.local

# Setup non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Copy application code from context
COPY src/ src/

EXPOSE 8080

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
