<?php
/**
 * MAARS — import the club's archive media into the WordPress media library.
 *
 * Run by WP-CLI from the entrypoint, after tools/seed.php and before
 * tools/seed_pages.php:
 *     wp eval-file /usr/src/maars/tools/import_media.php
 *
 * WHAT THIS IMPORTS, AND WHAT IT DOES NOT.
 * The Society's own record, in full, by its decision of 17 September 2026 --
 * including the 25 documents that carry officer contact details and the 18
 * Silent Key portraits. All of it stood on ks0man.com for years; the migration
 * is continuity, not new exposure. What is NOT here:
 *   - 14 third-party documents (a 1951 QST article, an ARRL band chart, a
 *     Kansas History paper, "Carl and Jerry", a US Army manual and others),
 *     because redistribution is not the Society's to grant. Five items that
 *     were on this list turned out to be the club's own work and now ship;
 *     see tools/screen_media.py, which reads each one rather than its name;
 *   - two Field Day videos, 66.7 MB, which belong on a video host;
 *   - 24 pieces of 1997 site furniture (spacers, arrows, a "get Acrobat" badge)
 *     are deliberately dropped rather than migrated.
 *
 * Idempotent: an attachment is keyed on _maars_media_src, so re-running on every
 * container boot changes nothing. That matters because the entrypoint runs on
 * every boot and a media library that grows by 179 items each time would be a
 * slow, silent disaster.
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	return;
}

/* The in-image location, overridable so this can be run against a local
   WordPress for testing. Hardcoding it meant the importer could only ever be
   exercised inside the container, which is how it shipped twice without once
   being run. */
$maars_media_dir = getenv( 'MAARS_MEDIA_DIR' );
if ( ! is_string( $maars_media_dir ) || '' === $maars_media_dir ) {
	$maars_media_dir = '/usr/src/maars/media';
}
$maars_media_dir = rtrim( $maars_media_dir, '/' );
$maars_manifest  = $maars_media_dir . '/manifest.json';

if ( ! file_exists( $maars_manifest ) ) {
	WP_CLI::warning( 'no media manifest at ' . $maars_manifest . '; nothing to import' );
	return;
}

$maars_items = json_decode( (string) file_get_contents( $maars_manifest ), true );
if ( ! is_array( $maars_items ) ) {
	WP_CLI::warning( 'media manifest is not valid JSON; nothing imported' );
	return;
}

require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

/**
 * Find an attachment already imported from this source file.
 *
 * @param string $src Original archive filename.
 * @return int Attachment ID, or 0.
 */
function maars_media_existing( $src ) {
	$found = get_posts(
		array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => '_maars_media_src',
			'meta_value'     => $src,
		)
	);
	return $found ? (int) $found[0] : 0;
}

/**
 * A readable title from an archive filename.
 *
 * @param string $src Archive filename.
 * @return string
 */
function maars_media_title( $src ) {
	$base = preg_replace( '/\.[A-Za-z0-9]+$/', '', $src );
	$base = str_replace( array( '_', '-' ), ' ', (string) $base );
	$base = preg_replace( '/\s+/', ' ', $base );
	return trim( (string) $base );
}


/**
 * Create the archive record a document belongs to, and attach the file to it.
 *
 * Idempotent on _maars_source_file: the entrypoint runs this on every boot.
 *
 * @param array  $item Manifest entry, carrying title, date, doc_type and year.
 * @param int    $att  Attachment ID of the imported PDF.
 * @param string $src  Original archive filename.
 * @return void
 */
function maars_media_publication( array $item, $att, $src ) {
	$existing = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => '_maars_source_file',
			'meta_value'     => $src,
		)
	);
	if ( $existing ) {
		return;
	}

	$date = (string) $item['date'];
	$post = wp_insert_post(
		array(
			'post_type'    => 'maars_publication',
			'post_status'  => 'publish',
			'post_title'   => (string) $item['title'],
			'post_date'    => $date . ' 09:00:00',
			'post_content' => '',
		),
		true
	);
	if ( is_wp_error( $post ) ) {
		WP_CLI::warning( $src . ': ' . $post->get_error_message() );
		return;
	}

	update_post_meta( $post, '_maars_source_file', $src );
	update_post_meta( $post, '_maars_doc_date', $date );
	update_post_meta( $post, '_maars_grade', 'sourced' );
	update_post_meta( $post, '_maars_attachment', (int) $att );

	if ( ! empty( $item['doc_type'] ) ) {
		wp_set_object_terms( $post, (string) $item['doc_type'], 'maars_doc_type', false );
	}
	if ( ! empty( $item['year'] ) ) {
		wp_set_object_terms( $post, (string) $item['year'], 'maars_year', false );
	}

	/* Re-parent the file so the document and its record are one thing. */
	wp_update_post( array( 'ID' => (int) $att, 'post_parent' => (int) $post ) );
}

