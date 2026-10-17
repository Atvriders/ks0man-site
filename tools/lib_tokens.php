<?php
/**
 * MAARS — resolve the tokens that content bundles carry instead of URLs.
 *
 *     {{media:<file>}}       an attachment, by the name it shipped under
 *     {{media-full:<file>}}  the same, at full size: WordPress keeps a large
 *                            upload aside and serves <name>-scaled.jpg, so a
 *                            link that promises the full picture names the
 *                            original (media_details original_image) instead
 *     {{pub:<source>}}       an archive record, by the file it was made from
 *
 * Required by tools/seed_pages.php and tools/import_html_archive.php, so a
 * page and an archive issue resolve the same token the same way.
 */

if ( defined( 'MAARS_TOKENS_LOADED' ) ) {
	return;
}
define( 'MAARS_TOKENS_LOADED', true );

/**
 * URL of an attachment, found by the name the file shipped under.
 *
 * The attachment carries _maars_media_src (its name on ks0man.com) and its slug
 * comes from the shipped file name; either can be the token. WordPress renames
 * a large image on upload -- fd18-tower.jpg is stored as fd18-tower-scaled.jpg
 * -- so the file on disk is exactly what must NOT be matched on.
 */
function maars_pages_media_url( string $file, bool $full = false ) {
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
	if ( ! is_string( $url ) || '' === $url ) {
		return null;
	}

	if ( $full ) {
		$meta = wp_get_attachment_metadata( (int) $found[0] );
		if ( is_array( $meta ) && ! empty( $meta['original_image'] ) ) {
			$url = trailingslashit( dirname( $url ) ) . rawurlencode( (string) $meta['original_image'] );
		}
	}

	return $url;
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
		'/\{\{(media-full|media|pub):([^}]+)\}\}/',
		static function ( $m ) use ( &$missing ) {
			if ( 'pub' === $m[1] ) {
				$url = maars_pages_publication_url( $m[2] );
			} else {
				$url = maars_pages_media_url( $m[2], 'media-full' === $m[1] );
			}

			if ( null === $url ) {
				$missing[] = $m[0];
				return $m[0];
			}

			return esc_url( $url );
		},
		$html
	);
}

