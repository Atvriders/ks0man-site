<?php
/**
 * MAARS / KSØMAN — idempotent content seeder.
 *
 * Run by WP-CLI:
 *
 *     wp eval-file tools/seed.php
 *     wp eval-file tools/seed.php /path/to/seed.json
 *
 * Reads content/seed.json (the public-safe bundle baked into the image) and
 * creates the standing pages, the maars_facility records, the maars_publication
 * records and the taxonomy terms. It sets the front page, the permalink
 * structure and the primary navigation, then prints a summary.
 *
 * Idempotent: every record is keyed on its slug within its post type, every
 * term on its slug, every menu item on the page it points at. Running the
 * script a second time reports everything as "unchanged" and writes nothing —
 * posts are only updated when the title, status, content or meta actually
 * differ from what the bundle says they should be.
 *
 * The bundle contains NO personal data. See content/seed.json for what is and
 * is not in it, and tools/build_content.py for the local generator the Society
 * runs against its own mirror to produce the full content set.
 *
 * @package maars
 */

if ( ! defined( 'WP_CLI' ) ) {
	return;
}

/**
 * Emit a line of progress output.
 *
 * @param string $message Message.
 * @return void
 */
function maars_seed_log( $message ) {
	WP_CLI::log( $message );
}

/**
 * Locate the seed bundle.
 *
 * A path given as an argument, or in MAARS_SEED_JSON, is used or the run fails.
 * With neither, the repository layout (tools/../content/seed.json) and a couple
 * of image locations are tried in turn.
 *
 * @param array $args Positional arguments handed to `wp eval-file`.
 * @return string Absolute path.
 */
function maars_seed_locate_json( $args ) {
	/*
	 * An explicitly named bundle is not a suggestion. If it is not there, say
	 * so — quietly seeding a different file than the one you asked for is worse
	 * than failing.
	 */
	$explicit = '';

	if ( ! empty( $args[0] ) ) {
		$explicit = (string) $args[0];
	} else {
		$env = getenv( 'MAARS_SEED_JSON' );

		if ( is_string( $env ) && '' !== $env ) {
			$explicit = $env;
		}
	}

	if ( '' !== $explicit ) {
		if ( is_readable( $explicit ) && is_file( $explicit ) ) {
			return $explicit;
		}

		WP_CLI::error( 'No readable bundle at ' . $explicit );
	}

	$here       = dirname( __FILE__ );
	$candidates = array(
		dirname( $here ) . '/content/seed.json',
		$here . '/seed.json',
		'/usr/local/share/maars/seed.json',
		'/var/www/html/wp-content/maars/seed.json',
	);

	if ( defined( 'ABSPATH' ) ) {
		$candidates[] = ABSPATH . 'wp-content/maars/seed.json';
	}

	foreach ( $candidates as $candidate ) {
		if ( is_readable( $candidate ) && is_file( $candidate ) ) {
			return $candidate;
		}
	}

	WP_CLI::error(
		"Could not find seed.json. Looked in:\n  - " . implode( "\n  - ", $candidates )
		. "\nPass a path (wp eval-file tools/seed.php /path/to/seed.json) or set MAARS_SEED_JSON."
	);

	return ''; // Unreachable; WP_CLI::error() exits.
}

/**
 * Read and validate the bundle.
 *
 * @param string $path Absolute path to the JSON bundle.
 * @return array Decoded bundle.
 */
function maars_seed_read_json( $path ) {
	$raw = file_get_contents( $path );

	if ( false === $raw ) {
		WP_CLI::error( 'Could not read ' . $path );
	}

	$data = json_decode( $raw, true );

	if ( null === $data || ! is_array( $data ) ) {
		WP_CLI::error( 'seed.json is not valid JSON: ' . json_last_error_msg() );
	}

	foreach ( array( 'site', 'terms', 'pages', 'facilities', 'publications' ) as $key ) {
		if ( ! isset( $data[ $key ] ) ) {
			WP_CLI::error( 'seed.json is missing the "' . $key . '" key.' );
		}
	}

	return $data;
}

/**
 * Make sure the maars-core post types and taxonomies are registered.
 *
 * The seeder normally runs after the plugin is active. If it is not, try to
 * activate it and register the types by hand so a first boot in any order
 * still works.
 *
 * @return void
 */
