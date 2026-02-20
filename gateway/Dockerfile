FROM python:3.11-slim

# Create a non-root user (Required for Hugging Face, good practice everywhere)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy and install requirements
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=user:user app/ ./app/

# Make sure the data folder exists for research.db
RUN mkdir -p app/data

# Removed --reload for production stability
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
