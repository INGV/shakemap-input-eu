#FROM python:3.7-slim-bullseye #### Aggiun gere anche gcc ai pacchetti da installare
FROM python:3.7-bullseye

LABEL maintainer="Valentino Lauciani <valentino.lauciani@ingv.it>"
ENV DEBIAN_FRONTEND=noninteractive 

# Installing all needed applications
RUN apt-get clean \
    && apt-get update \
    && apt-get dist-upgrade -y --no-install-recommends \
    && apt-get install -y \
        wget \
        vim

# Upgrade pip
RUN python -m pip install --upgrade pip

# Adding python3 libraries
RUN python3 -m pip install PyDriller
RUN python3 -m pip install numpy
RUN python3 -m pip install Pillow
RUN python3 -m pip install obspy
RUN python3 -m pip install requests

# Copy files
#COPY shakedata.py /opt
#COPY entrypoint.sh /opt

# Set GIT params
RUN git config --global user.email "valentino.lauciani@ingv.it"
RUN git config --global user.name "sergio"

#
WORKDIR /opt
ENTRYPOINT ["bash", "/opt/shakemap-input-eu/entrypoint.sh"]
