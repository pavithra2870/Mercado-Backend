FROM python:3.11-slim

# 1. Set environment variables to prevent Python from buffering stdout 
# and to route Hugging Face model downloads to a writable directory.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/user/.cache/huggingface

# 2. Install System Dependencies
# gcc/g++: Needed if scikit-learn or curl_cffi need to build C-extensions
# libjpeg/zlib/freetype: Crucial for xhtml2pdf to render PDF text and images
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 3. Setup Non-Root User (MANDATORY FOR HUGGING FACE SPACES)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# 4. Install Python Requirements
# Use --chown so the non-root user actually owns the files
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy Application Code
COPY --chown=user:user app/ ./app/

# 6. Start the FastAPI server
# Port 7860 is the required default port for Hugging Face Spaces
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]