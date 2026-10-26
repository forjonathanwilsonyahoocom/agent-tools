FROM python:3.13.17-slim-trixie

# Install system dependencies for spaCy and VADER
RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set workdir
WORKDIR /app

# Copy everything
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m pip install .

# Download spaCy model
RUN python -m spacy download en_core_web_sm
RUN python -m nltk.downloader -d /nltk_data punkt_tab
ENV NLTK_DATA=/nltk_data

# Expose entry point
ENTRYPOINT ["text-analysis"]