function maars_seed_require_post_types() {
	if ( post_type_exists( 'maars_publication' ) && post_type_exists( 'maars_facility' ) ) {
		return;
	}

	if ( defined( 'ABSPATH' ) && file_exists( ABSPATH . 'wp-admin/includes/plugin.php' ) ) {
		require_once ABSPATH . 'wp-admin/includes/plugin.php';

		$plugin = 'maars-core/maars-core.php';

		if ( function_exists( 'is_plugin_active' ) && ! is_plugin_active( $plugin )
			&& defined( 'WP_PLUGIN_DIR' ) && file_exists( WP_PLUGIN_DIR . '/' . $plugin ) ) {
			$activated = activate_plugin( $plugin );

			if ( is_wp_error( $activated ) ) {
				WP_CLI::warning( 'Could not activate maars-core: ' . $activated->get_error_message() );
			} else {
				maars_seed_log( 'Activated the maars-core plugin.' );
			}
		}
	}

	foreach ( array( 'maars_register_post_types', 'maars_register_taxonomies', 'maars_register_meta' ) as $callback ) {
		if ( function_exists( $callback ) ) {
			call_user_func( $callback );
		}
	}

	if ( ! post_type_exists( 'maars_publication' ) || ! post_type_exists( 'maars_facility' ) ) {
		WP_CLI::error(
			'The maars-core post types are not registered. Activate the plugin first: '
			. 'wp plugin activate maars-core'
		);
	}
}

/**
 * Create a taxonomy term if it is missing.
 *
 * @param array $spec  Term spec: taxonomy, slug, name, optional description and parent slug.
 * @param array $stats Counters, by reference.
 * @return int|null Term ID, or null when the taxonomy does not exist.
 */
function maars_seed_term( $spec, &$stats ) {
	$taxonomy = isset( $spec['taxonomy'] ) ? $spec['taxonomy'] : '';
	$slug     = isset( $spec['slug'] ) ? $spec['slug'] : '';
	$name     = isset( $spec['name'] ) ? $spec['name'] : $slug;

	if ( '' === $taxonomy || '' === $slug ) {
		return null;
	}

	if ( ! taxonomy_exists( $taxonomy ) ) {
		WP_CLI::warning( 'Taxonomy ' . $taxonomy . ' is not registered; skipping term "' . $slug . '".' );
		++$stats['terms_skipped'];
		return null;
	}

	$existing = get_term_by( 'slug', $slug, $taxonomy );

	if ( $existing instanceof WP_Term ) {
		++$stats['terms_unchanged'];
		return (int) $existing->term_id;
	}

	$args = array( 'slug' => $slug );

	if ( ! empty( $spec['description'] ) ) {
		$args['description'] = $spec['description'];
	}

	if ( ! empty( $spec['parent'] ) ) {
		$parent = get_term_by( 'slug', $spec['parent'], $taxonomy );
		if ( $parent instanceof WP_Term ) {
			$args['parent'] = (int) $parent->term_id;
		}
	}

	$created = wp_insert_term( $name, $taxonomy, $args );

	if ( is_wp_error( $created ) ) {
		WP_CLI::warning( 'Term "' . $slug . '" (' . $taxonomy . '): ' . $created->get_error_message() );
		++$stats['terms_skipped'];
		return null;
	}

	++$stats['terms_created'];

	return (int) $created['term_id'];
}

/**
 * Find an existing post by slug within a post type.
 *
 * @param string $slug      Post slug.
 * @param string $post_type Post type.
 * @return WP_Post|null
 */
function maars_seed_find( $slug, $post_type ) {
	$found = get_posts(
		array(
			'name'                   => $slug,
			'post_type'              => $post_type,
			'post_status'            => array( 'publish', 'draft', 'pending', 'private', 'future', 'trash' ),
			'posts_per_page'         => 1,
			'no_found_rows'          => true,
			'ignore_sticky_posts'    => true,
			'update_post_term_cache' => false,
			'suppress_filters'       => false,
		)
	);

	return empty( $found ) ? null : $found[0];
}

/**
 * Apply meta values, writing only the ones that differ.
 *
 * @param int   $post_id Post ID.
 * @param array $meta    Meta key => value.
 * @return int Number of meta values written.
 */
