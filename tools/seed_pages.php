<?php
/**
 * MAARS — publish the pages of ks0man.com that the archive migration did not
 * carry: the member roster, the Silent Keys, the Field Day galleries and three
 * write-ups of public-service events.
 *
 * Run by WP-CLI from the entrypoint, AFTER tools/import_media.php:
 *     wp eval-file /usr/src/maars/tools/seed_pages.php
 *
 * The order is not incidental. content/mirror_pages.json carries references as
 * tokens, not URLs, because the converter on a laptop cannot know what an
 * upload will be called on a live site:
 *
 *     {{media:silentkey-nadine-stueve.jpg}}   an attachment, by the name it shipped under
 *     {{pub:newsletter_01-24.pdf}}            an archive record, by its source file
 *
 * Both are resolved here against the database, which means the media has to be
 * in it first. A page whose tokens cannot all be resolved is NOT published:
 * a page that goes out with "{{media:...}}" printed in it is worse than a page
 * that is missing, because the first looks like the site is broken and the
 * second looks like what it is.
 *
 * Idempotent: pages are keyed on slug and updated in place, so a container that
 * boots a hundred times has eleven pages, not eleven hundred.
 */

if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) {
	return;
}

$maars_pages_json = getenv( 'MAARS_MIRROR_PAGES' );
if ( ! is_string( $maars_pages_json ) || '' === $maars_pages_json ) {
	$maars_pages_json = '/usr/src/maars/content/mirror_pages.json';
}

if ( ! file_exists( $maars_pages_json ) ) {
	WP_CLI::warning( 'no mirror pages at ' . $maars_pages_json . '; nothing to publish' );
	return;
}

$maars_bundle = json_decode( (string) file_get_contents( $maars_pages_json ), true );
if ( ! is_array( $maars_bundle ) || empty( $maars_bundle['pages'] ) ) {
	WP_CLI::warning( 'mirror pages file is not a bundle; nothing to publish' );
	return;
}

/**
 * URL of an attachment, found by the name the file shipped under.
 *
 * The attachment carries _maars_media_src (its name on ks0man.com) and its slug
 * comes from the shipped file name; either can be the token. WordPress renames
 * a large image on upload -- fd18-tower.jpg is stored as fd18-tower-scaled.jpg
 * -- so the file on disk is exactly what must NOT be matched on.
 */
function maars_pages_media_url( string $file ) {
	/* Three keys, tried in order of exactness:
	     _maars_media_file  the name the file shipped under, recorded by
	                        import_media.php -- the only exact match
	     slug               right for anything uploaded under its shipped name
	     _maars_media_src   the name it had on ks0man.com
	   None of them is the file on disk, which WordPress renames: a large image
	   is stored as <name>-scaled.jpg, and an attachment's slug comes from its
	   title, which comes from the ORIGINAL name. Matching on disk names is what
	   put fifteen duplicate photographs in the production media library. */
	$by_meta = static function ( string $key, string $value ) {
		return get_posts(
			array(
				'post_type'      => 'attachment',
				'post_status'    => 'inherit',
				'posts_per_page' => 1,
				'fields'         => 'ids',
				'meta_query'     => array(
					array(
						'key'     => $key,
						'value'   => $value,
						'compare' => '=',
					),
				),
			)
		);
	};

	$found = $by_meta( '_maars_media_file', $file );

	if ( ! $found ) {
		$found = get_posts(
			array(
				'post_type'        => 'attachment',
				'post_status'      => 'inherit',
				'name'             => sanitize_title( pathinfo( $file, PATHINFO_FILENAME ) ),
				'posts_per_page'   => 1,
				'fields'           => 'ids',
				'suppress_filters' => false,
			)
		);
	}

	if ( ! $found ) {
		$found = $by_meta( '_maars_media_src', $file );
	}

	if ( ! $found ) {
		return null;
	}

	$url = wp_get_attachment_url( (int) $found[0] );

	return is_string( $url ) && '' !== $url ? $url : null;
}

