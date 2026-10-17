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
/**
 * Where a document really came from: the old site as it was served, or the
 * webmaster's own folder. The fact chip on every record prints this.
 */
function maars_media_source_path( array $item, string $src ): string {
	$root = ( isset( $item['origin'] ) && 'webmaster-folder' === $item['origin'] ) ? 'webmaster-folder/' : 'mirror/ks0man.com/';
	return $root . $src;
}

function maars_media_publication( array $item, $att, $src ) {
	/* All three keys a record of this file can carry: the bare name the first
	   images wrote, and the two provenance paths written since. Checking one
	   of them would make a second record on the next boot. */
	$existing = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_query'     => array(
				'relation' => 'OR',
				array( 'key' => '_maars_source_file', 'value' => $src ),
				array( 'key' => '_maars_source_file', 'value' => 'mirror/ks0man.com/' . $src ),
				array( 'key' => '_maars_source_file', 'value' => 'webmaster-folder/' . $src ),
			),
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

	update_post_meta( $post, '_maars_source_file', maars_media_source_path( $item, $src ) );
	update_post_meta( $post, '_maars_doc_date', $date );
	update_post_meta( $post, '_maars_verified_on', '2026-10-17' );
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

/**
 * Hang an attachment off an existing record as the same document in another
 * format. The record is found by the source file it was made from.
 *
 * @param string $of Source file name of the record's own document, e.g. "newsletter_05-19.pdf".
 * @param int    $att Attachment ID to add.
 * @return void
 */
function maars_media_attach_alternate( string $of, int $att ) {
	$records = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_query'     => array(
				array(
					'key'     => '_maars_source_file',
					'value'   => $of,
					'compare' => 'LIKE',
				),
			),
		)
	);
	if ( ! $records ) {
		WP_CLI::warning( 'alternate format has no record to join: ' . $of );
		return;
	}

	$record = (int) $records[0];
	$list   = array_filter( explode( ',', (string) get_post_meta( $record, '_maars_alternates', true ) ) );
	if ( ! in_array( (string) $att, $list, true ) ) {
		$list[] = (string) $att;
		update_post_meta( $record, '_maars_alternates', implode( ',', $list ) );
	}
	wp_update_post( array( 'ID' => $att, 'post_parent' => $record ) );
}

/*
 * THE WEBMASTER'S SOURCE FILES. The folder ks0man.com was built from holds a
 * TrueType font, two Photoshop files, an InDesign document, a PageMaker file
 * and a plain-text order list, and the Society asked for every file in it.
 * WordPress's upload list refuses all six when this runs from WP-CLI, which has
 * no signed-in user and so no unfiltered_upload. The grant below is the
 * narrowest one that works: these extensions, these types, for the length of
 * this import, removed again at the end. Nothing a visitor can upload changes.
 */
$maars_source_types = array(
	'ttf'  => 'font/ttf',
	'psd'  => 'image/vnd.adobe.photoshop',
	'indd' => 'application/x-indesign',
	'pm'   => 'application/x-pagemaker',
	'txt'  => 'text/plain',
);
$maars_mimes_filter = static function ( $mimes ) use ( $maars_source_types ) {
	return array_merge( (array) $mimes, $maars_source_types );
};
$maars_check_filter = static function ( $data, $file, $filename ) use ( $maars_source_types ) {
	$ext = strtolower( pathinfo( (string) $filename, PATHINFO_EXTENSION ) );
	if ( isset( $maars_source_types[ $ext ] ) ) {
		return array(
			'ext'             => $ext,
			'type'            => $maars_source_types[ $ext ],
			'proper_filename' => false,
		);
	}
	return $data;
};
add_filter( 'upload_mimes', $maars_mimes_filter );
add_filter( 'wp_check_filetype_and_ext', $maars_check_filter, 10, 3 );

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

/*
 * RECORDS MATCH THE MANIFEST, on every boot. Records used to be made only in
 * the loop above, for files imported THIS boot -- so on a volume an earlier
 * image filled, twenty-one issues the manifest has since given a title stayed
 * bare attachments forever, and a correction to a title or a kind never
 * reached a record that already existed. This pass makes the record for any
 * titled document whose file is in the library, brings an existing record's
 * title, date, kind and year into line, and deletes the record of a file the
 * manifest marks as a copy of another.
 */
