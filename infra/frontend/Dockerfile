# frontend — Node 20 toolchain for the Vite/React UI (host networking)
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive SSH_PORT=2222
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server ca-certificates curl git gnupg sudo bash vim procps \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh
COPY ssh/authorized_keys /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PermitRootLogin[[:space:]].*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PasswordAuthentication[[:space:]].*/PasswordAuthentication no/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PubkeyAuthentication[[:space:]].*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
COPY sshd-entrypoint.sh /usr/local/bin/sshd-entrypoint.sh
RUN chmod +x /usr/local/bin/sshd-entrypoint.sh
ENV PATH=/usr/local/bin:$PATH
WORKDIR /workspace
EXPOSE 2222
ENTRYPOINT ["/usr/local/bin/sshd-entrypoint.sh"]
CMD []
