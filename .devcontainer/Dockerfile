FROM mambaorg/micromamba

USER root

ENV USERNAME=mambauser

ENV PATH=/opt/conda/envs/env_zoo_calrissian/bin:$PATH

RUN apt-get update -y \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl sudo git nodejs wget curl git-flow vim jq

RUN echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

RUN chown -R mambauser:1000 /opt/conda/

COPY ./assets /assets

RUN chown -R mambauser:1000 /assets

USER mambauser

ADD .devcontainer/environment.yml /tmp/environment.yml

RUN micromamba create -f /tmp/environment.yml

WORKDIR /home/mambauser
