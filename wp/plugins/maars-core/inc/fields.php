<?php
/**
 * MAARS Core — custom fields (post meta).
 *
 * Every meta key in the locked interface contract is registered here with
 * register_post_meta(): single, typed, exposed in REST, sanitized on write,
 * and gated by an auth_callback that requires the `edit_posts` capability.
 *
 * These keys are underscore-prefixed, i.e. WordPress treats them as protected
 * meta. Protected meta is invisible to the REST API unless an auth_callback
 * says otherwise, so the callback below is what makes the block editor and the
 * seed importer able to read and write them at all.
 *
 * Sanitizing matters more than usual here: `_maars_grade` and
 * `_maars_verified_on` are what the freshness machinery reads to decide
 * whether a fact is shown as measured, sourced, or unverified. A malformed
 * date must degrade to "we do not know when this was checked" — never to a
 * date that quietly reads as fresh.
 *
 * @package MAARS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Which meta keys belong to which post type.
 *
 * Three keys are universal provenance — grade, when it was last verified, and
 * which file in the club's own archive it came from. Document dates belong to
 * things that were published on a date. The RF keys belong to facilities
 * (repeaters and nets) only.
 *
 * @return array<string,string[]> Map of post type slug => list of meta keys.
 */
function maars_meta_registry() {
	$provenance = array(
		'_maars_verified_on',
		'_maars_grade',
		'_maars_source_file',
	);

	$registry = array(
		'post'              => array_merge( $provenance, array( '_maars_doc_date' ) ),
		'page'              => $provenance,
		'maars_publication' => array_merge( $provenance, array( '_maars_doc_date' ) ),
		'maars_person'      => $provenance,
		'maars_facility'    => array_merge(
			$provenance,
			array( '_maars_freq_mhz', '_maars_tone_hz', '_maars_offset', '_maars_schedule' )
		),
	);

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter the post type => meta key map before registration.
		 *
		 * @param array<string,string[]> $registry Map of post type slug => meta keys.
		 */
		$registry = (array) apply_filters( 'maars_meta_registry', $registry );
	}

	return $registry;
}

/**
 * Human-readable description and sanitizer for one meta key.
 *
 * @param string $key Meta key.
 * @return array{description:string,sanitize_callback:callable} Definition parts.
 */
function maars_meta_key_spec( $key ) {
	$specs = array(
		'_maars_verified_on' => array(
			'description'       => 'Date a human last checked this record against a source (YYYY-MM-DD).',
			'sanitize_callback' => 'maars_sanitize_date_meta',
		),
		'_maars_grade'       => array(
			'description'       => 'Evidence grade: measured, sourced, or unverified.',
			'sanitize_callback' => 'sanitize_text_field',
		),
		'_maars_source_file' => array(
			'description'       => 'Relative path of the archive file this record was derived from.',
			'sanitize_callback' => 'sanitize_text_field',
		),
		'_maars_doc_date'    => array(
			'description'       => 'Date the document itself carries, not the import date (YYYY-MM-DD).',
			'sanitize_callback' => 'maars_sanitize_date_meta',
		),
		'_maars_freq_mhz'    => array(
			'description'       => 'Output frequency in MHz as a plain numeric string, e.g. 147.255.',
			'sanitize_callback' => 'maars_sanitize_numeric_meta',
		),
		'_maars_tone_hz'     => array(
			'description'       => 'CTCSS access tone in Hz as a plain numeric string, e.g. 88.5.',
			'sanitize_callback' => 'maars_sanitize_numeric_meta',
		),
		'_maars_offset'      => array(
			'description'       => 'Repeater offset as written by the club, e.g. "+600 kHz".',
			'sanitize_callback' => 'sanitize_text_field',
		),
		'_maars_schedule'    => array(
			'description'       => 'When this net or facility is on the air, in plain words.',
			'sanitize_callback' => 'sanitize_text_field',
		),
	);

	if ( isset( $specs[ $key ] ) ) {
		return $specs[ $key ];
	}

	return array(
		'description'       => 'MAARS metadata.',
		'sanitize_callback' => 'sanitize_text_field',
	);
}

