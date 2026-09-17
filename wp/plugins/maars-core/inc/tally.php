<?php
/**
 * The archive, counted rather than remembered.
 *
 * Why this file exists
 * --------------------
 * The archive templates were written during the study of ks0man.com, when the
 * catalogue said 266 dated documents. The site that shipped holds 242 of them:
 * twenty-four are third-party material that is not the Society's to republish.
 * So every hand-written total in the theme -- "266 items", "14 pages in all",
 * "Back to all 266 documents" -- was wrong the moment real content arrived, and
 * wrong in the worst way: confidently, in the club's own voice, on the page that
 * exists to say what the record contains.
 *
 * Numbers in prose go stale. These do not: each one is counted out of the
 * database at render time. The prose stays in the theme templates where it can
 * be read and edited as prose; only the figures come from here, as shortcodes.
 *
 * Shortcodes are processed in block templates: get_the_block_template_html()
 * calls do_shortcode() on the template content (wp-includes/block-template.php,
 * WordPress 7.1). That is checked by a test, not assumed, because the whole
 * point of this file is to stop trusting things that were true once.
 *
 * @package MAARS
 */

defined( 'ABSPATH' ) || exit;

/**
 * How many publications the public can actually read.
 *
 * @return int Published maars_publication posts.
 */
function maars_archive_total(): int {
	if ( ! function_exists( 'wp_count_posts' ) || ! post_type_exists( 'maars_publication' ) ) {
		return 0;
	}

	$counts = wp_count_posts( 'maars_publication' );

	return isset( $counts->publish ) ? (int) $counts->publish : 0;
}

/**
 * Every year the archive actually has something in, oldest first.
 *
 * Read off the maars_year taxonomy, whose term counts include published posts
 * only, so a year that exists as a term but holds nothing is not a year the
 * archive covers.
 *
 * @return int[] Four-digit years, ascending.
 */
function maars_archive_years(): array {
	if ( ! function_exists( 'get_terms' ) || ! taxonomy_exists( 'maars_year' ) ) {
		return array();
	}

	$terms = get_terms(
		array(
			'taxonomy'   => 'maars_year',
			'hide_empty' => true,
		)
	);

	if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
		return array();
	}

	$years = array();
	foreach ( $terms as $term ) {
		$name = is_object( $term ) ? (string) $term->name : (string) $term;
		if ( preg_match( '/^(1[89]\d{2}|2\d{3})$/', trim( $name ) ) ) {
			$years[] = (int) $name;
		}
	}

	$years = array_values( array_unique( $years ) );
	sort( $years );

	return $years;
}

/**
 * First and last year of the record.
 *
 * @return array{0:int,1:int}|array{} Empty when the archive is empty.
 */
function maars_archive_span(): array {
	$years = maars_archive_years();
	if ( ! $years ) {
		return array();
	}

	return array( $years[0], $years[ count( $years ) - 1 ] );
}

/**
 * Years inside the span that produced nothing at all.
 *
 * A gap is a finding about the club's history, not a bug in the import: 2012
 * genuinely produced no surviving document. Deriving it means the page can
 * never claim a gap that has since been filled, nor hide one that opened.
 *
 * @return int[] Missing years, ascending.
 */
function maars_archive_gap_years(): array {
	$years = maars_archive_years();
	if ( count( $years ) < 2 ) {
		return array();
	}

	$have = array_flip( $years );
	$gaps = array();
	for ( $y = $years[0]; $y <= $years[ count( $years ) - 1 ]; $y++ ) {
		if ( ! isset( $have[ $y ] ) ) {
			$gaps[] = $y;
		}
	}

	return $gaps;
}

/**
 * How many of each kind of document, largest kind first.
 *
 * @return array<int, array{slug:string,name:string,plural:string,count:int}>
 */
