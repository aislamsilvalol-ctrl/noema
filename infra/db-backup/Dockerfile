# Nightly logical backup of the production database into a Railway bucket.
# pg_dump must be at least the server's major version: the server is
# pgvector/pgvector:pg16.
FROM postgres:16-alpine
RUN apk add --no-cache aws-cli
COPY backup.sh /backup.sh
CMD ["/bin/sh", "/backup.sh"]