function maars_seed_apply_meta( $post_id, $meta ) {
	$written = 0;

	foreach ( $meta as $key => $value ) {
		$value   = (string) $value;
		$current = get_post_meta( $post_id, $key, true );

		if ( (string) $current === $value ) {
			continue;
		}

		update_post_meta( $post_id, $key, $value );
		++$written;
	}

	return $written;
}

/**
 * Apply taxonomy terms, writing only when the set differs.
 *
 * @param int   $post_id Post ID.
 * @param array $terms   Taxonomy => list of term slugs.
 * @return int Number of taxonomies written.
 */
function maars_seed_apply_terms( $post_id, $terms ) {
	$written = 0;

	foreach ( $terms as $taxonomy => $slugs ) {
		if ( ! taxonomy_exists( $taxonomy ) ) {
			WP_CLI::warning( 'Taxonomy ' . $taxonomy . ' is not registered; skipping assignment.' );
			continue;
		}

		$ids = array();

		foreach ( (array) $slugs as $slug ) {
			$term = get_term_by( 'slug', $slug, $taxonomy );

			if ( ! $term instanceof WP_Term ) {
				$made = wp_insert_term( $slug, $taxonomy, array( 'slug' => $slug ) );

				if ( is_wp_error( $made ) ) {
					WP_CLI::warning( 'Could not create term "' . $slug . '" in ' . $taxonomy . '.' );
					continue;
				}

				$ids[] = (int) $made['term_id'];
				continue;
			}

			$ids[] = (int) $term->term_id;
		}

		$current = wp_get_object_terms( $post_id, $taxonomy, array( 'fields' => 'ids' ) );

		if ( is_wp_error( $current ) ) {
			$current = array();
		}

		$current = array_map( 'intval', $current );

		sort( $current );
		$wanted = $ids;
		sort( $wanted );

		if ( $current === $wanted ) {
			continue;
		}

		wp_set_object_terms( $post_id, $ids, $taxonomy, false );
		++$written;
	}

	return $written;
}

/**
 * Create or update one seeded post.
 *
 * @param array  $spec       Record spec from the bundle.
 * @param string $post_type  Post type to create it as.
 * @param array  $stats      Counters, by reference.
 * @param array  $page_index Page slug => post ID, for resolving a page parent.
 * @return int Post ID, or 0 on failure.
 */
