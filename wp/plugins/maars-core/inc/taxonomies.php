<?php
/**
 * Taxonomies for the MAARS content model.
 *
 *   maars_doc_type       hierarchical   what a publication IS (newsletter, minutes,
 *                                       treasurer's report, year-end report).
 *   maars_year           flat           the year a document belongs to; it is also the
 *                                       %maars_year% segment of /archive/{year}/.
 *   maars_callsign       NOT public     see the note below.
 *   maars_facility_kind  flat           repeater or net.
 *
 * WHY maars_callsign IS 'public' => false
 * ---------------------------------------
 * A callsign is not a tag. It is a licence identifier that resolves, through
 * the FCC's public ULS database, to a real person's legal name and mailing
 * address. A public callsign archive would therefore quietly build a browsable
 * index of real, mostly living members and everything the archive says about
 * them: who moved, who was ill, who resigned, who was thanked, who was
 * memorialised. Nobody consented to that index, and the Society has never
 * voted to publish one.
 *
 * So the taxonomy is registered with 'public' => false and 'rewrite' => false:
 * editors can still file and filter by callsign inside the admin, which is what
 * makes the archive searchable for the people maintaining it, but there is no
 * /callsign/ URL, no term archive, no sitemap entry and no anonymous REST read.
 *
 * The same reasoning governs maars_person in inc/post-types.php. Publishing
 * either one is a membership decision, not a default, and the constitution puts
 * that decision with the members present at a meeting.
 *
 * @package MAARS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Register the MAARS taxonomies.
 *
 * Hooked to `init` at priority 5, the same priority as the post types. The
 * plugin bootstrap loads this file FIRST so these run FIRST, for two concrete
 * reasons:
 *
 *   1. register_taxonomy( 'maars_year' ) is what creates the %maars_year%
 *      rewrite tag that the maars_publication permastruct
 *      (archive/%maars_year%/%postname%) is written against.
 *   2. Rewrite rules are emitted in permastruct registration order, so the
 *      taxonomy rules for /archive/type/newsletter/ and /archive/1998/ are
 *      matched before the two-segment publication rule that would otherwise
 *      swallow them.
 *
 * @return void
 */
