FROM python:3.10.12

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY /app .

COPY . .

ENTRYPOINT [ "bash", "_CI/entrypoint.sh"]