function maars_seed_upsert_post( $spec, $post_type, &$stats, $page_index = array() ) {
	$slug = isset( $spec['slug'] ) ? sanitize_title( $spec['slug'] ) : '';

	if ( '' === $slug ) {
		WP_CLI::warning( 'Skipping a ' . $post_type . ' record with no slug.' );
		return 0;
	}

	$title   = isset( $spec['title'] ) ? $spec['title'] : $slug;
	$content = isset( $spec['blocks'] ) ? $spec['blocks'] : '';
	$excerpt = isset( $spec['excerpt'] ) ? $spec['excerpt'] : '';
	$order   = isset( $spec['menu_order'] ) ? (int) $spec['menu_order'] : 0;

	$parent = 0;

	if ( ! empty( $spec['parent'] ) ) {
		$parent = maars_seed_resolve_page( $spec['parent'], $page_index );

		if ( 0 === $parent ) {
			WP_CLI::warning(
				'Page "' . $slug . '" wants the parent "' . $spec['parent']
				. '", which does not exist yet. Filing it at the top level.'
			);
		}
	}

	$data = array(
		'post_type'    => $post_type,
		'post_parent'  => $parent,
		'post_name'    => $slug,
		'post_title'   => $title,
		'post_content' => $content,
		'post_excerpt' => $excerpt,
		'post_status'  => 'publish',
		'menu_order'   => $order,
		'post_author'  => maars_seed_author_id(),
	);

	if ( ! empty( $spec['date'] ) ) {
		$stamp = strtotime( $spec['date'] . ' 12:00:00' );

		if ( false !== $stamp ) {
			$data['post_date']     = gmdate( 'Y-m-d H:i:s', $stamp );
			$data['post_date_gmt'] = gmdate( 'Y-m-d H:i:s', $stamp );
		}
	}

	$existing = maars_seed_find( $slug, $post_type );
	$verb     = 'unchanged';

	if ( $existing instanceof WP_Post && ! empty( $spec['if_absent'] ) ) {
		/*
		 * "Create it if it is missing, otherwise leave it alone." The public
		 * seed's archive records are demonstration stubs that share their slugs
		 * with the real documents, so that loading the full local bundle
		 * upgrades them in place. Without this flag, re-running the public seed
		 * afterwards would put the stubs back over the real thing.
		 */
		++$stats['posts_kept'];
		$stats['detail'][] = sprintf( '  %-9s %-18s %s', 'kept', $post_type, $slug );

		return (int) $existing->ID;
	}

	if ( $existing instanceof WP_Post ) {
		$post_id = (int) $existing->ID;
		$changed = false;

		foreach ( array( 'post_title', 'post_content', 'post_excerpt' ) as $field ) {
			if ( (string) $existing->$field !== (string) $data[ $field ] ) {
				$changed = true;
			}
		}

		if ( 'publish' !== $existing->post_status || (int) $existing->menu_order !== $order
			|| (int) $existing->post_parent !== $parent ) {
			$changed = true;
		}

		if ( $changed ) {
			$data['ID'] = $post_id;
			unset( $data['post_date'], $data['post_date_gmt'] );

			$updated = wp_update_post( wp_slash( $data ), true );

			if ( is_wp_error( $updated ) ) {
				WP_CLI::warning( $post_type . ' "' . $slug . '": ' . $updated->get_error_message() );
				return 0;
			}

			$verb = 'updated';
		}
	} else {
		$post_id = wp_insert_post( wp_slash( $data ), true );

		if ( is_wp_error( $post_id ) ) {
			WP_CLI::warning( $post_type . ' "' . $slug . '": ' . $post_id->get_error_message() );
			return 0;
		}

		$post_id = (int) $post_id;
		$verb    = 'created';
	}

	$meta_written = maars_seed_apply_meta( $post_id, isset( $spec['meta'] ) ? (array) $spec['meta'] : array() );
	$term_written = maars_seed_apply_terms( $post_id, isset( $spec['terms'] ) ? (array) $spec['terms'] : array() );

	if ( 'unchanged' === $verb && ( $meta_written > 0 || $term_written > 0 ) ) {
		$verb = 'updated';
	}

	++$stats[ 'posts_' . $verb ];
	$stats['detail'][] = sprintf( '  %-9s %-18s %s', $verb, $post_type, $slug );

	return $post_id;
}

/**
 * Pick an author for seeded content: the first administrator, else user 1.
 *
 * @return int User ID.
 */
function maars_seed_author_id() {
	static $author_id = null;

	if ( null !== $author_id ) {
		return $author_id;
	}

	$admins = get_users(
		array(
			'role'    => 'administrator',
			'number'  => 1,
			'orderby' => 'ID',
			'order'   => 'ASC',
			'fields'  => 'ID',
		)
	);

	$author_id = empty( $admins ) ? 1 : (int) $admins[0];

	return $author_id;
}

/**
 * Resolve a page slug to a post ID, in this bundle or already in the database.
 *
 * The archive bundle produced by tools/build_content.py carries the same site
 * and menu configuration as the seed but none of the seed's standing pages. If
 * navigation only ever looked at the bundle in hand, loading the archive on top
 * of the seed would silently empty the menu.
 *
 * @param string $slug    Page slug.
 * @param array  $page_id Page slug => post ID for pages in this bundle.
 * @return int Post ID, or 0 when there is no such page.
 */
function maars_seed_resolve_page( $slug, $page_id ) {
	if ( ! empty( $page_id[ $slug ] ) ) {
		return (int) $page_id[ $slug ];
	}

	$post = maars_seed_find( $slug, 'page' );

	if ( $post instanceof WP_Post && 'trash' !== $post->post_status ) {
		return (int) $post->ID;
	}

	return 0;
}

/**
 * Identity of a menu item: what it points at, not where it sits.
 *
 * @param string $type      Menu item type, "post_type" or "custom".
 * @param int    $object_id Target post ID for a post_type item.
 * @param string $url       Target URL for a custom item.
 * @return string Stable key.
 */
function maars_seed_menu_key( $type, $object_id, $url ) {
	if ( 'custom' === $type ) {
		return 'custom:' . untrailingslashit( (string) $url );
	}

	return 'post_type:' . (int) $object_id;
}

/**
 * Build the classic navigation menu and assign it to every registered location.
 *
 * @param array $menu    Menu spec from the bundle.
 * @param array $page_id Page slug => post ID.
 * @param array $stats   Counters, by reference.
 * @return int Menu term ID, or 0.
 */