function maars_register_taxonomies() {

	/*
	 * maars_doc_type — what a document is. Hierarchical because the club may
	 * later want, say, minutes > board meeting under an existing parent without
	 * re-filing the archive. The four seed terms are created on activation by
	 * maars_install_doc_type_terms().
	 */
	register_taxonomy(
		'maars_doc_type',
		array( 'maars_publication' ),
		array(
			'labels'             => array(
				'name'                       => _x( 'Document Types', 'taxonomy general name', 'maars' ),
				'singular_name'              => _x( 'Document Type', 'taxonomy singular name', 'maars' ),
				'menu_name'                  => __( 'Document Types', 'maars' ),
				'all_items'                  => __( 'All Document Types', 'maars' ),
				'parent_item'                => __( 'Parent Document Type', 'maars' ),
				'parent_item_colon'          => __( 'Parent Document Type:', 'maars' ),
				'edit_item'                  => __( 'Edit Document Type', 'maars' ),
				'view_item'                  => __( 'View Document Type', 'maars' ),
				'update_item'                => __( 'Update Document Type', 'maars' ),
				'add_new_item'               => __( 'Add New Document Type', 'maars' ),
				'new_item_name'              => __( 'New Document Type Name', 'maars' ),
				'search_items'               => __( 'Search Document Types', 'maars' ),
				'not_found'                  => __( 'No document types found.', 'maars' ),
				'no_terms'                   => __( 'No document types', 'maars' ),
				'back_to_items'              => __( '&larr; Go to Document Types', 'maars' ),
				'items_list_navigation'      => __( 'Document types list navigation', 'maars' ),
				'items_list'                 => __( 'Document types list', 'maars' ),
			),
			'description'        => __( 'What a publication is: newsletter, minutes, treasurer\'s report, year-end report.', 'maars' ),
			'hierarchical'       => true,
			'public'             => true,
			'publicly_queryable' => true,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => true,
			'show_in_rest'       => true,
			'show_admin_column'  => true,
			'show_tagcloud'      => false,
			'rewrite'            => array(
				'slug'         => 'archive/type',
				'with_front'   => false,
				'hierarchical' => false,
			),
			'query_var'          => true,
		)
	);

	/*
	 * maars_year — the year segment of an archive URL.
	 *
	 * The rewrite slug is 'archive' with no extra segment, so a term archive is
	 * /archive/1998/ — the same shape the publication permalink puts the year
	 * in. Term slugs are plain four-digit years. 2012 will legitimately have no
	 * term: the club produced nothing that year, and the archive should be able
	 * to say so rather than skip silently.
	 */
	register_taxonomy(
		'maars_year',
		array( 'maars_publication', 'post' ),
		array(
			'labels'             => array(
				'name'                  => _x( 'Years', 'taxonomy general name', 'maars' ),
				'singular_name'         => _x( 'Year', 'taxonomy singular name', 'maars' ),
				'menu_name'             => __( 'Years', 'maars' ),
				'all_items'             => __( 'All Years', 'maars' ),
				'edit_item'             => __( 'Edit Year', 'maars' ),
				'view_item'             => __( 'View Year', 'maars' ),
				'update_item'           => __( 'Update Year', 'maars' ),
				'add_new_item'          => __( 'Add New Year', 'maars' ),
				'new_item_name'         => __( 'New Year', 'maars' ),
				'search_items'          => __( 'Search Years', 'maars' ),
				'popular_items'         => __( 'Most Documented Years', 'maars' ),
				'separate_items_with_commas' => __( 'Separate years with commas', 'maars' ),
				'add_or_remove_items'   => __( 'Add or remove years', 'maars' ),
				'choose_from_most_used' => __( 'Choose from the most documented years', 'maars' ),
				'not_found'             => __( 'No years found.', 'maars' ),
				'no_terms'              => __( 'No years', 'maars' ),
				'back_to_items'         => __( '&larr; Go to Years', 'maars' ),
				'items_list_navigation' => __( 'Years list navigation', 'maars' ),
				'items_list'            => __( 'Years list', 'maars' ),
			),
			'description'        => __( 'The year a document belongs to. Also the year segment of its permalink.', 'maars' ),
			'hierarchical'       => false,
			'public'             => true,
			'publicly_queryable' => true,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => true,
			'show_in_rest'       => true,
			'show_admin_column'  => true,
			'show_tagcloud'      => false,
			'rewrite'            => array(
				'slug'       => 'archive',
				'with_front' => false,
			),
			'query_var'          => true,
		)
	);

	/*
	 * maars_callsign — see the WHY note at the top of this file.
	 *
	 * Parked values for the day the Society votes to publish:
	 *     'public'  => true,
	 *     'rewrite' => array( 'slug' => 'callsign', 'with_front' => false ),
	 *
	 * show_in_rest stays true so the importer can file terms over the REST API.
	 * With 'public' => false the REST route requires the assign/manage_terms
	 * capability, so an anonymous request sees nothing.
	 */
	register_taxonomy(
		'maars_callsign',
		array( 'post', 'page', 'maars_publication', 'maars_person', 'maars_facility' ),
		array(
			'labels'             => array(
				'name'                  => _x( 'Callsigns', 'taxonomy general name', 'maars' ),
				'singular_name'         => _x( 'Callsign', 'taxonomy singular name', 'maars' ),
				'menu_name'             => __( 'Callsigns (not published)', 'maars' ),
				'all_items'             => __( 'All Callsigns', 'maars' ),
				'edit_item'             => __( 'Edit Callsign', 'maars' ),
				'view_item'             => __( 'View Callsign', 'maars' ),
				'update_item'           => __( 'Update Callsign', 'maars' ),
				'add_new_item'          => __( 'Add New Callsign', 'maars' ),
				'new_item_name'         => __( 'New Callsign', 'maars' ),
				'search_items'          => __( 'Search Callsigns', 'maars' ),
				'separate_items_with_commas' => __( 'Separate callsigns with commas', 'maars' ),
				'add_or_remove_items'   => __( 'Add or remove callsigns', 'maars' ),
				'choose_from_most_used' => __( 'Choose from the most used callsigns', 'maars' ),
				'not_found'             => __( 'No callsigns found.', 'maars' ),
				'no_terms'              => __( 'No callsigns', 'maars' ),
				'back_to_items'         => __( '&larr; Go to Callsigns', 'maars' ),
				'items_list_navigation' => __( 'Callsigns list navigation', 'maars' ),
				'items_list'            => __( 'Callsigns list', 'maars' ),
			),
			'description'        => __( 'Admin-only index of callsigns mentioned in the archive. Not published: a callsign resolves to a real person, and no vote has been taken to put that index on the open web.', 'maars' ),
			'hierarchical'       => false,
			'public'             => false,
			'publicly_queryable' => false,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => false,
			'show_in_rest'       => true,
			'show_admin_column'  => true,
			'show_tagcloud'      => false,
			'rewrite'            => false,
			'query_var'          => false,
		)
	);

	/*
	 * maars_facility_kind — repeater or net. Kept as a taxonomy rather than a
	 * meta field so /on-the-air/kind/net/ is a real, linkable listing.
	 */
	register_taxonomy(
		'maars_facility_kind',
		array( 'maars_facility' ),
		array(
			'labels'             => array(
				'name'                  => _x( 'Facility Kinds', 'taxonomy general name', 'maars' ),
				'singular_name'         => _x( 'Facility Kind', 'taxonomy singular name', 'maars' ),
				'menu_name'             => __( 'Facility Kinds', 'maars' ),
				'all_items'             => __( 'All Facility Kinds', 'maars' ),
				'edit_item'             => __( 'Edit Facility Kind', 'maars' ),
				'view_item'             => __( 'View Facility Kind', 'maars' ),
				'update_item'           => __( 'Update Facility Kind', 'maars' ),
				'add_new_item'          => __( 'Add New Facility Kind', 'maars' ),
				'new_item_name'         => __( 'New Facility Kind', 'maars' ),
				'search_items'          => __( 'Search Facility Kinds', 'maars' ),
				'separate_items_with_commas' => __( 'Separate facility kinds with commas', 'maars' ),
				'add_or_remove_items'   => __( 'Add or remove facility kinds', 'maars' ),
				'choose_from_most_used' => __( 'Choose from the most used facility kinds', 'maars' ),
				'not_found'             => __( 'No facility kinds found.', 'maars' ),
				'no_terms'              => __( 'No facility kinds', 'maars' ),
				'back_to_items'         => __( '&larr; Go to Facility Kinds', 'maars' ),
				'items_list_navigation' => __( 'Facility kinds list navigation', 'maars' ),
				'items_list'            => __( 'Facility kinds list', 'maars' ),
			),
			'description'        => __( 'Repeater or net.', 'maars' ),
			'hierarchical'       => false,
			'public'             => true,
			'publicly_queryable' => true,
			'show_ui'            => true,
			'show_in_menu'       => true,
			'show_in_nav_menus'  => true,
			'show_in_rest'       => true,
			'show_admin_column'  => true,
			'show_tagcloud'      => false,
			'rewrite'            => array(
				'slug'       => 'on-the-air/kind',
				'with_front' => false,
			),
			'query_var'          => true,
		)
	);
}
add_action( 'init', 'maars_register_taxonomies', 5 );

