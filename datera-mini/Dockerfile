# DATERA EDU mini: image for free hosting (Hugging Face Spaces, Docker SDK) or any Docker host.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git && rm -rf /var/lib/apt/lists/*

# Spaces runs the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# CPU build of PyTorch is much smaller than the default one
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

# Download the neural networks while the image is built, so the first request is not slow
RUN python -c "import whisper; whisper.load_model('small')" \
 && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
 && python -c "from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector; Wav2Vec2FeatureExtractor.from_pretrained('microsoft/wavlm-base-plus-sv'); WavLMForXVector.from_pretrained('microsoft/wavlm-base-plus-sv')"

EXPOSE 7860
CMD ["uvicorn", "web.server:app", "--host", "0.0.0.0", "--port", "7860"]