function maars_seed_classic_menu( $menu, $page_id, &$stats ) {
	$name = isset( $menu['name'] ) ? $menu['name'] : 'Primary';

	$object = wp_get_nav_menu_object( $name );

	if ( ! $object ) {
		$menu_id = wp_create_nav_menu( $name );

		if ( is_wp_error( $menu_id ) ) {
			WP_CLI::warning( 'Could not create the "' . $name . '" menu: ' . $menu_id->get_error_message() );
			return 0;
		}

		$menu_id = (int) $menu_id;
		++$stats['menu_created'];
	} else {
		$menu_id = (int) $object->term_id;
	}

	$existing = wp_get_nav_menu_items( $menu_id, array( 'post_status' => 'publish,draft' ) );
	$existing = is_array( $existing ) ? $existing : array();

	$by_key = array();

	foreach ( $existing as $item ) {
		$by_key[ maars_seed_menu_key( $item->type, (int) $item->object_id, (string) $item->url ) ] = $item;
	}

	$keep     = array();
	$position = 0;

	foreach ( (array) $menu['items'] as $spec ) {
		$slug   = isset( $spec['page'] ) ? $spec['page'] : '';
		$url    = isset( $spec['url'] ) ? (string) $spec['url'] : '';
		$target = '' === $slug ? 0 : maars_seed_resolve_page( $slug, $page_id );

		if ( 0 === $target && '' === $url ) {
			continue;
		}

		++$position;
		$label = isset( $spec['label'] ) ? $spec['label'] : ( '' !== $slug ? $slug : $url );

		if ( $target > 0 ) {
			$args = array(
				'menu-item-title'     => $label,
				'menu-item-object'    => 'page',
				'menu-item-object-id' => $target,
				'menu-item-type'      => 'post_type',
				'menu-item-status'    => 'publish',
				'menu-item-position'  => $position,
			);
			$key  = maars_seed_menu_key( 'post_type', $target, '' );
		} else {
			$args = array(
				'menu-item-title'    => $label,
				'menu-item-url'      => home_url( $url ),
				'menu-item-type'     => 'custom',
				'menu-item-status'   => 'publish',
				'menu-item-position' => $position,
			);
			$key  = maars_seed_menu_key( 'custom', 0, home_url( $url ) );
		}

		$item = isset( $by_key[ $key ] ) ? $by_key[ $key ] : null;

		if ( $item ) {
			$keep[] = (int) $item->ID;

			if ( (string) $item->title === (string) $label && (int) $item->menu_order === $position ) {
				++$stats['menu_unchanged'];
				continue;
			}

			wp_update_nav_menu_item( $menu_id, (int) $item->ID, $args );
			++$stats['menu_updated'];
			continue;
		}

		$new_id = wp_update_nav_menu_item( $menu_id, 0, $args );

		if ( is_wp_error( $new_id ) ) {
			WP_CLI::warning( 'Menu item "' . $label . '": ' . $new_id->get_error_message() );
			continue;
		}

		$keep[] = (int) $new_id;
		++$stats['menu_created_items'];
	}

	if ( empty( $keep ) ) {
		// Nothing in this bundle resolved to a page. Leave the menu as it is
		// rather than emptying it.
		return $menu_id;
	}

	foreach ( $existing as $item ) {
		if ( ! in_array( (int) $item->ID, $keep, true ) ) {
			wp_delete_post( (int) $item->ID, true );
			++$stats['menu_removed'];
		}
	}

	$registered = get_registered_nav_menus();
	$locations  = get_theme_mod( 'nav_menu_locations' );
	$locations  = is_array( $locations ) ? $locations : array();
	$wanted     = isset( $menu['locations'] ) ? (array) $menu['locations'] : array();
	$dirty      = false;

	foreach ( array_keys( $registered ) as $location ) {
		if ( ! empty( $wanted ) && ! in_array( $location, $wanted, true ) && count( $registered ) > 1 ) {
			continue;
		}

		if ( isset( $locations[ $location ] ) && (int) $locations[ $location ] === $menu_id ) {
			continue;
		}

		$locations[ $location ] = $menu_id;
		$dirty                  = true;
	}

	if ( $dirty ) {
		set_theme_mod( 'nav_menu_locations', $locations );
		++$stats['menu_locations'];
	}

	return $menu_id;
}

