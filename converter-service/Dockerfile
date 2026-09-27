FROM python:3.10-slim-bullseye

RUN apt-get update && apt-get install -y --no-install-recommends --no-install-suggests build-essential libpq-dev python3-dev ffmpeg && pip install --no-cache-dir --upgrade pip


WORKDIR /app
COPY ./requirements.txt /app
#  for service health check 
COPY health_check.py /app/health_check.py
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
CMD python /app/health_check.py

RUN pip install --no-cache-dir --requirement /app/requirements.txt
COPY . /app

CMD ["python", "consumer.py"]