/**
 * Permalink of the archive record made from a given source file.
 */
function maars_pages_publication_url( string $source ) {
	$stem = pathinfo( $source, PATHINFO_FILENAME );

	foreach ( array( $source, $stem . '.pdf', $stem . '.html', $stem . '.htm' ) as $candidate ) {
		$found = get_posts(
			array(
				'post_type'      => 'maars_publication',
				'post_status'    => 'publish',
				'posts_per_page' => 1,
				'fields'         => 'ids',
				'meta_query'     => array(
					array(
						'key'     => '_maars_source_file',
						'value'   => $candidate,
						'compare' => 'LIKE',
					),
				),
			)
		);
		if ( $found ) {
			return get_permalink( (int) $found[0] );
		}
	}

	return null;
}

/**
 * Swap every {{media:…}} and {{pub:…}} for a URL, or report what is missing.
 *
 * @param string $html    Block markup with tokens in it.
 * @param array  $missing Filled with the tokens that could not be resolved.
 * @return string
 */
function maars_pages_resolve( string $html, array &$missing ): string {
	return (string) preg_replace_callback(
		'/\{\{(media|pub):([^}]+)\}\}/',
		static function ( $m ) use ( &$missing ) {
			$url = ( 'media' === $m[1] )
				? maars_pages_media_url( $m[2] )
				: maars_pages_publication_url( $m[2] );

			if ( null === $url ) {
				$missing[] = $m[0];
				return $m[0];
			}

			return esc_url( $url );
		},
		$html
	);
}

$maars_made = 0;
$maars_kept = 0;
$maars_held = 0;

foreach ( $maars_bundle['pages'] as $spec ) {
	if ( empty( $spec['slug'] ) || ! isset( $spec['blocks'] ) ) {
		continue;
	}

	$missing = array();
	$content = maars_pages_resolve( (string) $spec['blocks'], $missing );

	if ( $missing ) {
		++$maars_held;
		WP_CLI::warning(
			sprintf(
				'%s not published: %d unresolved reference(s), first is %s',
				$spec['slug'],
				count( $missing ),
				$missing[0]
			)
		);
		continue;
	}

	$parent_id = 0;
	if ( ! empty( $spec['parent'] ) ) {
		$parent = get_page_by_path( (string) $spec['parent'] );
		if ( $parent instanceof WP_Post ) {
			$parent_id = (int) $parent->ID;
		}
	}

	$existing = get_page_by_path(
		$parent_id ? $spec['parent'] . '/' . $spec['slug'] : $spec['slug']
	);
	if ( ! $existing instanceof WP_Post ) {
		/* A page seeded before its parent existed sits at the top level. */
		$existing = get_page_by_path( (string) $spec['slug'] );
	}

	$postarr = array(
		'post_type'    => 'page',
		'post_status'  => 'publish',
		'post_title'   => (string) ( $spec['title'] ?? $spec['slug'] ),
		'post_name'    => (string) $spec['slug'],
		'post_content' => $content,
		'post_parent'  => $parent_id,
	);

	if ( $existing instanceof WP_Post ) {
		$postarr['ID'] = (int) $existing->ID;
		$id            = wp_update_post( $postarr, true );
		++$maars_kept;
	} else {
		$id = wp_insert_post( $postarr, true );
		++$maars_made;
	}

	if ( is_wp_error( $id ) ) {
		WP_CLI::warning( $spec['slug'] . ': ' . $id->get_error_message() );
		continue;
	}

	update_post_meta( (int) $id, '_maars_grade', 'measured' );
	update_post_meta( (int) $id, '_maars_verified_on', (string) ( $maars_bundle['generated'] ?? '' ) );
	if ( ! empty( $spec['sources'][0] ) ) {
		update_post_meta( (int) $id, '_maars_source_file', 'mirror/ks0man.com/' . $spec['sources'][0] );
	}
}

WP_CLI::success(
	sprintf(
		'mirror pages: %d created, %d updated, %d withheld',
		$maars_made,
		$maars_kept,
		$maars_held
	)
);
