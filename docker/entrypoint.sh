#!/usr/bin/env bash
#
# ks0man-site container entrypoint - MAARS / KS0MAN.
#
# Wraps the stock WordPress entrypoint. Two jobs, clearly separated:
#
#   EVERY BOOT
#     Copy the maars-core plugin and the maars theme out of the image
#     (/usr/src/maars) into /var/www/html/wp-content. wp-content/uploads is a
#     volume and the code is not, so this is what makes `docker compose pull`
#     followed by `up -d` actually ship new code instead of losing to a volume
#     that was populated in 2024 and never looked at again.
#
#   FIRST BOOT ONLY, guarded by a marker file on the uploads volume
#     Wait for the database, run `wp core install` non-interactively from the
#     environment, activate the plugin and theme, set permalinks and the club
#     timezone, then run tools/seed.php.
#
# Idempotent: safe to run on every container start, every restart, and after
# an image upgrade. The marker is only written when first boot fully succeeds,
# so a half-finished setup is retried rather than papered over.
#
# It says what it is doing. It never prints a password, a salt, or the
# environment. Do not add `set -x` to this file.

set -euo pipefail

readonly MAARS_SRC_DIR="${MAARS_SRC:-/usr/src/maars}"
readonly WP_ROOT=/var/www/html
readonly WP_CONTENT="${WP_ROOT}/wp-content"
readonly UPLOADS_DIR="${WP_CONTENT}/uploads"
readonly MARKER="${UPLOADS_DIR}/.maars-first-boot-complete"
readonly BASE_ENTRYPOINT=/usr/local/bin/docker-entrypoint.sh
readonly WEB_USER=www-data
readonly WEB_GROUP=www-data

maars_log() { printf '[maars] %s\n' "$*"; }
maars_die() { printf '[maars] FATAL: %s\n' "$*" >&2; exit 1; }

# wp-cli, always against this install, always allowed to run as root (the
# container is single-tenant and PID 1 is root).
wp() { /usr/local/bin/wp --path="$WP_ROOT" --allow-root "$@"; }

# Every variable this script reads is set literally in docker-compose.yml:
#   MAARS_SITE_URL  MAARS_SITE_TITLE  MAARS_TIMEZONE
#   MAARS_ADMIN_USER  MAARS_ADMIN_PASSWORD  MAARS_ADMIN_EMAIL  MAARS_ADMIN_EMAIL_DOMAIN
#   MAARS_SKIP_SEED  MAARS_DB_WAIT_TRIES  WORDPRESS_DB_HOST/NAME/USER/PASSWORD
# plus MAARS_SRC and MAARS_SEED_JSON, which are ENV in the Dockerfile because
# they describe the image's own layout. There are no others, and there is no
# .env file to go looking in: what compose says is what this script sees.

# --- every boot -------------------------------------------------------------

# chown is best-effort throughout: it is the right thing to do when this runs
# as root, which is how the base image is built to run, and it must not take
# the whole container down when someone runs it as somebody else.
maars_own() { chown "$@" 2>/dev/null || true; }

maars_sync_payload() {
	install -d -o "$WEB_USER" -g "$WEB_GROUP" \
		"${WP_CONTENT}/plugins" "${WP_CONTENT}/themes" "$UPLOADS_DIR" 2>/dev/null \
		|| mkdir -p "${WP_CONTENT}/plugins" "${WP_CONTENT}/themes" "$UPLOADS_DIR"

	local item
	for item in plugins/maars-core themes/maars; do
		if [ -d "${MAARS_SRC_DIR}/${item}" ]; then
			rm -rf "${WP_CONTENT:?}/${item}"
			cp -a "${MAARS_SRC_DIR}/${item}" "${WP_CONTENT}/${item}"
			maars_own -R "${WEB_USER}:${WEB_GROUP}" "${WP_CONTENT}/${item}"
			maars_log "synced ${item} from the image"
		else
			maars_log "WARNING: ${MAARS_SRC_DIR}/${item} is not in this image"
		fi
	done
}

# --- first boot -------------------------------------------------------------

