<?php
/**
 * Post types for the MAARS content model.
 *
 * Three types, and one of them is deliberately not published:
 *
 *   maars_publication  public   /archive/{year}/   the 209 newsletters and minutes,
 *                                                  49 treasurer's reports, 6 year-end reports.
 *   maars_person       NOT public                  see the note below.
 *   maars_facility     public   /on-the-air/       repeaters and nets.
 *
 * WHY maars_person IS 'public' => false
 * -------------------------------------
 * This post type describes real, mostly living amateur operators: officers,
 * members, contributors, and the people named inside the archive. Putting a
 * roster of real people on the open web is a decision that belongs to the
 * Society under its Constitution and SOP, and the Society has not made it.
 * Nobody voted for it, so the code does not do it.
 *
 * So the type is registered with 'public' => false and 'show_ui' => true: the
 * records exist, they can be edited and linked from the admin, they can carry
 * relationships used to build public pages ("minutes taken by the Secretary"),
 * but there is no front-end URL, no archive, no search hit, and no sitemap
 * entry. The seed ships zero maars_person posts for the same reason.
 *
 * If the membership later votes to publish a roster, the flip is two lines
 * (see the parked 'public' / 'rewrite' values on the registration below) plus
 * a per-record consent field. It is intentionally a deliberate act, not a
 * default.
 *
 * @package MAARS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Register the MAARS post types.
 *
 * Hooked to `init` at priority 5 so the model exists before meta (priority 6)
 * and blocks (priority 10) are registered against it.
 *
 * @return void
 */