/**
 * Build the block-theme navigation (a wp_navigation post).
 *
 * A block theme's header part renders <!-- wp:navigation /-->, which resolves
 * to a wp_navigation post rather than a classic menu, so the seeder maintains
 * both and the header works whichever the theme asked for.
 *
 * @param array $menu    Menu spec from the bundle.
 * @param array $page_id Page slug => post ID.
 * @param array $stats   Counters, by reference.
 * @return int Navigation post ID, or 0.
 */
function maars_seed_navigation_post( $menu, $page_id, &$stats ) {
	if ( ! post_type_exists( 'wp_navigation' ) ) {
		return 0;
	}

	$slug   = isset( $menu['slug'] ) ? sanitize_title( $menu['slug'] ) : 'primary';
	$name   = isset( $menu['name'] ) ? $menu['name'] : 'Primary';
	$blocks = array();

	foreach ( (array) $menu['items'] as $spec ) {
		$page_slug = isset( $spec['page'] ) ? $spec['page'] : '';
		$custom    = isset( $spec['url'] ) ? (string) $spec['url'] : '';
		$target    = '' === $page_slug ? 0 : maars_seed_resolve_page( $page_slug, $page_id );

		if ( 0 === $target && '' === $custom ) {
			continue;
		}

		$label = isset( $spec['label'] ) ? $spec['label'] : ( '' !== $page_slug ? $page_slug : $custom );

		if ( $target > 0 ) {
			$url = get_permalink( $target );

			if ( ! $url ) {
				$url = home_url( '/' );
			}

			$attrs = array(
				'label' => wp_strip_all_tags( $label ),
				'type'  => 'page',
				'id'    => $target,
				'url'   => $url,
				'kind'  => 'post-type',
			);
		} else {
			$attrs = array(
				'label' => wp_strip_all_tags( $label ),
				'url'   => home_url( $custom ),
				'kind'  => 'custom',
			);
		}

		$blocks[] = '<!-- wp:navigation-link ' . wp_json_encode( $attrs ) . ' /-->';
	}

	if ( empty( $blocks ) ) {
		return 0;
	}

	$content  = implode( "\n", $blocks );
	$existing = maars_seed_find( $slug, 'wp_navigation' );

	if ( $existing instanceof WP_Post ) {
		if ( trim( (string) $existing->post_content ) === trim( $content )
			&& 'publish' === $existing->post_status ) {
			++$stats['navigation_unchanged'];
			return (int) $existing->ID;
		}

		$updated = wp_update_post(
			wp_slash(
				array(
					'ID'           => (int) $existing->ID,
					'post_content' => $content,
					'post_title'   => $name,
					'post_status'  => 'publish',
				)
			),
			true
		);

		if ( is_wp_error( $updated ) ) {
			WP_CLI::warning( 'Navigation: ' . $updated->get_error_message() );
			return 0;
		}

		++$stats['navigation_updated'];

		return (int) $existing->ID;
	}

	$new_id = wp_insert_post(
		wp_slash(
			array(
				'post_type'    => 'wp_navigation',
				'post_name'    => $slug,
				'post_title'   => $name,
				'post_content' => $content,
				'post_status'  => 'publish',
				'post_author'  => maars_seed_author_id(),
			)
		),
		true
	);

	if ( is_wp_error( $new_id ) ) {
		WP_CLI::warning( 'Navigation: ' . $new_id->get_error_message() );
		return 0;
	}

	++$stats['navigation_created'];

	return (int) $new_id;
}

/**
 * Set site options: title, tagline, timezone, front page and permalinks.
 *
 * @param array $site     Site spec from the bundle.
 * @param int   $home_id  Post ID of the front page.
 * @param int   $posts_id Post ID of the page that lists posts, or 0.
 * @param array $stats    Counters, by reference.
 * @return void
 */
