# syntax=docker/dockerfile:1
#
# ks0man-site - MAARS / KS0MAN WordPress rebuild, demonstration image.
#
# One image. `docker compose up` and the site is there, installed and seeded.
# The image carries the club's own code (the maars-core plugin and the maars
# block theme) and the club's own record: the newsletters, minutes, reports and
# photographs, in full and unredacted, by the Society's decision of 17 September
# 2026. Nothing third-party, and nothing about the machine this was built on.
# See CONTRACT.md, "HARD RULE - WHOSE INFORMATION IS IT".
#
# Base image is pinned here and ONLY here; CI does not pin it.
FROM wordpress:7.1-php8.3-apache

# WP-CLI. It is here because first-boot seeding without it means hand-rolling
# an installer against wp-load.php, and that is how you end up with a demo that
# only works on the machine it was written on.
#
# Pinned version + SHA-512 baked in. The digest below was taken from the
# published wp-cli-2.12.0.phar.sha512 release asset AND recomputed from the
# downloaded phar; verifying against a hash that travels with the download is
# not verification, so the expected value lives in this file, in git.
ARG WP_CLI_VERSION=2.12.0
ARG WP_CLI_SHA512=be928f6b8ca1e8dfb9d2f4b75a13aa4aee0896f8a9a0a1c45cd5d2c98605e6172e6d014dda2e27f88c98befc16c040cbb2bd1bfa121510ea5cdf5f6a30fe8832

# One RUN, no apt-get, no upgrade: the base image is the unit of patching, so a
# rebuild is how this image gets security fixes.
#
# The same RUN drops in an Apache override, because pretty permalinks are
# load-bearing here: maars_publication rewrites to /archive/%year%/, and
# without AllowOverride the .htaccess WordPress writes is ignored and every
# archive URL 404s.
RUN set -eux; \
    curl -fsSL -o /usr/local/bin/wp \
      "https://github.com/wp-cli/wp-cli/releases/download/v${WP_CLI_VERSION}/wp-cli-${WP_CLI_VERSION}.phar"; \
    printf '%s  %s\n' "${WP_CLI_SHA512}" /usr/local/bin/wp | sha512sum --check --strict -; \
    chmod 0755 /usr/local/bin/wp; \
    wp --allow-root --version; \
    printf '%s\n' \
      '<Directory /var/www/html>' \
      '    AllowOverride All' \
      '</Directory>' \
      > /etc/apache2/conf-available/maars-permalinks.conf; \
    a2enconf maars-permalinks

# The club's code, staged out of the way of the volume. The entrypoint copies
# it into wp-content on every boot, so pulling a newer image actually changes
# the running site instead of losing to a stale volume.
COPY wp/plugins/maars-core /usr/src/maars/plugins/maars-core
COPY wp/themes/maars       /usr/src/maars/themes/maars
COPY docker/site-url.php   /usr/src/maars/site-url.php
COPY tools/seed.php        /usr/src/maars/tools/seed.php
# The media importer. Shipping media/ without this ships 179 files and no way to
# import them, which is exactly what happened: the entrypoint logged "no media
# importer ... skipping" and the archive stayed at four records.
COPY tools/import_media.php /usr/src/maars/tools/import_media.php
COPY content/seed.json     /usr/src/maars/content/seed.json
# The club's own photographs and governance documents, published in full:
# 24 of them carry officer contact details and 18 are memorial portraits, and
# they ship deliberately -- see CONTRACT.md. What is screened OUT is
# third-party material, which is not the Society's to republish; that is what
# tools/screen_media.py fails on.
COPY media/                /usr/src/maars/media/
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/maars-entrypoint.sh

# Layout mirrors the repo, so tools/seed.php can find content/seed.json at
# __DIR__ . '/../content/seed.json'. MAARS_SEED_JSON is the same path, for
# seed scripts that would rather ask than guess.
ENV MAARS_SRC=/usr/src/maars \
    MAARS_SEED_JSON=/usr/src/maars/content/seed.json \
    WP_CLI_CACHE_DIR=/tmp/wp-cli-cache

# No secrets are baked in. Every credential arrives at run time, from the
# environment; the local-development values are written literally in
# docker-compose.yml, which is the only place they exist.
LABEL org.opencontainers.image.title="ks0man-site" \
      org.opencontainers.image.description="Manhattan Area Amateur Radio Society (KS0MAN) website: WordPress 6.7 with the maars-core plugin and the maars block theme. Runnable demonstration build - seed content is club history, governance and the archive's shape only, and every changeable fact carries a freshness grade." \
      org.opencontainers.image.source="https://github.com/Atvriders/ks0man-site" \
      org.opencontainers.image.documentation="https://github.com/Atvriders/ks0man-site#readme" \
      org.opencontainers.image.url="https://github.com/Atvriders/ks0man-site" \
      org.opencontainers.image.licenses="GPL-2.0-or-later" \
      org.opencontainers.image.vendor="Manhattan Area Amateur Radio Society (MAARS), Manhattan, Kansas" \
      org.opencontainers.image.base.name="docker.io/library/wordpress:6.7-php8.3-apache"

# wp-login.php is a real readiness signal: it needs PHP, Apache and the
# database all three. start-period covers first-boot install and seeding.
HEALTHCHECK --interval=30s --timeout=10s --start-period=150s --retries=5 \
  CMD curl -fsS -o /dev/null http://localhost/wp-login.php || exit 1

ENTRYPOINT ["/usr/local/bin/maars-entrypoint.sh"]
CMD ["apache2-foreground"]
