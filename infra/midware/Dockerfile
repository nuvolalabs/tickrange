# midware — Python 3 toolchain for the tick ingester + range engine (host networking)
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive SSH_PORT=2223
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server ca-certificates curl git sudo bash vim procps \
      python3 python3-pip python3-venv python3-dev build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh
COPY ssh/authorized_keys /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PermitRootLogin[[:space:]].*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PasswordAuthentication[[:space:]].*/PasswordAuthentication no/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PubkeyAuthentication[[:space:]].*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
COPY sshd-entrypoint.sh /usr/local/bin/sshd-entrypoint.sh
RUN chmod +x /usr/local/bin/sshd-entrypoint.sh
WORKDIR /workspace
EXPOSE 2223
ENTRYPOINT ["/usr/local/bin/sshd-entrypoint.sh"]
CMD []