function maars_seed_options( $site, $home_id, $posts_id, &$stats ) {
	$options = array();

	if ( ! empty( $site['title'] ) ) {
		$options['blogname'] = $site['title'];
	}

	if ( isset( $site['tagline'] ) ) {
		$options['blogdescription'] = $site['tagline'];
	}

	if ( ! empty( $site['timezone'] ) ) {
		$options['timezone_string'] = $site['timezone'];
		$options['gmt_offset']      = '';
	}

	if ( $home_id > 0 ) {
		$options['show_on_front'] = 'page';
		$options['page_on_front'] = $home_id;
	}

	if ( $posts_id > 0 && $posts_id !== $home_id ) {
		$options['page_for_posts'] = $posts_id;
	}

	foreach ( $options as $key => $value ) {
		if ( (string) get_option( $key ) === (string) $value ) {
			continue;
		}

		update_option( $key, $value );
		++$stats['options'];
		maars_seed_log( '  option    ' . $key . ' = ' . ( is_scalar( $value ) ? $value : '(array)' ) );
	}

	$structure = isset( $site['permalink_structure'] ) ? $site['permalink_structure'] : '/%postname%/';

	if ( (string) get_option( 'permalink_structure' ) !== (string) $structure ) {
		global $wp_rewrite;

		if ( $wp_rewrite instanceof WP_Rewrite ) {
			$wp_rewrite->set_permalink_structure( $structure );
		} else {
			update_option( 'permalink_structure', $structure );
		}

		++$stats['options'];
		maars_seed_log( '  option    permalink_structure = ' . $structure );
	}

	flush_rewrite_rules( true );
}

/**
 * Trash the default WordPress sample content, if it is still untouched.
 *
 * @param array $stats Counters, by reference.
 * @return void
 */
function maars_seed_remove_default_content( &$stats ) {
	$targets = array(
		array( 'hello-world', 'post', 'Hello world!' ),
		array( 'sample-page', 'page', 'Sample Page' ),
		array( 'privacy-policy', 'page', 'Privacy Policy' ),
	);

	foreach ( $targets as $target ) {
		list( $slug, $type, $title ) = $target;

		$post = maars_seed_find( $slug, $type );

		if ( ! $post instanceof WP_Post || 'trash' === $post->post_status ) {
			continue;
		}

		if ( (string) $post->post_title !== $title ) {
			continue; // Somebody has edited it; leave it alone.
		}

		wp_trash_post( (int) $post->ID );
		++$stats['defaults_removed'];
		maars_seed_log( '  trashed   ' . $type . ' "' . $title . '"' );
	}

	$comment = get_comment( 1 );

	if ( ! $comment ) {
		return;
	}

	$live = in_array( (string) $comment->comment_approved, array( '0', '1' ), true );

	if ( $live && false !== strpos( (string) $comment->comment_author, 'WordPress' ) ) {
		wp_trash_comment( 1 );
		++$stats['defaults_removed'];
		maars_seed_log( '  trashed   the default comment' );
	}
}

/**
 * Run the seeder.
 *
 * @param array $args Positional arguments handed to `wp eval-file`.
 * @return void
 */