foreach ( $maars_items as $maars_item ) {
	$src = isset( $maars_item['src'] ) ? (string) $maars_item['src'] : '';
	if ( '' === $src ) {
		continue;
	}

	$records = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_query'     => array(
				'relation' => 'OR',
				array( 'key' => '_maars_source_file', 'value' => $src ),
				array( 'key' => '_maars_source_file', 'value' => 'mirror/ks0man.com/' . $src ),
				array( 'key' => '_maars_source_file', 'value' => 'webmaster-folder/' . $src ),
			),
		)
	);

	if ( ! empty( $maars_item['duplicate_of'] ) ) {
		if ( $records ) {
			wp_delete_post( (int) $records[0], true );
			WP_CLI::log( 'removed the record for ' . $src . ', a copy of ' . $maars_item['duplicate_of'] );
		}
		continue;
	}

	if ( empty( $maars_item['title'] ) || empty( $maars_item['date'] ) ) {
		continue;
	}

	$att = maars_media_existing( $src );
	if ( ! $records ) {
		if ( $att ) {
			maars_media_publication( $maars_item, $att, $src );
		}
		continue;
	}

	$record = (int) $records[0];
	$want   = array(
		'ID'         => $record,
		'post_title' => (string) $maars_item['title'],
		'post_date'  => (string) $maars_item['date'] . ' 09:00:00',
	);
	$post = get_post( $record );
	if ( $post && ( $post->post_title !== $want['post_title'] || substr( $post->post_date, 0, 10 ) !== (string) $maars_item['date'] ) ) {
		$want['post_name'] = sanitize_title( $want['post_title'] );
		wp_update_post( $want );
	}
	update_post_meta( $record, '_maars_doc_date', (string) $maars_item['date'] );
	update_post_meta( $record, '_maars_source_file', maars_media_source_path( $maars_item, $src ) );
	if ( '' === (string) get_post_meta( $record, '_maars_verified_on', true ) ) {
		update_post_meta( $record, '_maars_verified_on', '2026-10-17' );
	}
	if ( ! empty( $maars_item['doc_type'] ) ) {
		wp_set_object_terms( $record, (string) $maars_item['doc_type'], 'maars_doc_type', false );
	}
	if ( ! empty( $maars_item['year'] ) ) {
		wp_set_object_terms( $record, (string) $maars_item['year'], 'maars_year', false );
	}
	if ( $att && (int) get_post_meta( $record, '_maars_attachment', true ) !== (int) $att ) {
		update_post_meta( $record, '_maars_attachment', (int) $att );
	}
}

/*
 * The same document in another format -- the .docx the treasurer wrote before
 * printing the PDF -- belongs to the record the PDF made, not to a record of
 * its own. Two records for one report is a duplicate in the archive list; one
 * record with two files is the truth.
 *
 * A second pass, after every record exists. Joined inside the loop, an
 * alternate that sorts before its document ("newsletter-05-19.doc" before
 * "newsletter-05-19.pdf") arrived before the record it belongs to, found
 * nothing to join, and stayed loose; and a re-run never joined it, because the
 * loop skips what is already imported. This pass is idempotent and covers both.
 */
foreach ( $maars_items as $maars_item ) {
	if ( empty( $maars_item['alternate_of'] ) || empty( $maars_item['src'] ) ) {
		continue;
	}
	$att = maars_media_existing( (string) $maars_item['src'] );
	if ( $att ) {
		maars_media_attach_alternate( (string) $maars_item['alternate_of'], (int) $att );
	}
}


remove_filter( 'upload_mimes', $maars_mimes_filter );
remove_filter( 'wp_check_filetype_and_ext', $maars_check_filter, 10 );

WP_CLI::success(
	sprintf(
		'media: %d imported, %d already present, %d failed',
		$maars_added,
		$maars_skipped,
		$maars_failed
	)
);
