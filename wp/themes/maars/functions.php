<?php
/**
 * MAARS theme — setup, assets and template-part areas.
 *
 * Manhattan Area Amateur Radio Society (KSØMAN), Manhattan, Kansas.
 * Founded 7 July 1976; the members voted to be a Society, not a Club.
 *
 * Design rule this theme exists to enforce: the site must never look current
 * when it is not. Presets live in theme.json, component styles in
 * assets/css/maars.css, and the WebGL2 propagation scene in assets/js/skywave.js.
 * No build step, no Composer, no npm, no external libraries.
 *
 * @package maars
 */

declare( strict_types = 1 );

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Relative paths of the theme's own assets. Kept in one place so the handles,
 * the filemtime versions and the editor styles can never drift apart.
 */
if ( ! defined( 'MAARS_THEME_CSS' ) ) {
	define( 'MAARS_THEME_CSS', 'assets/css/maars.css' );
}

if ( ! defined( 'MAARS_THEME_JS' ) ) {
	define( 'MAARS_THEME_JS', 'assets/js/skywave.js' );
}

/**
 * Public URI for a theme-relative asset, child-theme aware.
 *
 * @param string $rel Theme-relative path, e.g. 'assets/js/skywave.js'.
 * @return string Absolute URI. Empty string if $rel is empty.
 */
function maars_theme_asset_uri( string $rel ): string {
	$rel = ltrim( trim( $rel ), '/' );

	if ( '' === $rel ) {
		return '';
	}

	return get_theme_file_uri( $rel );
}

/**
 * Cache-busting version for a theme-relative asset.
 *
 * Uses the file's own mtime so a rebuilt image serves fresh CSS and JS without
 * anyone remembering to bump a number. Falls back to the theme version when the
 * file is missing, so a partial checkout cannot raise a filemtime() warning.
 *
 * @param string $rel Theme-relative path.
 * @return string Version string.
 */
function maars_theme_asset_version( string $rel ): string {
	$rel  = ltrim( trim( $rel ), '/' );
	$path = '' === $rel ? '' : get_theme_file_path( $rel );

	if ( '' !== $path && is_readable( $path ) ) {
		$mtime = filemtime( $path );

		if ( false !== $mtime ) {
			return (string) $mtime;
		}
	}

	return maars_theme_version();
}

/**
 * The theme's declared version, read from style.css.
 *
 * @return string Version string; '1.0.0' if the header cannot be read.
 */
function maars_theme_version(): string {
	static $version = null;

	if ( null !== $version ) {
		return $version;
	}

	$version = '1.0.0';

	if ( function_exists( 'wp_get_theme' ) ) {
		$declared = wp_get_theme( get_template() )->get( 'Version' );

		if ( is_string( $declared ) && '' !== $declared ) {
			$version = $declared;
		}
	}

	return $version;
}

/**
 * Theme supports and editor styles.
 *
 * @return void
 */
function maars_theme_setup(): void {
	load_theme_textdomain( 'maars', get_template_directory() . '/languages' );

	add_theme_support( 'automatic-feed-links' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'responsive-embeds' );
	add_theme_support( 'wp-block-styles' );
	add_theme_support( 'editor-styles' );
	add_theme_support(
		'html5',
		array(
			'caption',
			'comment-form',
			'comment-list',
			'gallery',
			'script',
			'search-form',
			'style',
		)
	);

	// The editor gets the same component styles and the same freshness chips as
	// the front end, so an editor can see a stale grade while writing.
	add_editor_style( MAARS_THEME_CSS );
}
add_action( 'after_setup_theme', 'maars_theme_setup' );

/**
 * Register the theme's script and stylesheet handles.
 *
 * Registered on `init` (not only on `wp_enqueue_scripts`) because the
 * server-rendered blocks in maars-core enqueue 'maars-skywave' from inside their
 * render callbacks, which run after the enqueue hooks have already fired.
 *
 * @return void
 */
function maars_theme_register_assets(): void {
	wp_register_style(
		'maars-maars',
		maars_theme_asset_uri( MAARS_THEME_CSS ),
		array(),
		maars_theme_asset_version( MAARS_THEME_CSS )
	);

	wp_register_style(
		'maars-style',
		get_stylesheet_uri(),
		array( 'maars-maars' ),
		maars_theme_asset_version( 'style.css' )
	);

	wp_register_script(
		'maars-skywave',
		maars_theme_asset_uri( MAARS_THEME_JS ),
		array(),
		maars_theme_asset_version( MAARS_THEME_JS ),
		array(
			'in_footer' => true,
			'strategy'  => 'defer',
		)
	);
}
add_action( 'init', 'maars_theme_register_assets', 20 );

/**
 * Enqueue the front-end assets.
 *
 * @return void
 */
function maars_theme_enqueue_assets(): void {
	wp_enqueue_style( 'maars-maars' );
	wp_enqueue_style( 'maars-style' );
	wp_enqueue_script( 'maars-skywave' );
}
add_action( 'wp_enqueue_scripts', 'maars_theme_enqueue_assets' );

/**
 * Two extra template-part areas, so the two honesty devices on this site are
 * editable in place rather than buried in a template.
 *
 * - dateline: the "when did the Society last do anything" banner.
 * - standing-facts: the grade-stamped cards (repeater, nets, meeting, joining).
 *
 * @param array<int, array<string, string>> $areas Registered areas.
 * @return array<int, array<string, string>> Areas with the MAARS additions.
 */
function maars_theme_template_part_areas( $areas ): array {
	if ( ! is_array( $areas ) ) {
		$areas = array();
	}

	$areas[] = array(
		'area'        => 'dateline',
		'area_tag'    => 'section',
		'label'       => __( 'Dateline', 'maars' ),
		'description' => __( 'States when the Society last published anything, and how long ago that was. Turns red past 120 days.', 'maars' ),
		'icon'        => 'layout',
	);

	$areas[] = array(
		'area'        => 'standing-facts',
		'area_tag'    => 'section',
		'label'       => __( 'Standing facts', 'maars' ),
		'description' => __( 'Facts a visitor can act on — meeting, repeater, nets — each carrying its own freshness grade and the date a human last checked it.', 'maars' ),
		'icon'        => 'layout',
	);

	return $areas;
}
add_filter( 'default_wp_template_part_areas', 'maars_theme_template_part_areas' );

/**
 * Tell the browser the theme ships both colour schemes, so form controls,
 * scrollbars and the address bar follow the page instead of fighting it.
 *
 * @return void
 */
function maars_theme_color_scheme_meta(): void {
	echo '<meta name="color-scheme" content="light dark">' . "\n";
}
add_action( 'wp_head', 'maars_theme_color_scheme_meta', 1 );