$maars_added   = 0;
$maars_skipped = 0;
$maars_failed  = 0;

foreach ( $maars_items as $maars_item ) {
	$src  = isset( $maars_item['src'] ) ? (string) $maars_item['src'] : '';
	$file = isset( $maars_item['file'] ) ? (string) $maars_item['file'] : '';
	$kind = isset( $maars_item['kind'] ) ? (string) $maars_item['kind'] : 'document';
	if ( '' === $src || '' === $file ) {
		continue;
	}

	$already = maars_media_existing( $src );
	if ( $already ) {
		/* Backfill the name the file shipped under. It is what a page token
		   carries, and an attachment imported before this meta existed cannot
		   be found by it -- which withheld the downloads page from a site that
		   had the files in its library all along. */
		if ( '' === (string) get_post_meta( (int) $already, '_maars_media_file', true ) ) {
			update_post_meta( (int) $already, '_maars_media_file', $file );
		}
		++$maars_skipped;
		continue;
	}

	$path = $maars_media_dir . ( 'image' === $kind ? '/images/' : '/documents/' ) . $file;
	if ( ! file_exists( $path ) ) {
		WP_CLI::warning( 'missing from the image: ' . $path );
		++$maars_failed;
		continue;
	}

	/* Copy to a temp file: media_handle_sideload MOVES what it is given, and the
	   source lives in a read-only layer that every boot depends on. */
	$tmp = wp_tempnam( $file );
	if ( ! $tmp || ! copy( $path, $tmp ) ) {
		WP_CLI::warning( 'could not stage ' . $file );
		++$maars_failed;
		continue;
	}

	$id = media_handle_sideload(
		array(
			'name'     => $file,
			'tmp_name' => $tmp,
		),
		0,
		null,
		array(
			/* Alt text is required, not optional: the site this replaces had
			   1,154 images without it. The archive filename is a poor
			   description, so it is a starting point a human is expected to
			   improve, never a finished caption. */
			'post_title'   => maars_media_title( $src ),
			'post_excerpt' => '',
		)
	);

	if ( is_wp_error( $id ) ) {
		if ( file_exists( $tmp ) ) {
			@unlink( $tmp ); // phpcs:ignore
		}
		WP_CLI::warning( $file . ': ' . $id->get_error_message() );
		++$maars_failed;
		continue;
	}

	update_post_meta( $id, '_maars_media_src', $src );
	/* The name the file ships under, which is NOT the name WordPress stores:
	   a large image is saved as <name>-scaled.jpg, and the attachment slug
	   comes from the title, which comes from the ORIGINAL name on ks0man.com.
	   Page tokens use the shipped name, so it is recorded here to be found by. */
	update_post_meta( $id, '_maars_media_file', $file );
	update_post_meta( $id, '_maars_grade', 'sourced' );
	if ( 'image' === $kind ) {
		update_post_meta( $id, '_wp_attachment_image_alt', maars_media_title( $src ) );
	}

	/*
	 * A DOCUMENT IS NOT JUST A FILE IN THE LIBRARY, IT IS A RECORD IN THE
	 * ARCHIVE. The archive template lists maars_publication posts, so importing
	 * 123 PDFs as bare attachments left it showing the four seeded stubs and
	 * nothing else -- every file present, none of it findable. Each classified
	 * document now gets a publication post carrying its title, its date, its
	 * type and its year, with the PDF attached to it.
	 */
	if ( 'document' === $kind && ! empty( $maars_item['title'] ) && ! empty( $maars_item['date'] ) ) {
		maars_media_publication( $maars_item, $id, $src );
	}
	++$maars_added;
}


WP_CLI::success(
	sprintf(
		'media: %d imported, %d already present, %d failed',
		$maars_added,
		$maars_skipped,
		$maars_failed
	)
);