/**
 * Sanitize a date meta value down to a real calendar day in YYYY-MM-DD form.
 *
 * Anything that is not an existing date — wrong shape, 2024-13-01, 2023-02-30,
 * an array, a stray timestamp — becomes the empty string. Empty means
 * "unknown", which the freshness code reads as stale. A half-parsed date would
 * be worse than none.
 *
 * @param mixed $value Raw meta value.
 * @return string Valid YYYY-MM-DD date, or ''.
 */
function maars_sanitize_date_meta( $value ) {
	$value = is_scalar( $value ) ? trim( (string) $value ) : '';

	if ( '' === $value ) {
		return '';
	}

	if ( ! preg_match( '/^(\d{4})-(\d{2})-(\d{2})$/', $value, $m ) ) {
		return '';
	}

	if ( ! checkdate( (int) $m[2], (int) $m[3], (int) $m[1] ) ) {
		return '';
	}

	return $value;
}

/**
 * Sanitize a frequency-shaped meta value to an unsigned numeric string.
 *
 * Stored as a string, deliberately: 147.255 and 88.5 are labels the club reads
 * off a radio, and floats would eventually print 147.25500000000001. Thousands
 * separators and spaces are stripped; anything left that is not digits with an
 * optional decimal part becomes ''.
 *
 * @param mixed $value Raw meta value.
 * @return string Numeric string, or ''.
 */
function maars_sanitize_numeric_meta( $value ) {
	$value = is_scalar( $value ) ? trim( (string) $value ) : '';

	if ( '' === $value ) {
		return '';
	}

	$value = str_replace( array( ',', ' ', "\xc2\xa0" ), '', $value );

	if ( ! preg_match( '/^\d{1,9}(\.\d{1,6})?$/', $value ) ) {
		return '';
	}

	return $value;
}

/**
 * Authorization for reading and writing MAARS protected meta over REST.
 *
 * Requires the edit_posts capability at minimum, and the per-post edit
 * capability when a post is in play. Subscribers and anonymous REST callers
 * get nothing.
 *
 * @param bool   $allowed  Whether the user can add or edit the meta. Unused; recomputed.
 * @param string $meta_key Meta key being checked.
 * @param int    $post_id  Post ID, 0 when the check is not post-specific.
 * @param int    $user_id  User ID.
 * @param string $cap      Capability being checked.
 * @param array  $caps     Primitive capabilities required.
 * @return bool True when the current user may touch this meta.
 */
function maars_meta_auth_callback( $allowed = false, $meta_key = '', $post_id = 0, $user_id = 0, $cap = '', $caps = array() ) {
	if ( ! function_exists( 'current_user_can' ) ) {
		return false;
	}

	$post_id = (int) $post_id;

	if ( $post_id > 0 && current_user_can( 'edit_post', $post_id ) ) {
		return true;
	}

	return (bool) current_user_can( 'edit_posts' );
}

/**
 * Register every MAARS meta key against every post type that uses it.
 *
 * Hooked to `init` at priority 6 — after post types and taxonomies register at
 * priority 5, before blocks at priority 10, because a block's render_callback
 * has no business reading a meta key that has not been declared yet.
 *
 * @return void
 */
function maars_register_meta() {
	if ( ! function_exists( 'register_post_meta' ) ) {
		return;
	}

	foreach ( maars_meta_registry() as $post_type => $keys ) {
		foreach ( array_unique( (array) $keys ) as $key ) {
			$spec = maars_meta_key_spec( $key );

			register_post_meta(
				$post_type,
				$key,
				array(
					'type'              => 'string',
					'description'       => $spec['description'],
					'single'            => true,
					'default'           => '',
					'show_in_rest'      => true,
					'sanitize_callback' => $spec['sanitize_callback'],
					'auth_callback'     => 'maars_meta_auth_callback',
				)
			);
		}
	}
}

if ( function_exists( 'add_action' ) ) {
	add_action( 'init', 'maars_register_meta', 6 );
}