function maars_register_post_types() {

	/*
	 * maars_publication — the archive.
	 *
	 * Permalink is /archive/{year}/{slug}/. The %maars_year% token is expanded
	 * by maars_publication_permalink() below; the rewrite tag itself is created
	 * by register_taxonomy( 'maars_year' ) in inc/taxonomies.php.
	 *
	 * has_archive is the literal string 'archive' rather than true, so the list
	 * view stays at /archive/ instead of inheriting the year-bearing slug.
	 */
	register_post_type(
		'maars_publication',
		array(
			'labels'             => array(
				'name'                     => _x( 'Publications', 'post type general name', 'maars' ),
				'singular_name'            => _x( 'Publication', 'post type singular name', 'maars' ),
				'menu_name'                => _x( 'Archive', 'admin menu', 'maars' ),
				'name_admin_bar'           => _x( 'Publication', 'add new on admin bar', 'maars' ),
				'add_new'                  => __( 'Add Publication', 'maars' ),
				'add_new_item'             => __( 'Add New Publication', 'maars' ),
				'edit_item'                => __( 'Edit Publication', 'maars' ),
				'new_item'                 => __( 'New Publication', 'maars' ),
				'view_item'                => __( 'View Publication', 'maars' ),
				'view_items'               => __( 'View Publications', 'maars' ),
				'search_items'             => __( 'Search Publications', 'maars' ),
				'not_found'                => __( 'No publications found.', 'maars' ),
				'not_found_in_trash'       => __( 'No publications found in Trash.', 'maars' ),
				'all_items'                => __( 'All Publications', 'maars' ),
				'archives'                 => __( 'Publication Archive', 'maars' ),
				'attributes'               => __( 'Publication Attributes', 'maars' ),
				'insert_into_item'         => __( 'Insert into publication', 'maars' ),
				'uploaded_to_this_item'    => __( 'Uploaded to this publication', 'maars' ),
				'filter_items_list'        => __( 'Filter publications list', 'maars' ),
				'items_list_navigation'    => __( 'Publications list navigation', 'maars' ),
				'items_list'               => __( 'Publications list', 'maars' ),
				'item_published'           => __( 'Publication published.', 'maars' ),
				'item_updated'             => __( 'Publication updated.', 'maars' ),
				'item_link'                => _x( 'Publication Link', 'navigation link block title', 'maars' ),
				'item_link_description'    => _x( 'A link to a publication.', 'navigation link block description', 'maars' ),
			),
			'description'        => __( 'Newsletters, meeting minutes, treasurer\'s reports and year-end reports, 1998 onward.', 'maars' ),
			'public'             => true,
			'publicly_queryable' => true,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => true,
			'show_in_admin_bar'  => true,
			'show_in_rest'       => true,
			'menu_position'      => 20,
			'menu_icon'          => 'dashicons-media-document',
			'capability_type'    => 'post',
			'map_meta_cap'       => true,
			'hierarchical'       => false,
			'supports'           => array( 'title', 'editor', 'excerpt', 'revisions', 'custom-fields', 'thumbnail' ),
			'taxonomies'         => array( 'maars_doc_type', 'maars_year', 'maars_callsign' ),
			'has_archive'        => 'archive',
			'rewrite'            => array(
				'slug'       => 'archive/%maars_year%',
				'with_front' => false,
				'feeds'      => true,
				'pages'      => true,
			),
			'query_var'          => true,
			'delete_with_user'   => false,
		)
	);

	/*
	 * maars_person — see the WHY note at the top of this file.
	 *
	 * Parked values for the day the Society votes to publish a roster:
	 *     'public'  => true,
	 *     'rewrite' => array( 'slug' => 'people', 'with_front' => false ),
	 * Until then: no URL, no archive, no search, no sitemap. Admin only.
	 *
	 * show_in_rest stays true because the importer writes these records over
	 * the REST API; REST still enforces edit_posts, so nothing is readable by
	 * an anonymous request.
	 */
	register_post_type(
		'maars_person',
		array(
			'labels'              => array(
				'name'                  => _x( 'People', 'post type general name', 'maars' ),
				'singular_name'         => _x( 'Person', 'post type singular name', 'maars' ),
				'menu_name'             => _x( 'People (not published)', 'admin menu', 'maars' ),
				'name_admin_bar'        => _x( 'Person', 'add new on admin bar', 'maars' ),
				'add_new'               => __( 'Add Person', 'maars' ),
				'add_new_item'          => __( 'Add New Person', 'maars' ),
				'edit_item'             => __( 'Edit Person', 'maars' ),
				'new_item'              => __( 'New Person', 'maars' ),
				'view_item'             => __( 'View Person', 'maars' ),
				'search_items'          => __( 'Search People', 'maars' ),
				'not_found'             => __( 'No people found.', 'maars' ),
				'not_found_in_trash'    => __( 'No people found in Trash.', 'maars' ),
				'all_items'             => __( 'All People', 'maars' ),
				'filter_items_list'     => __( 'Filter people list', 'maars' ),
				'items_list_navigation' => __( 'People list navigation', 'maars' ),
				'items_list'            => __( 'People list', 'maars' ),
				'item_updated'          => __( 'Person updated.', 'maars' ),
			),
			'description'         => __( 'Records describing real, mostly living operators. Held in the admin only: publishing a roster is a decision for the membership, and it has not been made.', 'maars' ),
			'public'              => false,
			'publicly_queryable'  => false,
			'exclude_from_search' => true,
			'show_ui'             => true,
			'show_in_menu'        => true,
			'show_in_nav_menus'   => false,
			'show_in_admin_bar'   => false,
			'show_in_rest'        => true,
			'menu_position'       => 21,
			'menu_icon'           => 'dashicons-groups',
			'capability_type'     => 'post',
			'map_meta_cap'        => true,
			'hierarchical'        => false,
			'supports'            => array( 'title', 'editor', 'revisions', 'custom-fields' ),
			'taxonomies'          => array( 'maars_callsign' ),
			'has_archive'         => false,
			'rewrite'             => false,
			'query_var'           => false,
			'can_export'          => true,
			'delete_with_user'    => false,
		)
	);

	/*
	 * maars_facility — repeaters and nets: the things you can actually work.
	 *
	 * Everything here is a technical claim that goes stale (a repeater moves
	 * sites, a controller gets voted out), so every record is expected to carry
	 * _maars_grade and _maars_verified_on and to render with a freshness chip.
	 */
	register_post_type(
		'maars_facility',
		array(
			'labels'             => array(
				'name'                  => _x( 'Facilities', 'post type general name', 'maars' ),
				'singular_name'         => _x( 'Facility', 'post type singular name', 'maars' ),
				'menu_name'             => _x( 'On The Air', 'admin menu', 'maars' ),
				'name_admin_bar'        => _x( 'Facility', 'add new on admin bar', 'maars' ),
				'add_new'               => __( 'Add Facility', 'maars' ),
				'add_new_item'          => __( 'Add New Facility', 'maars' ),
				'edit_item'             => __( 'Edit Facility', 'maars' ),
				'new_item'              => __( 'New Facility', 'maars' ),
				'view_item'             => __( 'View Facility', 'maars' ),
				'view_items'            => __( 'View Facilities', 'maars' ),
				'search_items'          => __( 'Search Facilities', 'maars' ),
				'not_found'             => __( 'No facilities found.', 'maars' ),
				'not_found_in_trash'    => __( 'No facilities found in Trash.', 'maars' ),
				'all_items'             => __( 'All Facilities', 'maars' ),
				'archives'              => __( 'On The Air', 'maars' ),
				'filter_items_list'     => __( 'Filter facilities list', 'maars' ),
				'items_list_navigation' => __( 'Facilities list navigation', 'maars' ),
				'items_list'            => __( 'Facilities list', 'maars' ),
				'item_published'        => __( 'Facility published.', 'maars' ),
				'item_updated'          => __( 'Facility updated.', 'maars' ),
			),
			'description'        => __( 'Repeaters and on-air nets. Every technical detail here carries a freshness grade, because a frequency that is quietly wrong is worse than no frequency at all.', 'maars' ),
			'public'             => true,
			'publicly_queryable' => true,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => true,
			'show_in_admin_bar'  => true,
			'show_in_rest'       => true,
			'menu_position'      => 22,
			'menu_icon'          => 'dashicons-admin-site-alt3',
			'capability_type'    => 'post',
			'map_meta_cap'       => true,
			'hierarchical'       => false,
			'supports'           => array( 'title', 'editor', 'excerpt', 'revisions', 'custom-fields' ),
			'taxonomies'         => array( 'maars_facility_kind', 'maars_callsign' ),
			'has_archive'        => 'on-the-air',
			'rewrite'            => array(
				'slug'       => 'on-the-air',
				'with_front' => false,
				'feeds'      => false,
				'pages'      => false,
			),
			'query_var'          => true,
			'delete_with_user'   => false,
		)
	);
}
add_action( 'init', 'maars_register_post_types', 5 );

