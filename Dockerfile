FROM linuxserver/ffmpeg

WORKDIR /app

COPY requirements.txt requirements.txt
RUN apt update && apt install  -y python3 python3-pip --no-install-recommends && pip3 install -r requirements.txt --upgrade

COPY telethon-downloader /app
COPY root/ /

ENTRYPOINT ["/init"]
