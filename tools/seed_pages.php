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

require_once __DIR__ . '/lib_tokens.php';

/**
 * content/seed.json, read once.
 *
 * @return array
 */
function maars_pages_seed(): array {
	static $seed = null;
	if ( null !== $seed ) {
		return $seed;
	}
	$seed      = array();
	$seed_json = getenv( 'MAARS_SEED_JSON' );
	if ( ! is_string( $seed_json ) || '' === $seed_json ) {
		$seed_json = dirname( __DIR__ ) . '/content/seed.json';
	}
	if ( file_exists( $seed_json ) ) {
		$decoded = json_decode( (string) file_get_contents( $seed_json ), true );
		$seed    = is_array( $decoded ) ? $decoded : array();
	}
	return $seed;
}

/**
 * Create a page that the seed defines, for a child that needs it as parent.
 *
 * @param string $slug Seed page slug.
 * @return WP_Post|null
 */
function maars_pages_make_seed_parent( string $slug ) {
	$seed = maars_pages_seed();
	foreach ( (array) ( $seed['pages'] ?? array() ) as $page ) {
		if ( ( $page['slug'] ?? '' ) !== $slug ) {
			continue;
		}
		$missing = array();
		$content = maars_pages_resolve( (string) ( $page['blocks'] ?? '' ), $missing );
		$id      = wp_insert_post(
			wp_slash(
				array(
					'post_type'    => 'page',
					'post_status'  => 'publish',
					'post_title'   => (string) ( $page['title'] ?? $slug ),
					'post_name'    => $slug,
					'post_content' => $content,
					'menu_order'   => (int) ( $page['menu_order'] ?? 0 ),
				)
			),
			true
		);
		if ( is_wp_error( $id ) ) {
			return null;
		}
		update_post_meta( (int) $id, '_maars_seed_hash', md5( $content ) );
		foreach ( (array) ( $page['meta'] ?? array() ) as $key => $value ) {
			update_post_meta( (int) $id, (string) $key, $value );
		}
		WP_CLI::log( 'made the seed page ' . $slug . ', which a carried-over page needs as its parent' );
		return get_post( (int) $id );
	}
	return null;
}

/**
 * Bring the seed's own pages -- About, Privacy, Officers and the rest -- and its
 * repeaters and nets up to content/seed.json.
 *
 * tools/seed.php writes them on FIRST boot only, and verbatim. So a correction
 * to the seed never reached a volume an earlier image had filled -- the Privacy
 * page went on saying the roster was not published after the Society published
 * it -- and a token in one ({{media:...}} on Links) went out unresolved.
 *
 * This pass resolves the tokens and updates a seed page, but only one nobody
 * has edited since this tooling wrote it: _maars_seed_hash records what was
 * written, and a page whose text has moved on from that is the club's own
 * work, which is left alone and reported. A page still holding seed.php's raw
 * first-boot text, or an unresolved token, is the tooling's by definition.
 * MAARS_RESEED_PAGES=1 overrides the guard for one boot, for a volume an image
 * older than the hash filled.
 *
 * @return array{updated:int,kept:int,left:int,held:int}
 */