/**
 * Expand the %maars_year% token in publication permalinks.
 *
 * WordPress builds the rule set for a taxonomy token in a post type slug, but
 * it does not build the outgoing link: without this filter every publication
 * URL would read /archive/%maars_year%/spring-1998-newsletter/.
 *
 * Resolution order, most trustworthy first:
 *   1. the maars_year term (lowest year wins, so a document filed under two
 *      years still gets one stable URL),
 *   2. the year inside the _maars_doc_date meta (the date printed on the
 *      document itself),
 *   3. the post date,
 *   4. 'undated' — an honest placeholder, never a guess.
 *
 * @param string  $permalink The post URL, possibly containing %maars_year%.
 * @param WP_Post $post      The post being linked.
 * @return string
 */
function maars_publication_permalink( $permalink, $post ) {
	if ( ! $post instanceof WP_Post || 'maars_publication' !== $post->post_type ) {
		return $permalink;
	}

	if ( ! is_string( $permalink ) || false === strpos( $permalink, '%maars_year%' ) ) {
		return $permalink;
	}

	$year = '';

	$terms = get_the_terms( $post, 'maars_year' );
	if ( is_array( $terms ) && $terms ) {
		$slugs = wp_list_pluck( $terms, 'slug' );
		sort( $slugs, SORT_STRING );
		$year = (string) reset( $slugs );
	}

	if ( '' === $year ) {
		$doc_date = get_post_meta( $post->ID, '_maars_doc_date', true );
		if ( is_string( $doc_date ) && preg_match( '/^(\d{4})/', $doc_date, $matches ) ) {
			$year = $matches[1];
		}
	}

	if ( '' === $year ) {
		$post_year = get_post_time( 'Y', false, $post );
		if ( is_string( $post_year ) && '' !== $post_year ) {
			$year = $post_year;
		}
	}

	if ( '' === $year ) {
		$year = 'undated';
	}

	return str_replace( '%maars_year%', sanitize_title( $year ), $permalink );
}
add_filter( 'post_type_link', 'maars_publication_permalink', 10, 2 );

/**
 * Slug of the page that says what the archive does not hold.
 *
 * It lives at /archive/gaps/, beside the record it is about, which takes an
 * explicit rule: the maars_year taxonomy owns /archive/<anything>/, so without
 * this WordPress reads "gaps" as a year, finds no such term and returns 404 --
 * which is precisely what the archive's own "what we know is missing" link did
 * from the day it was written.
 */
const MAARS_GAPS_PAGE_SLUG = 'archive-gaps';

/**
 * Route /archive/gaps/ to the gaps page.
 *
 * Registered 'top' so it is tested before the taxonomy rule, and anchored at
 * both ends so it can match nothing else.
 *
 * @return void
 */
function maars_register_gaps_route() {
	add_rewrite_rule(
		'^archive/gaps/?$',
		'index.php?pagename=' . MAARS_GAPS_PAGE_SLUG,
		'top'
	);
}
add_action( 'init', 'maars_register_gaps_route', 6 );

/**
 * Flush the rewrite rules once, after a deploy that changes them.
 *
 * Activation-time flushing is not enough here: updating a plugin's files on a
 * live site does not re-run activation, so a new rule would sit in the rule
 * array unwritten and the URL would keep 404ing. The stamp makes the flush
 * happen exactly once per rule change -- bump MAARS_REWRITE_VERSION whenever a
 * rewrite rule in this plugin changes, and never otherwise, because flushing on
 * every request is a documented way to make a site slow.
 *
 * @return void
 */
function maars_maybe_flush_rewrites() {
	if ( ! function_exists( 'get_option' ) ) {
		return;
	}

	if ( (string) get_option( 'maars_rewrite_version', '' ) === (string) MAARS_REWRITE_VERSION ) {
		return;
	}

	flush_rewrite_rules( false );
	update_option( 'maars_rewrite_version', (string) MAARS_REWRITE_VERSION );
}
add_action( 'init', 'maars_maybe_flush_rewrites', 99 );
