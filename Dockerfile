FROM python:3.8-bullseye

LABEL maintainer="Valentino Lauciani <valentino.lauciani@ingv.it>"
ENV DEBIAN_FRONTEND=noninteractive 

# Set User and Group variabls
ENV GROUP_NAME=shake
ENV USER_NAME=shake
ENV DIR_EE_HOME=/home/${USER_NAME}

# Set default User and Group id from arguments
# If UID and/or GID are equal to zero then new user and/or group are created
ARG ENV_UID=0
ARG ENV_GID=0

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
RUN python3 -m pip install xmldiff

##### START - Create user #####
RUN echo ENV_UID=${ENV_UID}
RUN echo ENV_GID=${ENV_GID}

RUN \
    if [ ${ENV_UID} -eq 0 ] || [ ${ENV_GID} -eq 0 ]; \
    then \
    echo ""; \
    echo "WARNING: when passing UID or GID equal to zero, new user and/or group are created."; \
    echo "         On Linux, if you run docker image by different UID or GID you could not able to write in docker mount data directory."; \
    echo ""; \
    fi

# Check if GID already exists
RUN cat /etc/group
RUN \
    if [ ${ENV_GID} -eq 0 ]; \
    then \
    addgroup --system ${GROUP_NAME}; \
    elif grep -q -e "[^:][^:]*:[^:][^:]*:${ENV_GID}:.*$" /etc/group; \
    then \
    GROUP_NAME_ALREADY_EXISTS=$(grep  -e "[^:][^:]*:[^:][^:]*:${ENV_GID}:.*$" /etc/group | cut -f 1 -d':'); \
    echo "GID ${ENV_GID} already exists with group name ${GROUP_NAME_ALREADY_EXISTS}"; \
    groupmod -n ${GROUP_NAME} ${GROUP_NAME_ALREADY_EXISTS}; \
    else \
    echo "GID ${ENV_GID} does not exist"; \
    addgroup --gid ${ENV_GID} --system ${GROUP_NAME}; \
    fi

# Check if UID already exists
RUN cat /etc/passwd
RUN \
    if [ ${ENV_UID} -eq 0 ]; \
    then \
    useradd --system -d ${DIR_EE_HOME} -g ${GROUP_NAME} -s /bin/bash ${USER_NAME}; \
    elif grep -q -e "[^:][^:]*:[^:][^:]*:${ENV_UID}:.*$" /etc/passwd; \
    then \
    USER_NAME_ALREADY_EXISTS=$(grep  -e "[^:][^:]*:[^:][^:]*:${ENV_UID}:.*$" /etc/passwd | cut -f 1 -d':'); \
    echo "UID ${ENV_UID} already exists with user name ${USER_NAME_ALREADY_EXISTS}"; \
    usermod -d ${DIR_EE_HOME} -g ${ENV_GID} -l ${USER_NAME} ${USER_NAME_ALREADY_EXISTS}; \
    else \
    echo "UID ${ENV_UID} does not exist"; \
    useradd --system -u ${ENV_UID} -d ${DIR_EE_HOME} -g ${ENV_GID} -G ${GROUP_NAME} -s /bin/bash ${USER_NAME}; \
    fi
# adduser -S -h ${DIR_EE_HOME} -G ${GROUP_NAME} -s /bin/bash ${USER_NAME}; \
# adduser --uid ${ENV_UID} --home ${DIR_EE_HOME} --gid ${ENV_GID} --shell /bin/bash ${USER_NAME}; \

# Set USER password 
RUN echo ${USER_NAME}:${USER_NAME} | chpasswd

# Create home drectory
RUN mkdir ${DIR_EE_HOME}

# Fix permissions for USER
RUN chown -R ${USER_NAME}:${GROUP_NAME} ${DIR_EE_HOME}
##### END - Create user #####

# Change user
USER ${USER_NAME}:${GROUP_NAME}

# Set GIT params
RUN git config --global user.email "valentino.lauciani@ingv.it"
RUN git config --global user.name "sergio"

#
WORKDIR /opt
ENTRYPOINT ["bash", "/opt/shakemap-input-eu/entrypoint.sh"]