function maars_archive_kind_counts(): array {
	if ( ! function_exists( 'get_terms' ) || ! taxonomy_exists( 'maars_doc_type' ) ) {
		return array();
	}

	$terms = get_terms(
		array(
			'taxonomy'   => 'maars_doc_type',
			'hide_empty' => true,
			'orderby'    => 'count',
			'order'      => 'DESC',
		)
	);

	if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
		return array();
	}

	$vocabulary = function_exists( 'maars_doc_type_terms' ) ? maars_doc_type_terms() : array();

	$out = array();
	foreach ( $terms as $term ) {
		if ( ! is_object( $term ) || (int) $term->count < 1 ) {
			continue;
		}

		$slug   = (string) $term->slug;
		$name   = (string) $term->name;
		$plural = isset( $vocabulary[ $slug ]['plural'] ) ? (string) $vocabulary[ $slug ]['plural'] : '';

		if ( '' === $plural ) {
			/* A term the club added itself. Lower-case it and add an s, unless it already ends in one. */
			$lower  = function_exists( 'mb_strtolower' ) ? mb_strtolower( $name, 'UTF-8' ) : strtolower( $name );
			$plural = ( 's' === substr( $lower, -1 ) ) ? $lower : $lower . 's';
		}

		$out[] = array(
			'slug'   => $slug,
			'name'   => $name,
			'plural' => $plural,
			'count'  => (int) $term->count,
		);
	}

	return $out;
}

/**
 * Pages the archive list runs to at a given page size.
 *
 * @param int $per_page Rows per page.
 * @return int Pages, at least 1 when there is anything at all.
 */
function maars_archive_pages( int $per_page = 20 ): int {
	if ( $per_page < 1 ) {
		$per_page = 20;
	}

	$total = maars_archive_total();

	return $total > 0 ? (int) ceil( $total / $per_page ) : 0;
}

/**
 * Join a list the way a person would say it: "a, b and c".
 *
 * @param string[] $items List items, already escaped.
 * @return string
 */
function maars_tally_join( array $items ): string {
	$items = array_values(
		array_filter(
			$items,
			static function ( $item ) {
				return '' !== trim( (string) $item );
			}
		)
	);

	$count = count( $items );
	if ( 0 === $count ) {
		return '';
	}
	if ( 1 === $count ) {
		return $items[0];
	}

	$last = array_pop( $items );

	return sprintf(
		/* translators: 1: comma-separated list, 2: the last item. */
		_x( '%1$s and %2$s', 'list of things', 'maars' ),
		implode( ', ', $items ),
		$last
	);
}

/**
 * [maars_archive_count] -- how many documents are in the archive.
 *
 * @return string
 */
function maars_tally_shortcode_count(): string {
	$total = maars_archive_total();

	return esc_html( function_exists( 'number_format_i18n' ) ? number_format_i18n( $total ) : (string) $total );
}

/**
 * [maars_archive_span] -- "1998 to 2024", or a single year, or nothing.
 *
 * @return string
 */
function maars_tally_shortcode_span(): string {
	$span = maars_archive_span();
	if ( ! $span ) {
		return '';
	}

	if ( $span[0] === $span[1] ) {
		return esc_html( (string) $span[0] );
	}

	return sprintf(
		/* translators: 1: first year, 2: last year. */
		esc_html__( '%1$s to %2$s', 'maars' ),
		esc_html( (string) $span[0] ),
		esc_html( (string) $span[1] )
	);
}

/**
 * [maars_archive_first_year] -- the year the record starts.
 *
 * @return string
 */
function maars_tally_shortcode_first_year(): string {
	$span = maars_archive_span();

	return $span ? esc_html( (string) $span[0] ) : '';
}

/**
 * [maars_archive_last_year] -- the year the record reaches.
 *
 * @return string
 */
function maars_tally_shortcode_last_year(): string {
	$span = maars_archive_span();

	return $span ? esc_html( (string) $span[1] ) : '';
}

/**
 * [maars_archive_kinds] -- "121 newsletters, 66 sets of meeting minutes ...".
 *
 * @return string
 */
function maars_tally_shortcode_kinds(): string {
	$phrases = array();
	foreach ( maars_archive_kind_counts() as $kind ) {
		$phrases[] = sprintf(
			/* translators: 1: a count, 2: plural name of a kind of document. */
			esc_html__( '%1$s %2$s', 'maars' ),
			esc_html( function_exists( 'number_format_i18n' ) ? number_format_i18n( $kind['count'] ) : (string) $kind['count'] ),
			esc_html( $kind['plural'] )
		);
	}

	return maars_tally_join( $phrases );
}

/**
 * [maars_archive_pages per_page="20"] -- how many pages the list runs to.
 *
 * @param array|string $atts Shortcode attributes.
 * @return string
 */
