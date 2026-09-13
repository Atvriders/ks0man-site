<?php
/**
 * Plugin Name:       MAARS Core
 * Plugin URI:        https://ks0man.org/
 * Description:       Content model for the Manhattan Area Amateur Radio Society (KS0MAN): publications, people, facilities, freshness grading, and the server-rendered blocks that make staleness visible instead of hiding it.
 * Version:           0.1.0
 * Requires at least: 6.7
 * Requires PHP:      8.1
 * Author:            Manhattan Area Amateur Radio Society
 * License:           GPL-2.0-or-later
 * License URI:       https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain:       maars
 * Domain Path:       /languages
 *
 * Bootstrap only. No content model lives in this file: it defines the two
 * constants the rest of the plugin resolves paths with, loads each module in
 * inc/, and owns the activation / deactivation lifecycle.
 *
 * @package MAARS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Plugin version. Bumped by hand; used for asset cache-busting elsewhere.
 */
define( 'MAARS_CORE_VERSION', '0.1.0' );

/**
 * Absolute filesystem path to this plugin's directory, with a trailing slash.
 */
define( 'MAARS_CORE_DIR', plugin_dir_path( __FILE__ ) );

/*
 * Load order matters exactly once, and this is it: taxonomies.php is required
 * before post-types.php so that maars_register_taxonomies() is hooked to `init`
 * ahead of maars_register_post_types() at the same priority (5). Registering
 * maars_year first is what creates the %maars_year% rewrite tag the publication
 * permalink /archive/%maars_year%/%postname%/ is written against, and it puts
 * the taxonomy rewrite rules ahead of the two-segment publication rule that
 * would otherwise swallow /archive/type/newsletter/. Everything after this is
 * order-independent.
 */
require_once MAARS_CORE_DIR . 'inc/taxonomies.php';
require_once MAARS_CORE_DIR . 'inc/post-types.php';
require_once MAARS_CORE_DIR . 'inc/fields.php';
require_once MAARS_CORE_DIR . 'inc/freshness.php';
require_once MAARS_CORE_DIR . 'inc/blocks.php';

/**
 * Activation: register the content model once by hand, seed the fixed
 * vocabulary, then rebuild permalinks.
 *
 * Activation runs before `init` fires on this request, so the post types and
 * taxonomies do not exist yet. flush_rewrite_rules() would therefore write a
 * rule set with no /archive/ or /on-the-air/ in it. Registering first is what
 * makes the very first page load work without a manual Settings > Permalinks
 * save.
 *
 * @return void
 */
function maars_core_activate() {
	if ( function_exists( 'maars_register_taxonomies' ) ) {
		maars_register_taxonomies();
	}

	if ( function_exists( 'maars_register_post_types' ) ) {
		maars_register_post_types();
	}

	if ( function_exists( 'maars_install_doc_type_terms' ) ) {
		maars_install_doc_type_terms();
	}

	flush_rewrite_rules();
}
register_activation_hook( __FILE__, 'maars_core_activate' );

/**
 * Deactivation: drop this plugin's rewrite rules so a deactivated plugin does
 * not leave /archive/ and /on-the-air/ answering with stale 404s.
 *
 * Terms and posts are deliberately left alone. Deleting a club's archive
 * because someone toggled a checkbox is not a decision code gets to make.
 *
 * @return void
 */
function maars_core_deactivate() {
	flush_rewrite_rules();
}
register_deactivation_hook( __FILE__, 'maars_core_deactivate' );
