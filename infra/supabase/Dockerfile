# supabase — PostgreSQL 16 (+ sshd). Full Supabase API layer (PostgREST/Auth/Realtime)
# gets layered on later; for the tick app this box is the persistence store.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive SSH_PORT=2224
RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server ca-certificates curl git sudo bash vim procps \
      postgresql postgresql-contrib \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh
COPY ssh/authorized_keys /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PermitRootLogin[[:space:]].*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PasswordAuthentication[[:space:]].*/PasswordAuthentication no/' /etc/ssh/sshd_config \
 && sed -i -E 's/^[[:space:]]*#?[[:space:]]*PubkeyAuthentication[[:space:]].*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
COPY sshd-entrypoint.sh /usr/local/bin/sshd-entrypoint.sh
RUN chmod +x /usr/local/bin/sshd-entrypoint.sh
COPY supabase/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh
EXPOSE 2224 5432
ENTRYPOINT ["/usr/local/bin/sshd-entrypoint.sh"]
CMD ["/usr/local/bin/start.sh"]
