FROM python:3.11-slim

# Install Google Chrome Stable, FFmpeg & Fonts on Cloud Server
RUN apt-get update && apt-get install -y \
    wget gnupg curl unzip ffmpeg git procps \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir flask requests python-dotenv selenium imageio-ffmpeg instagrapi yt-dlp

EXPOSE 7860 5000

# Run our Auto-Sync + Dashboard Server
CMD ["python", "cloud_runner.py"]