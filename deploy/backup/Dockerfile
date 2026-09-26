FROM postgres:16-alpine
RUN apk add --no-cache rclone curl
COPY backup.sh backup-loop.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/backup-loop.sh
CMD ["/usr/local/bin/backup-loop.sh"]
