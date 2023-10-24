FROM python:3.9.17-alpine AS basetelethon


WORKDIR /app

COPY requirements.txt requirements.txt
RUN apk add  --no-cache ffmpeg rust cargo  && \
	pip3 install -r requirements.txt --upgrade



FROM basetelethon

COPY telethon-downloader /app
COPY root/ /

RUN chmod 777 /app/bottorrent.py
RUN chmod 777 -R /etc/services.d/


VOLUME /download /watch /config

ENV bottorrent /config/bottorrent

CMD ["python3", "/app/bottorrent.py"]
