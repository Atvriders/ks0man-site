<?php
/**
 * MAARS — resolve WP_HOME / WP_SITEURL for however this stack was actually started.
 *
 * This file exists as a FILE, and not as PHP embedded in docker-compose.yml,
 * for one hard-won reason: Docker Compose interpolates `$VAR` inside compose
 * values. Every PHP variable in an inline WORDPRESS_CONFIG_EXTRA is silently
 * replaced with an empty string, so `$maars_url = getenv_docker(...)` reaches
 * the container as `= getenv_docker(...)` and WordPress dies with
 *   PHP Parse error: syntax error, unexpected token "=", expecting end of file
 * on every request. Escaping as `$$` is the documented workaround, but it puts
 * the correctness of the whole site on one escape rule that `docker compose
 * config` does not even render back, so it cannot be checked before deploying.
 *
 * A file has no such hazard: it is linted by `php -l`, executed directly by
 * tests/test_site_url.py, and the compose file only has to say `require_once`
 * with no dollar sign anywhere in it.
 *
 * Loaded from wp-config.php, so it runs on every request, before WordPress
 * boots. It must define constants and nothing else.
 */

// Only meaningful inside wp-config; never expose it directly.
if ( ! function_exists( 'getenv_docker' ) ) {
	/**
	 * The official wordpress image defines this in wp-config-docker.php. The
	 * fallback keeps the file runnable standalone under test.
	 */
	function getenv_docker( $env, $default ) { // phpcs:ignore
		$v = getenv( $env );
		return ( false !== $v && '' !== $v ) ? $v : $default;
	}
}


if ( ! function_exists( 'maars_normalise_site_url' ) ) {
	/**
	 * Force a scheme onto a site URL, because a bare host silently breaks everything.
	 *
	 * Setting MAARS_SITE_URL to `example.org` rather than `https://example.org`
	 * looks reasonable and produces a site that half works. WordPress stores the
	 * value verbatim, then some call sites prepend a scheme and some do not, so
	 * the page emits BOTH of these from the same request:
	 *
	 *   https://example.orgexample.org/wp-includes/blocks/navigation/style.min.css
	 *   src="example.org/wp-includes/js/.../navigation/view.min.js"
	 *
	 * The first 404s on a doubled host, the second resolves as a relative path.
	 * Observed live: it took out the navigation block's stylesheet and its
	 * interactivity module, so the menu rendered as a raw list with its Menu and
	 * Close buttons both showing.
	 *
	 * @param string $url    Whatever the operator set.
	 * @param array  $server Superglobal-shaped array, for deciding the scheme.
	 * @return string Absolute origin with a scheme, or '' if unusable.
	 */
	function maars_normalise_site_url( $url, array $server = array() ) {
		$url = trim( (string) $url );
		if ( '' === $url ) {
			return '';
		}
		if ( preg_match( '#^https?://#i', $url ) ) {
			return rtrim( $url, '/' );
		}
		/* A scheme-relative //host is legal in a link but not in WP_HOME. */
		$url = ltrim( $url, '/' );
		$https = ( ! empty( $server['HTTPS'] ) && 'off' !== $server['HTTPS'] );
		if (
			! $https
			&& '1' === getenv_docker( 'MAARS_TRUST_PROXY', '0' )
			&& isset( $server['HTTP_X_FORWARDED_PROTO'] )
			&& 'https' === strtolower( (string) $server['HTTP_X_FORWARDED_PROTO'] )
		) {
			$https = true;
		}
		return ( $https ? 'https://' : 'http://' ) . rtrim( $url, '/' );
	}
}

if ( ! function_exists( 'maars_resolve_site_url' ) ) {
	/**
	 * Decide the site URL, or return '' to leave WordPress on its stored option.
	 *
	 * The Host header is attacker-controlled. Believed blindly it lets someone
	 * bake their own domain into every absolute URL the site emits — password
	 * reset links, canonical tags, cached pages. So the request host is accepted
	 * only where this stack could plausibly live: loopback, a private LAN range,
	 * a .local/.lan/.internal name, or a host the operator listed themselves.
	 *
	 * @param array $server  Superglobal-shaped array, injectable for tests.
	 * @return string Absolute origin, or '' for "do not define anything".
	 */
	function maars_resolve_site_url( array $server ) {
		$explicit = getenv_docker( 'MAARS_SITE_URL', '' );
		if ( '' !== $explicit ) {
			return maars_normalise_site_url( $explicit, $server );
		}

		if ( empty( $server['HTTP_HOST'] ) ) {
			return '';
		}

		$raw = strtolower( (string) $server['HTTP_HOST'] );

		// Shape first: host[:port] only. Rejects CR/LF, paths, userinfo and the
		// ambiguous forms used to smuggle a second host past a naive check.
		if ( ! preg_match( '/^([a-z0-9._-]+|\[[0-9a-f:]+\])(:[0-9]{1,5})?$/', $raw ) ) {
			return '';
		}

		$host = preg_replace( '/:[0-9]{1,5}$/', '', $raw );
		$ok   = false;

		// An explicit allowlist always wins. Space or comma separated.
		$allowed = trim( getenv_docker( 'MAARS_ALLOWED_HOSTS', '' ) );
		if ( '' !== $allowed ) {
			foreach ( preg_split( '/[\s,]+/', strtolower( $allowed ) ) as $entry ) {
				if ( '' !== $entry && ( $entry === $raw || $entry === $host ) ) {
					$ok = true;
					break;
				}
			}
		}

		if ( ! $ok ) {
			$bare = trim( $host, '[]' );
			if ( 'localhost' === $host || '::1' === $bare ) {
				$ok = true;
			} elseif ( filter_var( $bare, FILTER_VALIDATE_IP ) ) {
				// Loopback and RFC1918/ULA only. A public IP is not something
				// this stack should adopt just because someone asked.
				$ok = ! filter_var(
					$bare,
					FILTER_VALIDATE_IP,
					FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE
				);
			} elseif ( preg_match( '/\.(local|lan|internal|home|localdomain)$/', $host ) ) {
				$ok = true;
			}
		}

		if ( ! $ok ) {
			return '';
		}

		// X-Forwarded-Proto is only meaningful behind a proxy you control, so it
		// is opt-in rather than believed by default.
		$https = ( ! empty( $server['HTTPS'] ) && 'off' !== $server['HTTPS'] );
		if (
			! $https
			&& '1' === getenv_docker( 'MAARS_TRUST_PROXY', '0' )
			&& isset( $server['HTTP_X_FORWARDED_PROTO'] )
			&& 'https' === strtolower( (string) $server['HTTP_X_FORWARDED_PROTO'] )
		) {
			$https = true;
		}

		return ( $https ? 'https://' : 'http://' ) . $raw;
	}
}

$maars_site_url = maars_resolve_site_url( isset( $_SERVER ) ? $_SERVER : array() );
if ( '' !== $maars_site_url ) {
	if ( ! defined( 'WP_HOME' ) ) {
		define( 'WP_HOME', $maars_site_url );
	}
	if ( ! defined( 'WP_SITEURL' ) ) {
		define( 'WP_SITEURL', $maars_site_url );
	}
}
unset( $maars_site_url );

if ( ! defined( 'AUTOMATIC_UPDATER_DISABLED' ) ) {
	define( 'AUTOMATIC_UPDATER_DISABLED', true );
}
if ( ! defined( 'DISALLOW_FILE_EDIT' ) ) {
	define( 'DISALLOW_FILE_EDIT', true );
}