# The stock entrypoint copies WordPress into /var/www/html and writes
# wp-config.php, but only when it is handed an apache2/php-fpm command.
# Calling it with `apache2 -v` runs exactly that setup and then exits, which
# leaves a configured WordPress for wp-cli to talk to before the real server
# starts. Nothing here races the web server, because the web server is not up.
maars_prepare_wordpress() {
	maars_log "materialising WordPress core and wp-config.php"
	if ! "$BASE_ENTRYPOINT" apache2 -v >/dev/null 2>&1; then
		maars_log "WARNING: the base entrypoint returned non-zero during setup"
	fi
	[ -f "${WP_ROOT}/wp-config.php" ] || maars_die "wp-config.php was not created; check the WORDPRESS_DB_* variables"
}

maars_wait_for_db() {
	local tries="${MAARS_DB_WAIT_TRIES:-60}" attempt=1
	maars_log "waiting for the database (up to ${tries} attempts, 2s apart)"
	while [ "$attempt" -le "$tries" ]; do
		if php -r '
if (!function_exists("mysqli_connect")) { exit(0); }
mysqli_report(MYSQLI_REPORT_OFF);
$host = getenv("WORDPRESS_DB_HOST"); if (!$host) { $host = "db"; }
$port = 3306;
if (strpos($host, ":") !== false) {
	list($host, $maybe_port) = explode(":", $host, 2);
	if (ctype_digit($maybe_port)) { $port = (int) $maybe_port; }
}
$user = getenv("WORDPRESS_DB_USER"); if (!$user) { $user = "wordpress"; }
$name = getenv("WORDPRESS_DB_NAME"); if (!$name) { $name = "wordpress"; }
$pass = getenv("WORDPRESS_DB_PASSWORD");
if ($pass === false) { $pass = ""; }
$link = @mysqli_connect($host, $user, $pass, $name, $port);
exit($link ? 0 : 1);
' 2>/dev/null; then
			maars_log "database is up"
			return 0
		fi
		sleep 2
		attempt=$((attempt + 1))
	done
	maars_log "WARNING: database not reachable after ${tries} attempts; continuing so the failure is visible"
	return 0
}

maars_first_boot() {
	local failed=0

	local site_url="${MAARS_SITE_URL:-http://localhost:3039}"
	local site_title="${MAARS_SITE_TITLE:-Manhattan Area Amateur Radio Society}"
	local admin_user="${MAARS_ADMIN_USER:-maars_admin}"
	# Assembled from two parts on purpose. This image is public, so no address
	# of any kind is written out whole in this repository - not even a fake
	# one. Override MAARS_ADMIN_EMAIL locally; it never leaves your machine.
	local admin_domain="${MAARS_ADMIN_EMAIL_DOMAIN:-maars.invalid}"
	local admin_email="${MAARS_ADMIN_EMAIL:-no-reply@${admin_domain}}"

	if [ -z "${MAARS_ADMIN_PASSWORD:-}" ]; then
		maars_die "MAARS_ADMIN_PASSWORD is empty, so there is nothing to install with.
        It is set literally in docker-compose.yml, under the wordpress service.
        Put a value back and start again. This script never prints it."
	fi

	if wp core is-installed >/dev/null 2>&1; then
		maars_log "WordPress is already installed; not reinstalling"
	else
		maars_log "installing WordPress at ${site_url} for administrator '${admin_user}'"
		# The real password does NOT go on the command line: argv is readable
		# through /proc for the life of the process. Install with a throwaway
		# and hand the real one over through the environment, below.
		local throwaway
		throwaway="$(php -r 'echo bin2hex(random_bytes(24));')"
		# --skip-email: there is no mail transport in this image, and the
		# Society's official organ is the e-mail reflector, not the website.
		if ! wp core install \
			--url="$site_url" \
			--title="$site_title" \
			--admin_user="$admin_user" \
			--admin_password="$throwaway" \
			--admin_email="$admin_email" \
			--skip-email; then
			maars_log "ERROR: wp core install failed"
			return 1
		fi
	fi

	# Set the administrator password from the environment. Runs on every
	# first-boot attempt, so a boot that failed halfway still ends up with the
	# password the operator actually asked for.
	export MAARS_ADMIN_LOGIN="$admin_user"
	if wp eval '
$user = get_user_by( "login", getenv( "MAARS_ADMIN_LOGIN" ) );
if ( ! $user ) { WP_CLI::error( "administrator account not found" ); }
wp_set_password( getenv( "MAARS_ADMIN_PASSWORD" ), $user->ID );
'; then
		maars_log "administrator password set from the environment"
	else
		maars_log "ERROR: could not set the administrator password"
		failed=1
	fi

	if wp plugin activate maars-core; then
		maars_log "activated the maars-core plugin"
	else
		maars_log "ERROR: could not activate the maars-core plugin"
		failed=1
	fi

	if wp theme activate maars; then
		maars_log "activated the maars theme"
	else
		maars_log "ERROR: could not activate the maars theme"
		failed=1
	fi

	# Never store a date a computer can compute - but the timezone the
	# computation happens in is a fact, and it is Manhattan, Kansas.
	wp option update timezone_string "${MAARS_TIMEZONE:-America/Chicago}" || failed=1

	# maars_publication rewrites to /archive/%year%/, so permalinks have to be
	# pretty and .htaccess has to exist before any archive URL will resolve.
	wp rewrite structure '/%postname%/' --hard || failed=1
	wp rewrite flush --hard || failed=1

	maars_seed || failed=1

	return "$failed"
}

