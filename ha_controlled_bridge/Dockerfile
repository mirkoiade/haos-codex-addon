FROM ghcr.io/home-assistant/base:3.24

RUN apk add --no-cache python3 py3-pip
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY policy.py transactions.py bridge.py ./
CMD ["python3", "/app/bridge.py"]
