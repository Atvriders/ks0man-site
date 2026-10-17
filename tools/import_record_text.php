<?php
/**
 * MAARS — give the archive records made from PDF and Word files their text.
 *
 * Run by WP-CLI from the entrypoint, after tools/import_media.php has made the
 * records:
 *     wp eval-file /usr/src/maars/tools/import_record_text.php
 *
 * content/record_text.json (tools/prepare_record_text.py) holds the machine-read
 * text of 142 records: the minutes from 2013 on, every treasurer's and year-end
 * report, and the 2009-2010 newsletters. Without it those records were a title,
 * a date and a link, and the archive's search could not find a word inside
 * them.
 *
 * A record is found by the source file it was made from, under either of the
 * two places a file came from. Idempotent: text that is already there is left
 * alone, and a better reading replaces an older one.
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	return;
}

$maars_text_json = getenv( 'MAARS_RECORD_TEXT' );
if ( ! is_string( $maars_text_json ) || '' === $maars_text_json ) {
	$maars_text_json = '/usr/src/maars/content/record_text.json';
}

if ( ! file_exists( $maars_text_json ) ) {
	WP_CLI::warning( 'no record text at ' . $maars_text_json . '; nothing to import' );
	return;
}

$maars_bundle = json_decode( (string) file_get_contents( $maars_text_json ), true );
if ( ! is_array( $maars_bundle ) || empty( $maars_bundle['records'] ) ) {
	WP_CLI::warning( 'the record text file holds no records; nothing to import' );
	return;
}

$maars_updated = 0;
$maars_kept    = 0;
$maars_absent  = 0;

foreach ( $maars_bundle['records'] as $maars_item ) {
	if ( ! is_array( $maars_item ) || empty( $maars_item['src'] ) || ! isset( $maars_item['blocks'] ) ) {
		continue;
	}
	$maars_src = basename( (string) $maars_item['src'] );

	$maars_found = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'no_found_rows'  => true,
			'meta_query'     => array(
				array(
					'key'     => '_maars_source_file',
					'value'   => array( 'mirror/ks0man.com/' . $maars_src, 'webmaster-folder/' . $maars_src ),
					'compare' => 'IN',
				),
			),
		)
	);
	if ( ! $maars_found ) {
		++$maars_absent;
		continue;
	}

	$maars_id = (int) $maars_found[0];
	if ( (string) get_post_field( 'post_content', $maars_id ) === (string) $maars_item['blocks'] ) {
		++$maars_kept;
		continue;
	}

	$maars_result = wp_update_post(
		wp_slash(
			array(
				'ID'           => $maars_id,
				'post_content' => (string) $maars_item['blocks'],
			)
		),
		true
	);
	if ( is_wp_error( $maars_result ) ) {
		WP_CLI::warning( $maars_src . ': ' . $maars_result->get_error_message() );
		continue;
	}
	++$maars_updated;
}

WP_CLI::success(
	sprintf(
		'record text: %d updated, %d unchanged, %d with no record on this site',
		$maars_updated,
		$maars_kept,
		$maars_absent
	)
);