function maars_seed_run( $args ) {
	$path   = maars_seed_locate_json( $args );
	$bundle = maars_seed_read_json( $path );

	maars_seed_require_post_types();

	/*
	 * Become an administrator for the duration of the run. Without a current
	 * user, kses filters `content_save_pre` and rewrites HTML comments — which
	 * is exactly what Gutenberg block delimiters are. Setting the user also
	 * re-runs kses_init() and takes those filters back off.
	 */
	wp_set_current_user( maars_seed_author_id() );

	$stats = array(
		'terms_created'        => 0,
		'terms_unchanged'      => 0,
		'terms_skipped'        => 0,
		'posts_created'        => 0,
		'posts_updated'        => 0,
		'posts_unchanged'      => 0,
		'posts_kept'           => 0,
		'menu_created'         => 0,
		'menu_created_items'   => 0,
		'menu_updated'         => 0,
		'menu_unchanged'       => 0,
		'menu_removed'         => 0,
		'menu_locations'       => 0,
		'navigation_created'   => 0,
		'navigation_updated'   => 0,
		'navigation_unchanged' => 0,
		'options'              => 0,
		'defaults_removed'     => 0,
		'detail'               => array(),
	);

	maars_seed_log( 'MAARS seeder — reading ' . $path );

	if ( ! empty( $bundle['kind'] ) ) {
		maars_seed_log( 'Bundle: ' . $bundle['kind'] . ' (' . ( isset( $bundle['generated'] ) ? $bundle['generated'] : 'undated' ) . ')' );
	}

	$theme = wp_get_theme();

	if ( 'maars' !== $theme->get_stylesheet() ) {
		WP_CLI::warning(
			'The active theme is "' . $theme->get_stylesheet() . '", not "maars". '
			. 'Run: wp theme activate maars'
		);
	}

	foreach ( (array) $bundle['terms'] as $spec ) {
		maars_seed_term( $spec, $stats );
	}

	$page_id = array();

	foreach ( (array) $bundle['pages'] as $spec ) {
		$id = maars_seed_upsert_post( $spec, 'page', $stats, $page_id );

		if ( $id > 0 ) {
			$page_id[ $spec['slug'] ] = $id;
		}
	}

	foreach ( (array) $bundle['facilities'] as $spec ) {
		maars_seed_upsert_post( $spec, 'maars_facility', $stats );
	}

	foreach ( (array) $bundle['publications'] as $spec ) {
		maars_seed_upsert_post( $spec, 'maars_publication', $stats );
	}

	if ( ! empty( $bundle['posts'] ) ) {
		foreach ( (array) $bundle['posts'] as $spec ) {
			maars_seed_upsert_post( $spec, 'post', $stats );
		}
	}

	if ( ! empty( $bundle['people'] ) && post_type_exists( 'maars_person' ) ) {
		foreach ( (array) $bundle['people'] as $spec ) {
			maars_seed_upsert_post( $spec, 'maars_person', $stats );
		}
	}

	$site    = (array) $bundle['site'];
	$home    = isset( $site['front_page_slug'] ) ? $site['front_page_slug'] : 'home';
	$home_id = maars_seed_resolve_page( $home, $page_id );
	$posts   = isset( $site['posts_page_slug'] ) ? $site['posts_page_slug'] : '';
	$posts_id = '' === $posts ? 0 : maars_seed_resolve_page( $posts, $page_id );

	if ( ! empty( $site['remove_default_content'] ) ) {
		maars_seed_remove_default_content( $stats );
	}

	if ( ! empty( $site['menu'] ) ) {
		maars_seed_classic_menu( $site['menu'], $page_id, $stats );
		maars_seed_navigation_post( $site['menu'], $page_id, $stats );
	}

	maars_seed_options( $site, $home_id, $posts_id, $stats );

	foreach ( $stats['detail'] as $line ) {
		maars_seed_log( $line );
	}

	maars_seed_log( '' );
	maars_seed_log(
		sprintf(
			'terms      %d created, %d already present, %d skipped',
			$stats['terms_created'],
			$stats['terms_unchanged'],
			$stats['terms_skipped']
		)
	);
	maars_seed_log(
		sprintf(
			'content    %d created, %d updated, %d unchanged, %d left alone (if_absent)',
			$stats['posts_created'],
			$stats['posts_updated'],
			$stats['posts_unchanged'],
			$stats['posts_kept']
		)
	);
	maars_seed_log(
		sprintf(
			'menu       %d items added, %d updated, %d unchanged, %d removed, %d location(s) set',
			$stats['menu_created_items'],
			$stats['menu_updated'],
			$stats['menu_unchanged'],
			$stats['menu_removed'],
			$stats['menu_locations']
		)
	);
	maars_seed_log(
		sprintf(
			'navigation %d created, %d updated, %d unchanged (block theme)',
			$stats['navigation_created'],
			$stats['navigation_updated'],
			$stats['navigation_unchanged']
		)
	);
	maars_seed_log(
		sprintf(
			'options    %d written, %d default item(s) trashed',
			$stats['options'],
			$stats['defaults_removed']
		)
	);

	if ( $home_id > 0 ) {
		maars_seed_log( 'front page ' . get_the_title( $home_id ) . ' (#' . $home_id . ') at ' . home_url( '/' ) );
	} else {
		WP_CLI::warning( 'No front page was set: the bundle has no page with slug "' . $home . '".' );
	}

	$total_changed = $stats['terms_created'] + $stats['posts_created'] + $stats['posts_updated']
		+ $stats['menu_created_items'] + $stats['menu_updated'] + $stats['menu_removed']
		+ $stats['navigation_created'] + $stats['navigation_updated'] + $stats['options']
		+ $stats['defaults_removed'];

	if ( 0 === $total_changed ) {
		WP_CLI::success( 'Already seeded — nothing to change.' );
		return;
	}

	WP_CLI::success( 'Seeded. ' . $total_changed . ' change(s) written.' );
}

maars_seed_run( isset( $args ) && is_array( $args ) ? $args : array() );