function maars_pages_sync_seed_pages(): array {
	$counts = array(
		'updated' => 0,
		'kept'    => 0,
		'left'    => 0,
		'held'    => 0,
	);
	$force  = '1' === (string) getenv( 'MAARS_RESEED_PAGES' );

	$items = array();
	foreach ( array( 'pages' => 'page', 'facilities' => 'maars_facility' ) as $section => $type ) {
		foreach ( (array) ( maars_pages_seed()[ $section ] ?? array() ) as $page ) {
			$items[] = array( $type, $page );
		}
	}

	foreach ( $items as list( $type, $page ) ) {
		$slug = (string) ( $page['slug'] ?? '' );
		if ( '' === $slug || ! isset( $page['blocks'] ) ) {
			continue;
		}
		$raw     = (string) $page['blocks'];
		$missing = array();
		$content = maars_pages_resolve( $raw, $missing );
		if ( $missing ) {
			++$counts['held'];
			WP_CLI::warning( 'seed page ' . $slug . ' not updated: ' . count( $missing ) . ' unresolved reference(s), first ' . $missing[0] );
			continue;
		}

		$path = ( 'page' === $type && ! empty( $page['parent'] ) ) ? $page['parent'] . '/' . $slug : $slug;
		$post = get_page_by_path( $path, OBJECT, $type );
		if ( ! $post instanceof WP_Post ) {
			continue;                     /* creating seed content is tools/seed.php's job */
		}

		$current = (string) $post->post_content;
		if ( $current === $content ) {
			if ( '' === (string) get_post_meta( (int) $post->ID, '_maars_seed_hash', true ) ) {
				update_post_meta( (int) $post->ID, '_maars_seed_hash', md5( $content ) );
			}
			++$counts['kept'];
			continue;
		}

		$stored    = (string) get_post_meta( (int) $post->ID, '_maars_seed_hash', true );
		$untouched = ( '' !== $stored && hash_equals( $stored, md5( $current ) ) )
			|| $current === $raw
			|| (bool) preg_match( '/\{\{(media-full|media|pub):/', $current );
		if ( ! $untouched && ! $force ) {
			++$counts['left'];
			WP_CLI::log( 'seed page ' . $slug . ' left alone: it has been edited since it was seeded (MAARS_RESEED_PAGES=1 overrides)' );
			continue;
		}

		$id = wp_update_post(
			wp_slash(
				array(
					'ID'           => (int) $post->ID,
					'post_title'   => (string) ( $page['title'] ?? $post->post_title ),
					'post_content' => $content,
				)
			),
			true
		);
		if ( is_wp_error( $id ) ) {
			WP_CLI::warning( 'seed page ' . $slug . ': ' . $id->get_error_message() );
			continue;
		}
		update_post_meta( (int) $post->ID, '_maars_seed_hash', md5( $content ) );
		foreach ( (array) ( $page['meta'] ?? array() ) as $key => $value ) {
			update_post_meta( (int) $post->ID, (string) $key, $value );
		}
		++$counts['updated'];
	}

	return $counts;
}

$maars_seed_counts = maars_pages_sync_seed_pages();
WP_CLI::log(
	sprintf(
		'seed pages: %d updated, %d already current, %d left alone (edited), %d withheld',
		$maars_seed_counts['updated'],
		$maars_seed_counts['kept'],
		$maars_seed_counts['left'],
		$maars_seed_counts['held']
	)
);

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
		if ( ! $parent instanceof WP_Post ) {
			/* tools/seed.php makes seed pages on FIRST boot only, so a parent
			   added to the seed later ("history") never exists on a volume an
			   earlier image filled. Make it from the seed now, rather than
			   publish its children at the top level, where the footer's link
			   to /history/ and every child URL would be wrong for good. */
			$parent = maars_pages_make_seed_parent( (string) $spec['parent'] );
		}
		if ( ! $parent instanceof WP_Post ) {
			++$maars_held;
			WP_CLI::warning( $spec['slug'] . ' not published: its parent page "' . $spec['parent'] . '" does not exist and is not in the seed' );
			continue;
		}
		$parent_id = (int) $parent->ID;
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
		$id            = wp_update_post( wp_slash( $postarr ), true );
		++$maars_kept;
	} else {
		$id = wp_insert_post( wp_slash( $postarr ), true );
		++$maars_made;
	}

	if ( is_wp_error( $id ) ) {
		WP_CLI::warning( $spec['slug'] . ': ' . $id->get_error_message() );
		continue;
	}

	update_post_meta( (int) $id, '_maars_grade', 'measured' );
	update_post_meta( (int) $id, '_maars_verified_on', (string) ( $maars_bundle['generated'] ?? '' ) );
	if ( ! empty( $spec['source_paths'][0] ) ) {
		update_post_meta( (int) $id, '_maars_source_file', (string) $spec['source_paths'][0] );
	} elseif ( ! empty( $spec['sources'][0] ) ) {
		update_post_meta( (int) $id, '_maars_source_file', (string) $spec['sources'][0] );
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
