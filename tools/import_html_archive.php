<?php
/**
 * MAARS — import the issues from the years when the newsletter WAS the web page.
 *
 * Run by WP-CLI from the entrypoint, after tools/import_media.php and before
 * tools/seed_pages.php (the carried-over pages link to these issues by token):
 *     wp eval-file /usr/src/maars/tools/import_html_archive.php
 *
 * content/html_archive.json holds 125 issues, 1998 to 2015, converted from the
 * old site's HTML by tools/prepare_html_archive.py. Production received them
 * through a one-off REST script that lived in /tmp and did not survive a tmp
 * cleaner, and nothing in the image imported them at all -- so `docker compose
 * up` produced an archive that started in 2009 while the live site started in
 * 1998. This is the image's half of that import, kept in the repository.
 *
 * Idempotent: an issue is keyed on _maars_source_file, so re-running on every
 * boot changes nothing.
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	return;
}

$maars_html_json = getenv( 'MAARS_HTML_ARCHIVE' );
if ( ! is_string( $maars_html_json ) || '' === $maars_html_json ) {
	$maars_html_json = '/usr/src/maars/content/html_archive.json';
}

if ( ! file_exists( $maars_html_json ) ) {
	WP_CLI::warning( 'no HTML-era archive at ' . $maars_html_json . '; nothing to import' );
	return;
}

$maars_issues = json_decode( (string) file_get_contents( $maars_html_json ), true );
if ( ! is_array( $maars_issues ) ) {
	WP_CLI::warning( 'the HTML-era archive is not a list of issues; nothing to import' );
	return;
}

require_once __DIR__ . '/lib_tokens.php';

/*
 * The previous image's seed made four placeholder records keyed to real issue
 * files ("The demonstration image carries the record ... and not the document
 * body"). On a volume that image filled they are still there, and the key this
 * import checks would treat them as the issues and never write the real text.
 * They are removed, once, by slug and by their own placeholder sentence.
 */
foreach ( array( 'newsletter-1999-03-01', 'minutes-2015-03-13', 'minutes-2023-11-10', 'minutes-2024-01-12' ) as $maars_stub ) {
	$maars_stub_post = get_page_by_path( $maars_stub, OBJECT, 'maars_publication' );
	if ( $maars_stub_post instanceof WP_Post
		&& false !== strpos( (string) $maars_stub_post->post_content, 'demonstration image carries the record' ) ) {
		wp_delete_post( (int) $maars_stub_post->ID, true );
		WP_CLI::log( 'removed the demonstration placeholder ' . $maars_stub );
	}
}

$maars_made    = 0;
$maars_kept    = 0;
$maars_updated = 0;
$maars_bad     = 0;

/*
 * Two passes. An issue can link another ("see last month's minutes"), and on a
 * fresh volume the issue it links may not exist yet when the first is written,
 * so that link resolves to nothing and is dropped. The second pass resolves
 * every issue again with all of them present, and writes only what changed.
 */
for ( $maars_pass = 1; $maars_pass <= 2; $maars_pass++ ) :
foreach ( $maars_issues as $issue ) {
	if ( ! is_array( $issue ) || empty( $issue['src'] ) || empty( $issue['title'] ) || empty( $issue['date'] ) ) {
		if ( 1 === $maars_pass ) {
			++$maars_bad;
		}
		continue;
	}

	/* The same key production uses, so a record made by the REST import and a
	   record made here are recognisably the same record. */
	$source = 'mirror/ks0man.com/' . basename( (string) $issue['src'] );

	/* Links in the issue are tokens; resolve them, and never publish one that
	   did not resolve -- the link goes, its words stay. */
	$missing = array();
	$content = maars_pages_resolve( (string) ( $issue['blocks'] ?? '' ), $missing );
	if ( $missing ) {
		if ( 2 === $maars_pass ) {
			WP_CLI::warning( $issue['src'] . ': ' . count( $missing ) . ' unresolved reference(s), first ' . $missing[0] );
		}
		$content = (string) preg_replace( '/<a href="\{\{[^"]*\}\}"[^>]*>(.*?)<\/a>/s', '$1', $content );
		$content = (string) preg_replace( '/<img src="\{\{[^"]*\}\}"[^>]*\/?>/', '', $content );
	}

	$existing = get_posts(
		array(
			'post_type'      => 'maars_publication',
			'post_status'    => 'any',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => '_maars_source_file',
			'meta_value'     => $source,
		)
	);
	if ( $existing ) {
		/* An issue already imported takes the better transcription when the
		   converter improves: the first one lost tables, pictures and links. */
		if ( (string) get_post_field( 'post_content', (int) $existing[0] ) !== $content ) {
			wp_update_post( array( 'ID' => (int) $existing[0], 'post_content' => $content ) );
			++$maars_updated;
		} elseif ( 2 === $maars_pass ) {
			++$maars_kept;
		}
		continue;
	}
	if ( 2 === $maars_pass ) {
		continue;
	}

	$post = wp_insert_post(
		array(
			'post_type'    => 'maars_publication',
			'post_status'  => 'publish',
			'post_title'   => (string) $issue['title'],
			'post_date'    => (string) $issue['date'] . ' 09:00:00',
			'post_content' => $content,
		),
		true
	);

	if ( is_wp_error( $post ) ) {
		WP_CLI::warning( $issue['src'] . ': ' . $post->get_error_message() );
		++$maars_bad;
		continue;
	}

	update_post_meta( $post, '_maars_source_file', $source );
	update_post_meta( $post, '_maars_doc_date', (string) $issue['date'] );
	update_post_meta( $post, '_maars_grade', 'sourced' );
	update_post_meta( $post, '_maars_verified_on', '2026-10-17' );

	if ( ! empty( $issue['doc_type'] ) ) {
		wp_set_object_terms( $post, (string) $issue['doc_type'], 'maars_doc_type', false );
	}
	if ( ! empty( $issue['year'] ) ) {
		wp_set_object_terms( $post, (string) $issue['year'], 'maars_year', false );
	}

	++$maars_made;
}
endfor;

WP_CLI::success(
	sprintf(
		'HTML-era archive: %d imported, %d updated, %d unchanged, %d unusable',
		$maars_made,
		$maars_updated,
		$maars_kept,
		$maars_bad
	)
);