maars_seed() {
	local seed_php="${MAARS_SRC_DIR}/tools/seed.php"

	if [ "${MAARS_SKIP_SEED:-0}" = "1" ]; then
		maars_log "MAARS_SKIP_SEED=1; leaving the site empty"
		return 0
	fi
	if [ ! -f "$seed_php" ]; then
		maars_log "WARNING: no seed script at ${seed_php}; leaving the site empty"
		return 0
	fi

	maars_log "seeding from ${MAARS_SEED_JSON:-${MAARS_SRC_DIR}/content/seed.json}"
	# seed.php runs inside a bootstrapped WordPress - it returns without doing
	# anything unless WP_CLI is defined - so `wp eval-file` is the only way to
	# run it, and there is deliberately no fallback: a fallback here could only
	# ever turn a silent no-op into a reported success, which is the exact
	# failure this whole project exists to stop doing.
	local media_php="${MAARS_SRC_DIR}/tools/import_media.php"

	if wp eval-file "$seed_php"; then
		maars_log "seed complete"

		# The screened archive media, imported after the content it belongs to.
		# Idempotent on _maars_media_src, so it is safe on every boot -- a media
		# library that grew by 179 items per restart would be a slow, silent
		# disaster. A failure here is reported but does not fail the boot: the
		# site is still usable without its photographs.
		if [ -f "$media_php" ]; then
			wp eval-file "$media_php" || maars_log "WARNING: media import reported a problem"
		else
			maars_log "WARNING: no media importer at ${media_php}"
		fi

		return 0
	fi
	maars_log "ERROR: seeding failed"
	return 1
}

# --- main -------------------------------------------------------------------

main() {
	maars_sync_payload

	case "${1:-}" in
		apache2* | php-fpm)
			if [ -e "$MARKER" ]; then
				maars_log "first boot already done ($(cat "$MARKER" 2>/dev/null || echo 'marker present')); skipping install and seed"
			else
				maars_prepare_wordpress
				maars_wait_for_db
				if maars_first_boot; then
					date -u +%Y-%m-%dT%H:%M:%SZ >"$MARKER"
					maars_own "${WEB_USER}:${WEB_GROUP}" "$MARKER"
					maars_log "first-boot setup complete"
				else
					maars_log "first-boot setup finished with errors; the marker was NOT written, so the next boot will try again"
				fi
			fi
			maars_own "${WEB_USER}:${WEB_GROUP}" "$UPLOADS_DIR"
			;;
		*)
			maars_log "command is '${1:-}'; skipping WordPress setup"
			;;
	esac

	maars_log "handing off to the WordPress entrypoint"
	exec "$BASE_ENTRYPOINT" "$@"
}

main "$@"