function maars_tally_shortcode_pages( $atts = array() ): string {
	$atts     = shortcode_atts( array( 'per_page' => '20' ), is_array( $atts ) ? $atts : array(), 'maars_archive_pages' );
	$per_page = (int) $atts['per_page'];
	$pages    = maars_archive_pages( $per_page > 0 ? $per_page : 20 );

	return esc_html( function_exists( 'number_format_i18n' ) ? number_format_i18n( $pages ) : (string) $pages );
}

/**
 * [maars_archive_gap_years] -- "2012 and 2014", or nothing at all.
 *
 * @return string
 */
function maars_tally_shortcode_gap_years(): string {
	$years = maars_archive_gap_years();
	if ( ! $years ) {
		return '';
	}

	/*
	 * Runs become ranges. A club that stopped publishing for a decade should
	 * read as "2000 to 2011", not as twelve years listed one after another;
	 * the long form is what this said before the whole record was imported,
	 * and it was unreadable.
	 */
	$parts = array();
	$start = $years[0];
	$prev  = $years[0];

	foreach ( array_slice( $years, 1 ) as $year ) {
		if ( $year === $prev + 1 ) {
			$prev = $year;
			continue;
		}
		$parts[] = maars_tally_year_run( $start, $prev );
		$start   = $year;
		$prev    = $year;
	}
	$parts[] = maars_tally_year_run( $start, $prev );

	return maars_tally_join( $parts );
}

/**
 * One gap, as a year or as a range.
 *
 * @param int $start First year of the run.
 * @param int $end   Last year of the run.
 * @return string
 */
function maars_tally_year_run( int $start, int $end ): string {
	if ( $start === $end ) {
		return esc_html( (string) $start );
	}

	if ( $end === $start + 1 ) {
		/* Two years read better as a pair than as a range. */
		return sprintf(
			/* translators: 1: a year, 2: the following year. */
			esc_html__( '%1$s and %2$s', 'maars' ),
			esc_html( (string) $start ),
			esc_html( (string) $end )
		);
	}

	return sprintf(
		/* translators: 1: first year of a run, 2: last year of a run. */
		esc_html__( '%1$s to %2$s', 'maars' ),
		esc_html( (string) $start ),
		esc_html( (string) $end )
	);
}

/**
 * [maars_archive_gaps] -- the whole sentence, or nothing.
 *
 * A sentence rather than a list, because "2012 and 2014 produced nothing at
 * all." has to disappear entirely on the day someone finds the 2012 minutes,
 * and a bare list left in the prose would leave " produced nothing at all."
 * behind it.
 *
 * @return string
 */
function maars_tally_shortcode_gaps(): string {
	$years = maars_archive_gap_years();
	if ( ! $years ) {
		return '';
	}

	$list = maars_tally_shortcode_gap_years();

	return sprintf(
		/* translators: %s: one or more years, e.g. "2012 and 2014". */
		esc_html( _n( '%s produced nothing at all.', '%s produced nothing at all.', count( $years ), 'maars' ) ),
		$list
	);
}

/**
 * [maars_archive_newest] -- the date on the newest document of any kind.
 *
 * @return string
 */
function maars_tally_shortcode_newest(): string {
	$date = '';
	if ( function_exists( 'maars_last_publication_date' ) ) {
		$date = (string) maars_last_publication_date();
	}

	if ( '' === $date ) {
		return esc_html__( 'not yet recorded', 'maars' );
	}

	if ( function_exists( 'maars_blocks_format_date' ) ) {
		return esc_html( maars_blocks_format_date( $date ) );
	}

	return esc_html( $date );
}

/**
 * Documents held for each year of the record.
 *
 * @return array<int,int> Year => count, ascending, including the empty years.
 */