/**
 * The fixed maars_doc_type vocabulary.
 *
 * Fixed on purpose. The archive has exactly four kinds of document in it, and a
 * free-text type field is how an archive ends up with "Minutes", "minutes",
 * "Meeting Minutes" and "MINUTES" as four different things.
 *
 * @return array<string, array{name: string, description: string}> Keyed by term slug.
 */
function maars_doc_type_terms() {
	return array(
		'newsletter'       => array(
			'name'        => __( 'Newsletter', 'maars' ),
			'description' => __( 'The Society newsletter, usually carrying the previous meeting\'s minutes inside it.', 'maars' ),
		),
		'minutes'          => array(
			'name'        => __( 'Minutes', 'maars' ),
			'description' => __( 'Minutes of a monthly meeting, including the motions made and their disposition.', 'maars' ),
		),
		'treasurer-report' => array(
			'name'        => __( 'Treasurer\'s Report', 'maars' ),
			'description' => __( 'A period financial report presented to the membership.', 'maars' ),
		),
		'year-end-report'  => array(
			'name'        => __( 'Year-End Report', 'maars' ),
			'description' => __( 'An annual summary of the Society\'s year.', 'maars' ),
		),
	);
}

/**
 * Create the four maars_doc_type terms.
 *
 * Called from the plugin activation hook. Idempotent: an existing term is left
 * exactly as the club edited it, so re-activating the plugin can never clobber
 * a renamed or re-described term.
 *
 * @return void
 */
function maars_install_doc_type_terms() {
	if ( ! taxonomy_exists( 'maars_doc_type' ) ) {
		if ( ! function_exists( 'maars_register_taxonomies' ) ) {
			return;
		}
		maars_register_taxonomies();
	}

	foreach ( maars_doc_type_terms() as $slug => $term ) {
		if ( term_exists( $slug, 'maars_doc_type' ) ) {
			continue;
		}

		wp_insert_term(
			$term['name'],
			'maars_doc_type',
			array(
				'slug'        => $slug,
				'description' => $term['description'],
			)
		);
	}
}
