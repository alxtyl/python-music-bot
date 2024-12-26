# python-music-bot
A simple Discord bot that can stream audio from various sources. Built with [Wavelink](https://wavelink.dev/en/latest/index.html) & [Lavalink](https://lavalink.dev/).

## Running the bot
Depending on your setup, you can run the bot and Lavalink natively on your hardware. In order to help with deployment and not having to manage
different language versions, I went with Docker and Docker Compose for orchestrating the two services. 
Below are an example of a Dockerfile that will build the bot, and then a compose yaml to run the bot with Lavalink.

Sample Dockerfile:
```Dockerfile
# Must have 3.10 <= py version
FROM python:3.12-alpine

WORKDIR /app

COPY /python-music-bot /app

# Upgrade pip and install latests packages from pypi
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir discord.py==2.3.2 wavelink==3.4.1

CMD ["python", "main.py"]
```

Sample Docker Compose file:
```yaml
version: "3.8"

services:
    lavalink:
        image: LATEST_LAVALINK_IMAGE
        container_name: lavalink
        restart: unless-stopped
        environment:
            - LAVALINK_SERVER_PASSWORD=YOUR_SERVER_PASS
            - _JAVA_OPTIONS=-Xmx1G
            - SERVER_PORT=2333
        networks:
            - lavalink
        volumes:
            - ./application.yml:/opt/Lavalink/application.yml
            - ./plugins/:/opt/Lavalink/plugins/
        expose:
            - 2333
    wavelink:
        image: YOUR_BOT_IMAGE_NAME_HERE:LATEST
        container_name: YOUR_BOT_CONTAINER_NAME
        networks:
            - lavalink
        environment:
            - WAIT_TIME=13  # Delay the start of the container to allow Lavalink to load
            - LAVAINK_SERVER=http://lavalink:2333
            - LAVALINK_SERVER_PASSWORD=YOUR_SERVER_PASS  # This should match your password above
            - BOT_KEY=YOUR_BOT_KEY_HERE
        volumes:
            - ./app:YOUR_PATH_HERE

networks:
    lavalink:
       name: lavalink
```