function maars_archive_year_counts(): array {
	if ( ! function_exists( 'get_terms' ) || ! taxonomy_exists( 'maars_year' ) ) {
		return array();
	}

	$terms = get_terms(
		array(
			'taxonomy'   => 'maars_year',
			'hide_empty' => true,
		)
	);

	if ( is_wp_error( $terms ) || ! is_array( $terms ) ) {
		return array();
	}

	$counts = array();
	foreach ( $terms as $term ) {
		if ( ! is_object( $term ) || ! preg_match( '/^(1[89]\d{2}|2\d{3})$/', trim( (string) $term->name ) ) ) {
			continue;
		}
		$counts[ (int) $term->name ] = (int) $term->count;
	}

	if ( ! $counts ) {
		return array();
	}

	/* Fill the span, so an empty year is a row that says none rather than a row that is not there. */
	$years = array_keys( $counts );
	sort( $years );
	$filled = array();
	for ( $y = $years[0]; $y <= $years[ count( $years ) - 1 ]; $y++ ) {
		$filled[ $y ] = isset( $counts[ $y ] ) ? $counts[ $y ] : 0;
	}

	return $filled;
}

/**
 * [maars_archive_year_table] -- the record, year by year, gaps included.
 *
 * Two columns and no third: a "read the year" link repeated down twenty-seven
 * rows is the placeholder sentence this project already removed from the
 * archive log once, so the year itself is the link and carries the count
 * beside it. The count cell is ruled to the width of its own number against
 * the fullest year, which makes a thin year visible as a shape before it is
 * read as a figure -- and a gap, having no bar at all, unmissable.
 *
 * @return string
 */
function maars_tally_shortcode_year_table(): string {
	$counts = maars_archive_year_counts();
	if ( ! $counts ) {
		return '';
	}

	$most = max( $counts );
	$most = $most > 0 ? $most : 1;

	$rows = '';
	foreach ( $counts as $year => $count ) {
		$empty = ( 0 === $count );
		$width = (int) round( ( $count / $most ) * 100 );

		$year_cell = $empty
			? esc_html( (string) $year )
			: sprintf(
				'<a href="%1$s">%2$s</a>',
				esc_url( home_url( '/archive/' . $year . '/' ) ),
				esc_html( (string) $year )
			);

		$count_cell = $empty
			? esc_html__( 'none', 'maars' )
			: esc_html( function_exists( 'number_format_i18n' ) ? number_format_i18n( $count ) : (string) $count );

		$rows .= sprintf(
			'<tr class="maars-yeartable__row%1$s"><th scope="row" class="maars-yeartable__year">%2$s</th>'
			. '<td class="maars-yeartable__count" style="--maars-bar:%3$d%%">%4$s</td></tr>',
			$empty ? ' maars-yeartable__row--empty' : '',
			$year_cell,
			$width,
			$count_cell
		);
	}

	return '<figure class="maars-yeartable__wrap"><table class="maars-yeartable">'
		. '<caption class="maars-yeartable__caption">' . esc_html__( 'Documents held, year by year, measured against the fullest year. A year marked "none" is a gap in the record itself, not a gap in this website.', 'maars' ) . '</caption>'
		. '<thead><tr><th scope="col">' . esc_html__( 'Year', 'maars' ) . '</th>'
		. '<th scope="col">' . esc_html__( 'Documents', 'maars' ) . '</th></tr></thead>'
		. '<tbody>' . $rows . '</tbody></table></figure>';
}

/**
 * Register the archive shortcodes.
 *
 * @return void
 */
function maars_register_tally_shortcodes(): void {
	if ( ! function_exists( 'add_shortcode' ) ) {
		return;
	}

	add_shortcode( 'maars_archive_count', 'maars_tally_shortcode_count' );
	add_shortcode( 'maars_archive_span', 'maars_tally_shortcode_span' );
	add_shortcode( 'maars_archive_first_year', 'maars_tally_shortcode_first_year' );
	add_shortcode( 'maars_archive_last_year', 'maars_tally_shortcode_last_year' );
	add_shortcode( 'maars_archive_kinds', 'maars_tally_shortcode_kinds' );
	add_shortcode( 'maars_archive_pages', 'maars_tally_shortcode_pages' );
	add_shortcode( 'maars_archive_gap_years', 'maars_tally_shortcode_gap_years' );
	add_shortcode( 'maars_archive_gaps', 'maars_tally_shortcode_gaps' );
	add_shortcode( 'maars_archive_newest', 'maars_tally_shortcode_newest' );
	add_shortcode( 'maars_archive_year_table', 'maars_tally_shortcode_year_table' );
}
add_action( 'init', 'maars_register_tally_shortcodes', 10 );
