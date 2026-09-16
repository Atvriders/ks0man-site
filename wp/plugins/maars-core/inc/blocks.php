<?php
/**
 * MAARS core — server-rendered blocks.
 *
 * Five dynamic blocks, registered in plain PHP with render callbacks.
 * There is deliberately NO JavaScript build step, no block.json bundler and no
 * editor script: everything here is produced on the server so the markup is the
 * same for a browser, a screen reader and curl.
 *
 * Design rule for every block in this file: staleness is visible, never hidden.
 * A date is shown together with the rule that produced it; a fact is shown
 * together with how well it is known; an archive with nothing in it says so
 * instead of printing a confident zero.
 *
 * -------------------------------------------------------------------------
 * VISUAL SYSTEM — revision 2 (see DESIGN.md)
 * -------------------------------------------------------------------------
 * Revision 1 shouted. Every block wore a tracked-out ALL-CAPS eyebrow, every
 * fact carried a bordered coloured chip, and a prose date was set in the data
 * face so it read like a part number. Revision 2 takes all of that off. The
 * rules this file now renders to:
 *
 *   1. NO EYEBROWS. Nothing in this file emits a shouted label above a value.
 *      The heading above the block already says what the block is; a second
 *      label in capitals is noise at the exact size a 78-year-old is trying to
 *      read past. Where a label is still owed to a screen reader and nowhere
 *      else, it goes in .screen-reader-text.
 *
 *   2. THE DATA FACE IS FOR FIGURES ONLY. <span class="maars-fig"> — Fira Code
 *      with tabular, natively slashed zeros — goes on callsigns, frequencies,
 *      tones, offsets, counts and money, so KSØMAN is written the way a ham
 *      writes it and a column of numbers lines up. It does NOT go on prose.
 *      "Friday, October 9, 2026 at 6:30 P.M." and "12 January 2024" are
 *      sentences; they stay in the body face. maars_blocks_fig() marks a
 *      figure; maars_blocks_fig_date() emits a machine-readable <time> whose
 *      visible text is ordinary prose.
 *
 *   3. NO MIDDLE DOTS. Nothing here joins values with an interpunct. A
 *      specification is a list of labelled values or a sentence with real
 *      punctuation, never a string of fragments stitched together.
 *
 *   4. THE PROVENANCE LINE IS FURNITURE. One quiet line under the value: the
 *      grade word, then when it was last checked and how long ago. No border
 *      of its own, no internal archive path — that is a record locator for
 *      whoever maintains the site, so it lives in a title attribute and
 *      nowhere a club member has to read it.
 *
 *   5. THE NEXT MEETING IS FIRST AND LARGEST. maars/next-meeting renders the
 *      date as its own line, first, with the governing rule beneath it small
 *      and quiet. It is not a row in a log; it must not look like one.
 *
 * CLASS VOCABULARY EMITTED BY THIS FILE. The stylesheet
 * (wp/themes/maars/assets/css/maars.css) is expected to style exactly these,
 * and this file emits no class the stylesheet does not need:
 *
 *   .maars-fig                     the data face + tabular figures. Always on a
 *                                  <span>. Figures only — never prose.
 *   .maars-log                     a group of rows, separated by a hairline
 *                                  rule rather than boxed. The only user left
 *                                  in this file is the skywave band list, which
 *                                  is a real list of rows.
 *   .maars-log__line               one row in such a group.
 *   .maars-next-meeting            + --unknown/.is-unknown, __date, __rule,
 *                                  __rule-text. No __eyebrow and no __rule-tag
 *                                  any more: both were shouted labels.
 *   .maars-dateline                + --fresh/.is-fresh, --stale/.is-stale,
 *                                  --empty/.is-empty, __headline, __detail;
 *                                  also data-state, data-maars-days,
 *                                  data-maars-threshold
 *   .maars-fact                    + --measured/--sourced/--unverified,
 *                                  .is-stale, __body, __chip, __chip--<grade>,
 *                                  __grade, __detail, __checked; also
 *                                  data-grade and data-verified-on
 *   .maars-skywave                 + --fallback, __canvas, __controls,
 *                                  __control, __control-band, __control-freq,
 *                                  __caption, __chip, __fallback,
 *                                  __fallback-title, __prose, __noscript,
 *                                  __bands, __band, __band--<id>
 *   .maars-masthead                + --fallback, __canvas, __identity,
 *                                  __call, __long, __tuned; also
 *                                  data-maars-autostart
 *   .screen-reader-text            the theme's visually-hidden class
 *
 * The freshness chip is a LABEL, never an alert. The grade word carries the
 * meaning on its own — no emoji, no bare coloured dot, nothing a reader with
 * any colour vision can miss — and the date beside it says how old the claim
 * is. "Unverified" is an honest description of the evidence, not a siren, and
 * what each grade means is explained once on the page rather than repeated
 * beside every fact.
 *
 * ESCAPING CONVENTION. Every string reaching the browser is escaped at the
 * point it is built. A variable whose name ends in `_html` already holds
 * escaped markup and must not be escaped again; everything else is passed
 * through esc_html()/esc_attr() on output. Translated strings that carry a
 * placeholder are escaped first (esc_html__) and then sprintf()'d with
 * already-escaped fragments, so neither half can smuggle markup. Inner block
 * content goes through wp_kses_post().
 *
 * @package maars
 */

defined( 'ABSPATH' ) || exit;

/**
 * Register the five MAARS blocks.
 *
 * Hooked to init at priority 10 (see the interface contract). Registration is
 * dynamic: 'api_version' => 3 plus a 'render_callback', no asset handles.
 *
 * @return void
 */
function maars_register_blocks() {
	if ( ! function_exists( 'register_block_type' ) ) {
		return;
	}

	register_block_type( 'maars/next-meeting', array(
		'api_version'     => 3,
		'title'           => __( 'Next meeting', 'maars' ),
		'description'     => __( 'The next meeting date, computed from the Society SOP rule, with the rule printed underneath so a reader can see the date was derived rather than typed.', 'maars' ),
		'category'        => 'widgets',
		'icon'            => 'calendar-alt',
		'keywords'        => array( 'meeting', 'calendar', 'maars' ),
		'supports'        => array(
			'html'   => false,
			'anchor' => true,
		),
		'attributes'      => array(
			'label'    => array(
				'type'    => 'string',
				'default' => '',
			),
			'showRule' => array(
				'type'    => 'boolean',
				'default' => true,
			),
		),
		'render_callback' => 'maars_render_next_meeting_block',
	) );

	register_block_type( 'maars/dateline', array(
		'api_version'     => 3,
		'title'           => __( 'Dateline', 'maars' ),
		'description'     => __( 'How long it has been since the club last published anything. Goes to the alarm state past the freshness threshold.', 'maars' ),
		'category'        => 'widgets',
		'icon'            => 'clock',
		'keywords'        => array( 'stale', 'freshness', 'dateline', 'maars' ),
		'supports'        => array(
			'html'   => false,
			'anchor' => true,
		),
		'attributes'      => array(
			'threshold' => array(
				'type'    => 'number',
				'default' => 120,
			),
			'showDate'  => array(
				'type'    => 'boolean',
				'default' => true,
			),
		),
		'render_callback' => 'maars_render_dateline_block',
	) );

	register_block_type( 'maars/fact', array(
		'api_version'     => 3,
		'title'           => __( 'Fact', 'maars' ),
		'description'     => __( 'Wraps a statement with the freshness grade it earned: measured, sourced or unverified.', 'maars' ),
		'category'        => 'text',
		'icon'            => 'info-outline',
		'keywords'        => array( 'fact', 'freshness', 'grade', 'maars' ),
		'supports'        => array(
			'html'   => false,
			'anchor' => true,
		),
		'uses_context'    => array( 'postId' ),
		'attributes'      => array(
			'grade'      => array(
				'type'    => 'string',
				'default' => '',
			),
			'verifiedOn' => array(
				'type'    => 'string',
				'default' => '',
			),
			'sourceFile' => array(
				'type'    => 'string',
				'default' => '',
			),
		),
		'render_callback' => 'maars_render_fact_block',
	) );

	register_block_type( 'maars/skywave', array(
		'api_version'     => 3,
		'title'           => __( 'Skywave', 'maars' ),
		'description'     => __( 'WebGL2 skywave propagation diagram launched from Manhattan, Kansas, with a static fallback for browsers without WebGL2 and a noscript fallback for browsers without JavaScript.', 'maars' ),
		'category'        => 'media',
		'icon'            => 'admin-site-alt3',
		'keywords'        => array( 'propagation', 'ionosphere', 'webgl', 'maars' ),
		'supports'        => array(
			'html'   => false,
			'anchor' => true,
			'align'  => array( 'wide', 'full' ),
		),
		'attributes'      => array(
			'band'      => array(
				'type'    => 'string',
				'default' => '80m',
			),
			'width'     => array(
				'type'    => 'number',
				'default' => 1280,
			),
			'height'    => array(
				'type'    => 'number',
				'default' => 720,
			),
			'caption'   => array(
				'type'    => 'string',
				'default' => '',
			),
			'autostart' => array(
				'type'    => 'boolean',
				'default' => true,
			),
		),
		'render_callback' => 'maars_render_skywave_block',
	) );

	register_block_type( 'maars/masthead', array(
		'api_version'     => 3,
		'title'           => __( 'Masthead', 'maars' ),
		'description'     => __( 'The head of the site as a 2 metre receiver: a spectrum trace and waterfall tuned to the Society\'s own repeater, with the identity resting in it as real text. Decorative, and it says so.', 'maars' ),
		'category'        => 'design',
		'icon'            => 'chart-area',
		'keywords'        => array( 'masthead', 'header', 'waterfall', 'identity', 'maars' ),
		'supports'        => array(
			'html'   => false,
			'anchor' => true,
			'align'  => array( 'full' ),
		),
		'attributes'      => array(
			'callsign'  => array(
				'type'    => 'string',
				'default' => '',
			),
			'society'   => array(
				'type'    => 'string',
				'default' => '',
			),
			'height'    => array(
				'type'    => 'number',
				'default' => 180,
			),
			'autostart' => array(
				'type'    => 'boolean',
				'default' => true,
			),
		),
		'render_callback' => 'maars_render_masthead_block',
	) );
}
add_action( 'init', 'maars_register_blocks', 10 );

/* -------------------------------------------------------------------------
 * Shared helpers (all prefixed maars_blocks_ so they cannot collide with the
 * contract's public API).
 * ---------------------------------------------------------------------- */

/**
 * Wrapper attributes for a dynamic block, with a graceful fallback.
 *
 * @param array $extra Extra attributes, e.g. array( 'class' => 'maars-fact' ).
 * @return string Attribute string ready to drop into a tag.
 */
function maars_blocks_wrapper_attributes( array $extra = array() ): string {
	/*
	 * Only 'class' and 'style' are handed to core. get_block_wrapper_attributes()
	 * is documented around those two, and relying on it to echo arbitrary
	 * data-* attributes makes the markup depend on an implementation detail that
	 * has moved between releases. A dropped data-maars-autostart is silent and
	 * fatal: the bootstrap selector matches nothing and the canvas never mounts,
	 * leaving a blank box with no error. So emit them ourselves, always.
	 */
	$passthrough = array();
	foreach ( $extra as $key => $value ) {
		if ( 'class' !== $key && 'style' !== $key ) {
			$passthrough[ $key ] = $value;
			unset( $extra[ $key ] );
		}
	}

	if ( function_exists( 'get_block_wrapper_attributes' ) ) {
		$out = get_block_wrapper_attributes( $extra );
	} else {
		$parts = array();
		foreach ( $extra as $key => $value ) {
			$parts[] = esc_attr( (string) $key ) . '="' . esc_attr( (string) $value ) . '"';
		}
		$out = implode( ' ', $parts );
	}

	foreach ( $passthrough as $key => $value ) {
		$out .= ( '' === $out ? '' : ' ' ) . esc_attr( (string) $key ) . '="' . esc_attr( (string) $value ) . '"';
	}

	return $out;
}

/**
 * Wrap a figure — a callsign, frequency, tone, offset, count or dollar amount —
 * so it renders in the data face with tabular figures.
 *
 * This is the site's typographic signature and the reason it is a function
 * rather than a hand-written span: applied unevenly it reads as a mistake, and
 * a frequency in the body face has an unslashed zero that an older reader can
 * mistake for the letter O. Anything that would be written in a logbook COLUMN
 * goes through here.
 *
 * What does NOT go through here is prose. A date written out in words is a
 * sentence — "Friday, October 9, 2026 at 6:30 P.M.", "12 January 2024" — and
 * setting a sentence in Fira Code makes it look like a serial number. That was
 * revision 1's mistake and it is the reason this docblock is emphatic.
 *
 * @param string $text Plain text figure. Escaped here; never pass markup.
 * @return string Escaped markup, or '' for an empty figure.
 */
function maars_blocks_fig( $text ): string {
	$text = is_scalar( $text ) ? trim( (string) $text ) : '';

	if ( '' === $text ) {
		return '';
	}

	return '<span class="maars-fig">' . esc_html( $text ) . '</span>';
}

/**
 * A date as a machine-readable <time> whose visible text is ordinary prose.
 *
 * The <time> carries the ISO day for anything parsing the page. The visible
 * text does NOT get the data face: "12 January 2024" is a sentence fragment,
 * not a figure, and revision 1 set it in Fira Code, which made every
 * provenance line read like a part number. The function keeps its historical
 * name because the contract freezes the names in this file; only what it emits
 * has changed.
 *
 * @param string $ymd Date in YYYY-MM-DD form.
 * @return string Escaped markup, or '' when the date is not a real day.
 */
function maars_blocks_fig_date( $ymd ): string {
	$ymd = maars_blocks_normalize_date( $ymd );

	if ( '' === $ymd ) {
		return '';
	}

	$display = maars_blocks_format_date( $ymd );

	if ( '' === $display ) {
		$display = $ymd;
	}

	return '<time datetime="' . esc_attr( $ymd ) . '">' . esc_html( $display ) . '</time>';
}

/**
 * Put the club's callsign into the data face inside an already-escaped string.
 *
 * KSØMAN is written with a slashed zero on the repeater plate, in the minutes
 * and on every QSL card, and Fira Code is the face that draws it that way. The
 * callsign reaches this file inside translated sentences (the 2 m band label,
 * which is also handed to skywave.js verbatim and therefore must not be split
 * up at the source), so the only honest place to mark it is in the rendered
 * output.
 *
 * Input must already be escaped: the replacement is a literal token containing
 * no HTML-special characters, so the only markup this can introduce is the
 * span it adds. Call it once per string — a second pass would nest spans.
 *
 * It does not parse HTML, so it must only ever see plain escaped text. Run it
 * over arbitrary markup and a callsign living inside an attribute — an href, an
 * alt, a title — would have a <span> spliced into the middle of that attribute
 * and the tag would break. That is why block inner content, which arrives as
 * author HTML through wp_kses_post(), is left alone here: figures inside a
 * fact's prose are marked up in the template that writes the prose.
 *
 * @param string $escaped_html Already-escaped text.
 * @return string Escaped markup.
 */
function maars_blocks_mark_callsign( string $escaped_html ): string {
	/* Both spellings: the slashed form the club uses, and the plain zero that
	   appears in file names and in anything typed on a keyboard. */
	foreach ( array( 'KSØMAN', 'KS0MAN' ) as $call ) {
		if ( false === strpos( $escaped_html, $call ) ) {
			continue;
		}

		$escaped_html = str_replace(
			$call,
			'<span class="maars-fig">' . $call . '</span>',
			$escaped_html
		);
	}

	return $escaped_html;
}

/**
 * The three freshness grades this site recognises.
 *
 * @return array<int,string>
 */
function maars_blocks_grades(): array {
	return array( 'measured', 'sourced', 'unverified' );
}

/**
 * Reduce an arbitrary string to a known grade, or '' if it is not one.
 *
 * @param mixed $grade Candidate grade.
 * @return string One of measured|sourced|unverified, or ''.
 */
function maars_blocks_normalize_grade( $grade ): string {
	$grade = is_string( $grade ) ? strtolower( trim( $grade ) ) : '';

	return in_array( $grade, maars_blocks_grades(), true ) ? $grade : '';
}

/**
 * Human label for a grade. This word is the whole signal: it has to carry the
 * meaning with no colour, no icon and no shape helping it.
 *
 * @param string $grade Normalised grade.
 * @return string Translated label.
 */
function maars_blocks_grade_label( string $grade ): string {
	switch ( $grade ) {
		case 'measured':
			return __( 'Measured', 'maars' );
		case 'sourced':
			return __( 'Sourced', 'maars' );
		default:
			return __( 'Unverified', 'maars' );
	}
}

/**
 * One sentence explaining what a grade means, in plain language.
 *
 * Written flat and calm on purpose. "Unverified" is a description of the
 * evidence behind a line in the record, not an error the reader has to act on.
 *
 * Revision 2 no longer prints this beside every fact — the page explains the
 * three grades once, in one place, and repeating it under each row was most of
 * why the homepage ran to 6,363 pixels. It survives here as the text of the
 * chip's title attribute.
 *
 * @param string $grade Normalised grade.
 * @return string Translated sentence.
 */
function maars_blocks_grade_meaning( string $grade ): string {
	switch ( $grade ) {
		case 'measured':
			return __( 'Checked against the thing itself.', 'maars' );
		case 'sourced':
			return __( 'Taken from a club document.', 'maars' );
		default:
			return __( 'Nobody has confirmed this. Treat it as history, not as current.', 'maars' );
	}
}

/**
 * The freshness chip: ONE quiet line under the value it describes.
 *
 * Revision 1 made this a bordered, coloured, three-column box carrying a title,
 * a sentence, an internal archive path and a date, which outweighed the fact it
 * was grading. It is furniture, not an alarm. What is left is the grade word
 * and when the claim was last checked:
 *
 *     Sourced. Last checked 12 January 2024 — 977 days ago.
 *
 * The grade word carries the meaning on its own, so the line survives
 * greyscale, deuteranopia and a photocopy. What each grade means is stated once
 * on the page; it is not repeated beside every fact. Anything a maintainer
 * needs and a reader does not — the archive path a claim came out of — goes in
 * $title, where it is available to whoever is chasing provenance and invisible
 * to everybody else.
 *
 * The chip is a paragraph inside a maars/fact card and an inline span inside
 * the skywave caption, which is why the tag is a parameter.
 *
 * @param string $grade        Normalised grade; anything unknown reads as unverified.
 * @param string $detail_html  Already-escaped markup: an extra clause, or '' for none.
 * @param string $checked_html Already-escaped markup: when it was last checked. '' omits it.
 * @param string $tag          'p' (default) or 'span'.
 * @param string $extra_class  Extra class for the chip element, already trusted.
 * @param string $title        Plain text for the title attribute: provenance for a
 *                             maintainer. Escaped here. '' omits the attribute.
 * @return string Escaped markup.
 */
function maars_blocks_chip( string $grade, string $detail_html, string $checked_html = '', string $tag = 'p', string $extra_class = '', string $title = '' ): string {
	$grade = maars_blocks_normalize_grade( $grade );

	if ( '' === $grade ) {
		$grade = 'unverified';
	}

	$tag = ( 'span' === $tag ) ? 'span' : 'p';

	/*
	 * No .maars-log__line, and no label/value/note column classes. This is a
	 * sentence, not a row in a table, and the column classes are what turned the
	 * grade word into a tracked-out capital label in revision 1.
	 */
	$classes = 'maars-fact__chip maars-fact__chip--' . $grade;
	if ( '' !== $extra_class ) {
		$classes = $extra_class . ' ' . $classes;
	}

	$out = '<' . $tag . ' class="' . esc_attr( $classes ) . '" data-grade="' . esc_attr( $grade ) . '"';

	if ( '' !== trim( $title ) ) {
		$out .= ' title="' . esc_attr( trim( $title ) ) . '"';
	}

	$out .= '>';

	/* The full stop is load-bearing in exactly one way: it makes the grade word
	   read as the first sentence of a quiet line rather than as a label stuck to
	   the front of the next one. */
	$out .= '<span class="maars-fact__grade">' . esc_html( maars_blocks_grade_label( $grade ) ) . '.</span>';

	if ( '' !== $detail_html ) {
		$out .= ' <span class="maars-fact__detail">' . $detail_html . '</span>';
	}

	if ( '' !== $checked_html ) {
		$out .= ' <span class="maars-fact__checked">' . $checked_html . '</span>';
	}

	$out .= '</' . $tag . '>';

	return $out;
}

/**
 * Accept a real calendar day written YYYY-MM-DD, reject anything else.
 *
 * Delegates to maars_valid_ymd() in inc/freshness.php when that module is
 * loaded, so the same date string cannot be judged valid by one file and
 * invalid by another. The inline copy is the identical test — shape AND
 * checkdate() — and exists only so this file still behaves correctly if it is
 * ever loaded on its own.
 *
 * The checkdate() half matters: without it '2024-02-31' passes the shape test,
 * and mysql2date() then prints it as "March 2, 2024". A fabricated verification
 * date is exactly the kind of quiet wrongness this site exists to prevent.
 *
 * @param mixed $date Candidate date.
 * @return string The date, or ''.
 */
function maars_blocks_normalize_date( $date ): string {
	if ( function_exists( 'maars_valid_ymd' ) ) {
		return maars_valid_ymd( $date );
	}

	$date = is_string( $date ) ? trim( $date ) : '';

	if ( ! preg_match( '/^(\d{4})-(\d{2})-(\d{2})$/', $date, $m ) ) {
		return '';
	}

	return checkdate( (int) $m[2], (int) $m[3], (int) $m[1] ) ? $date : '';
}

/**
 * Format a YYYY-MM-DD string for display using the site's date format.
 *
 * @param string $date Normalised date.
 * @return string Formatted date, or ''.
 */
function maars_blocks_format_date( string $date ): string {
	if ( '' === $date ) {
		return '';
	}

	$format = function_exists( 'get_option' ) ? (string) get_option( 'date_format' ) : '';
	$format = '' !== $format ? $format : 'F j, Y';

	if ( function_exists( 'mysql2date' ) ) {
		$formatted = mysql2date( $format, $date . ' 12:00:00' );
		if ( is_string( $formatted ) && '' !== $formatted ) {
			return $formatted;
		}
	}

	return $date;
}

/**
 * Timestamp (UTC) of the newest published item the public can actually read.
 *
 * Used only to decide whether the archive is empty and to print the newest
 * item's date; the day count itself comes from maars_days_since_last_publication().
 *
 * @return int|null Unix timestamp, or null when nothing is published.
 */
function maars_blocks_latest_publication_time(): ?int {
	if ( ! function_exists( 'get_posts' ) || ! function_exists( 'post_type_exists' ) ) {
		return null;
	}

	$types = array();
	foreach ( array( 'maars_publication', 'post' ) as $type ) {
		if ( post_type_exists( $type ) ) {
			$types[] = $type;
		}
	}

	if ( empty( $types ) ) {
		return null;
	}

	$ids = get_posts(
		array(
			'post_type'           => $types,
			'post_status'         => 'publish',
			'numberposts'         => 1,
			'orderby'             => 'date',
			'order'               => 'DESC',
			'fields'              => 'ids',
			'no_found_rows'       => true,
			'ignore_sticky_posts' => true,
			'suppress_filters'    => false,
		)
	);

	if ( empty( $ids ) ) {
		return null;
	}

	$gmt = (string) get_post_field( 'post_date_gmt', (int) $ids[0] );
	if ( '' === $gmt || 0 === strpos( $gmt, '0000-00-00' ) ) {
		return null;
	}

	$ts = strtotime( $gmt . ' UTC' );

	return false === $ts ? null : (int) $ts;
}

/* -------------------------------------------------------------------------
 * maars/next-meeting
 * ---------------------------------------------------------------------- */

/**
 * Render the computed next-meeting date plus the rule that produced it.
 *
 * This is the one thing a visitor came for, so it is the first thing and the
 * largest thing. The date is its own line, in the body face because a written
 * date is a sentence, and the rule that produced it sits underneath, small and
 * quiet — the working shown beneath the answer, because a date whose
 * provenance is invisible is the thing that rotted on the old site.
 *
 * What is deliberately NOT here any more:
 *   - the "NEXT MEETING" eyebrow above the date. It was a tracked-out capital
 *     label sitting where the answer should be, and it pushed the answer into
 *     second place on the page. The heading above the block, and the
 *     screen-reader label below, already say what this is.
 *   - the "COMPUTED" tag in front of the rule. A bordered capitalised tag made
 *     provenance look like a warning.
 *   - the log-line column classes. This block is not a row; the rows beneath it
 *     are rows, and revision 1 made the two look like siblings.
 *   - the data face on the date. "Friday, October 9, 2026 at 6:30 P.M." is a
 *     sentence, not a frequency.
 *
 * @param array         $attributes Block attributes.
 * @param string        $content    Inner content (unused).
 * @param WP_Block|null $block      Block instance (unused).
 * @return string HTML.
 */
function maars_render_next_meeting_block( $attributes = array(), $content = '', $block = null ): string {
	unset( $content, $block );

	$attributes = is_array( $attributes ) ? $attributes : array();

	$label = isset( $attributes['label'] ) ? trim( (string) $attributes['label'] ) : '';
	$label = '' !== $label ? $label : __( 'Next meeting', 'maars' );

	$show_rule = ! isset( $attributes['showRule'] ) || (bool) $attributes['showRule'];

	$meeting = function_exists( 'maars_next_meeting' ) ? maars_next_meeting() : array();
	$meeting = is_array( $meeting ) ? $meeting : array();

	$ts   = isset( $meeting['ts'] ) ? (int) $meeting['ts'] : 0;
	$iso  = isset( $meeting['iso'] ) ? maars_blocks_normalize_date( $meeting['iso'] ) : '';
	$text = isset( $meeting['label'] ) ? trim( (string) $meeting['label'] ) : '';
	$rule = isset( $meeting['rule'] ) ? trim( (string) $meeting['rule'] ) : '';

	$known = ( $ts > 0 || '' !== $iso );

	if ( '' === $text ) {
		if ( '' !== $iso ) {
			$text = maars_blocks_format_date( $iso );
		} elseif ( $ts > 0 && function_exists( 'wp_date' ) ) {
			$text = (string) wp_date( 'l, F j, Y', $ts );
		} else {
			$text = __( 'Not computed yet', 'maars' );
		}
	}

	$datetime = '';
	if ( $ts > 0 && function_exists( 'wp_date' ) ) {
		$datetime = (string) wp_date( 'c', $ts );
	} elseif ( '' !== $iso ) {
		$datetime = $iso;
	}

	$classes = 'maars-next-meeting';
	if ( ! $known ) {
		$classes .= ' maars-next-meeting--unknown is-unknown';
	}

	/*
	 * Prose, in the body face, whether it is a date or an admission. The date is
	 * written out in words — day, month, year, hour — and a written date is a
	 * sentence. Only the machine-readable datetime attribute is a figure, and
	 * nobody reads that.
	 */
	$date_text = esc_html( $text );

	if ( $known && '' !== $datetime ) {
		$date_text = '<time datetime="' . esc_attr( $datetime ) . '">' . $date_text . '</time>';
	}

	/*
	 * The label is owed to a screen reader and to nobody else. Read aloud, a
	 * bare date at the top of a panel is "Friday, October 9, 2026" with no idea
	 * what it is the date OF; on screen, the heading above this block and the
	 * size of the line say it already. The trailing space inside the span keeps
	 * the two apart for any reader that renders it as ordinary text.
	 */
	$out  = '<p class="maars-next-meeting__date">';
	$out .= '<span class="screen-reader-text">' . esc_html( $label ) . ': </span>';
	$out .= $date_text;
	$out .= '</p>';

	if ( $show_rule ) {
		if ( '' === $rule ) {
			$rule = __( 'No rule was supplied by maars_next_meeting(), so this date cannot be shown as derived.', 'maars' );
		}

		/* The working, underneath the answer: no tag, no border, no capitals. */
		$out .= '<p class="maars-next-meeting__rule">'
			. '<span class="maars-next-meeting__rule-text">' . esc_html( $rule ) . '</span>'
			. '</p>';
	}

	return '<div ' . maars_blocks_wrapper_attributes( array( 'class' => $classes ) ) . '>'
		. $out
		. '</div>';
}

/* -------------------------------------------------------------------------
 * maars/dateline
 * ---------------------------------------------------------------------- */

/**
 * Render the "last published N days ago" banner.
 *
 * On a site with nothing published it says so in words. It never prints a
 * reassuring zero for an empty archive: that was the old site's whole problem.
 *
 * @param array         $attributes Block attributes.
 * @param string        $content    Inner content (unused).
 * @param WP_Block|null $block      Block instance (unused).
 * @return string HTML.
 */
function maars_render_dateline_block( $attributes = array(), $content = '', $block = null ): string {
	unset( $content, $block );

	$attributes = is_array( $attributes ) ? $attributes : array();

	$threshold = isset( $attributes['threshold'] ) ? (int) $attributes['threshold'] : 120;
	if ( $threshold < 1 ) {
		$threshold = 120;
	}

	$show_date = ! isset( $attributes['showDate'] ) || (bool) $attributes['showDate'];

	$latest = maars_blocks_latest_publication_time();

	$days = null;
	if ( function_exists( 'maars_days_since_last_publication' ) ) {
		$reported = (int) maars_days_since_last_publication();
		if ( $reported >= 0 ) {
			$days = $reported;
		}
	}

	if ( null === $days && null !== $latest ) {
		$day = defined( 'DAY_IN_SECONDS' ) ? DAY_IN_SECONDS : 86400;
		$days = (int) floor( ( time() - $latest ) / $day );
		$days = max( 0, $days );
	}

	/*
	 * The date printed in the detail line must come off the SAME clock as the
	 * day count in the headline, or the banner can contradict itself: the count
	 * comes from maars_days_since_last_publication(), which prefers the date the
	 * document itself carries (_maars_doc_date) over the day it was imported.
	 * Printing the import date next to a count derived from the document date is
	 * how a page ends up saying "last published 608 days ago. Newest item: today".
	 */
	$latest_iso = '';
	if ( function_exists( 'maars_last_publication_date' ) ) {
		$latest_iso = maars_blocks_normalize_date( maars_last_publication_date() );
	}

	$classes = 'maars-dateline';
	$attrs   = array();
	$inner   = '';

	if ( null === $latest || null === $days ) {
		/* Empty archive: say it plainly. */
		$classes            .= ' maars-dateline--empty is-empty';
		$attrs['data-state'] = 'empty';

		$inner .= '<p class="maars-dateline__headline">' . esc_html__( 'Nothing has been published here yet.', 'maars' ) . '</p>';
		$inner .= '<p class="maars-dateline__detail">'
			. esc_html__( 'There is no archive item to date, so there is no dateline to report. This line will start counting the day the first newsletter, minutes or news item is published.', 'maars' )
			. '</p>';
	} else {
		$stale = ( $days > $threshold );

		$classes .= $stale ? ' maars-dateline--stale is-stale' : ' maars-dateline--fresh is-fresh';

		$attrs['data-state']           = $stale ? 'stale' : 'fresh';
		$attrs['data-maars-days']      = (string) $days;
		$attrs['data-maars-threshold'] = (string) $threshold;

		if ( 0 === $days ) {
			$headline_html = esc_html__( 'The club last published today.', 'maars' );
		} else {
			/* The count is a figure; the word "days" around it is not. */
			$phrase_html = sprintf(
				/* translators: %s: number of days. */
				esc_html( _n( '%s day', '%s days', $days, 'maars' ) ),
				maars_blocks_fig( number_format_i18n( $days ) )
			);

			$headline_html = sprintf(
				/* translators: %s: a duration such as "608 days". */
				esc_html__( 'The club last published %s ago.', 'maars' ),
				$phrase_html
			);

			if ( $days >= 60 ) {
				$months = (int) round( $days / 30.44 );
				if ( $months > 1 ) {
					$headline_html .= ' ' . sprintf(
						/* translators: %s: number of months. */
						esc_html__( 'That is about %s months.', 'maars' ),
						maars_blocks_fig( number_format_i18n( $months ) )
					);
				}
			}
		}

		$inner .= '<p class="maars-dateline__headline">' . $headline_html . '</p>';

		$detail_html = $stale
			? sprintf(
				/* translators: %s: number of days. */
				esc_html__( 'Past the %s-day freshness threshold. Nothing on this site should be assumed current until it has been checked.', 'maars' ),
				maars_blocks_fig( number_format_i18n( $threshold ) )
			)
			: sprintf(
				/* translators: %s: number of days. */
				esc_html__( 'Within the %s-day freshness threshold.', 'maars' ),
				maars_blocks_fig( number_format_i18n( $threshold ) )
			);

		if ( $show_date ) {
			$newest_html = '';

			if ( '' !== $latest_iso ) {
				$newest_html = maars_blocks_fig_date( $latest_iso );
			} elseif ( function_exists( 'wp_date' ) ) {
				$format      = function_exists( 'get_option' ) ? (string) get_option( 'date_format' ) : '';
				$format      = '' !== $format ? $format : 'F j, Y';
				$newest_html = '<time datetime="' . esc_attr( (string) wp_date( 'Y-m-d', $latest ) ) . '">'
					. esc_html( (string) wp_date( $format, $latest ) )
					. '</time>';
			}

			if ( '' !== $newest_html ) {
				$detail_html .= ' ' . sprintf(
					/* translators: %s: a formatted date. */
					esc_html__( 'Newest item: %s.', 'maars' ),
					$newest_html
				);
			}
		}

		$inner .= '<p class="maars-dateline__detail">' . $detail_html . '</p>';
	}

	$attrs['class'] = $classes;

	return '<div ' . maars_blocks_wrapper_attributes( $attrs ) . ' role="status">' . $inner . '</div>';
}

/* -------------------------------------------------------------------------
 * maars/fact
 * ---------------------------------------------------------------------- */

/**
 * Wrap inner content with a freshness chip.
 *
 * Grade resolution order: explicit block attribute, then the post's own
 * freshness state, then 'unverified'. An unlabelled claim is an unverified
 * claim; it is never promoted by omission.
 *
 * The chip is ONE quiet line under the statement: the grade word, then when
 * the claim was last checked and how long ago. Both are words, so the grade
 * survives greyscale, deuteranopia and a photocopier. What the grade means is
 * explained once on the page rather than under every row, and the archive path
 * a claim came out of is a record locator for whoever maintains the site — it
 * goes in the title attribute, not into the reader's face.
 *
 * @param array         $attributes Block attributes: grade, verifiedOn, sourceFile.
 * @param string        $content    Inner content.
 * @param WP_Block|null $block      Block instance (for postId context).
 * @return string HTML.
 */
function maars_render_fact_block( $attributes = array(), $content = '', $block = null ): string {
	$attributes = is_array( $attributes ) ? $attributes : array();

	$post_id = 0;
	if ( $block instanceof WP_Block && ! empty( $block->context['postId'] ) ) {
		$post_id = (int) $block->context['postId'];
	}
	if ( $post_id < 1 && function_exists( 'get_the_ID' ) ) {
		$post_id = (int) get_the_ID();
	}

	$state = array(
		'grade'       => '',
		'verified_on' => '',
		'age_days'    => null,
		'stale'       => false,
	);

	if ( $post_id > 0 && function_exists( 'maars_freshness_state' ) ) {
		$resolved = maars_freshness_state( $post_id );
		if ( is_array( $resolved ) ) {
			$state = array_merge( $state, $resolved );
		}
	}

	$grade = maars_blocks_normalize_grade( isset( $attributes['grade'] ) ? $attributes['grade'] : '' );
	if ( '' === $grade ) {
		$grade = maars_blocks_normalize_grade( $state['grade'] );
	}
	if ( '' === $grade ) {
		$grade = 'unverified';
	}

	$verified_on = maars_blocks_normalize_date( isset( $attributes['verifiedOn'] ) ? $attributes['verifiedOn'] : '' );
	if ( '' === $verified_on ) {
		$verified_on = maars_blocks_normalize_date( $state['verified_on'] );
	}

	$source = isset( $attributes['sourceFile'] ) ? trim( (string) $attributes['sourceFile'] ) : '';
	if ( '' === $source && $post_id > 0 && function_exists( 'get_post_meta' ) ) {
		$source = trim( (string) get_post_meta( $post_id, '_maars_source_file', true ) );
	}

	$age_days = isset( $state['age_days'] ) && null !== $state['age_days'] ? (int) $state['age_days'] : null;
	/*
	 * STALENESS IS ABOUT AGE, NOT ABOUT GRADE. Treating every "unverified" fact
	 * as stale painted rust on a fact checked three days ago, which is the page
	 * crying wolf: "unverified" is a statement about the EVIDENCE, and the word
	 * already carries it. Rust is spent only where a reader is being told
	 * something the word does not say -- that the check itself has gone old.
	 */
	$stale    = ! empty( $state['stale'] );

	/*
	 * The age has to be the age of the date this chip actually prints. A block
	 * attribute may override the post's own _maars_verified_on, and the two
	 * numbers then come off different records: the chip would read "Last
	 * checked September 13, 2026, 972 days ago" and contradict itself inside
	 * one sentence. Recompute from the date being shown, and let the staleness
	 * follow it, so the chip is never more — or less — confident than the date
	 * beside it.
	 */
	if ( '' !== $verified_on && $verified_on !== maars_blocks_normalize_date( $state['verified_on'] ) ) {
		$age_days = null;

		if ( function_exists( 'maars_days_since_date' ) ) {
			$recomputed = maars_days_since_date( $verified_on );
			$age_days   = ( null === $recomputed ) ? null : (int) $recomputed;
		}

		$threshold = function_exists( 'maars_stale_threshold_days' ) ? (int) maars_stale_threshold_days() : 120;
		$stale     = ( null !== $age_days ) && ( $age_days > $threshold );
	}

	/* Body. */
	$body = trim( (string) $content );
	if ( '' === $body ) {
		$body = '<p>' . esc_html__( 'No fact text was supplied for this block. It still shows its grade, so an empty claim cannot pass for a checked one.', 'maars' ) . '</p>';
	} else {
		$body = wp_kses_post( $body );
	}

	/*
	 * Provenance for a maintainer, not for a club member. "mirror/ks0man.com/
	 * index.html" means nothing to somebody reading this in a church basement,
	 * and revision 1 printed it in the page, where it turned a one-line label
	 * into three lines of debug output. The path and the definition of the grade
	 * both live in the title attribute now: available to anyone chasing a
	 * document, invisible to everybody else.
	 */
	$title = maars_blocks_grade_meaning( $grade );

	if ( '' !== $source ) {
		$title .= ' ' . sprintf(
			/* translators: %s: a file name from the club archive. */
			__( 'Source: %s', 'maars' ),
			$source
		);
	}

	/* The fact chip says the grade and the date and nothing else. */
	$detail_html = '';

	/* When it was last checked. Never silent — a "Sourced" chip with no date
	   would otherwise read as checked. The day count is a figure; the date is a
	   sentence and stays in the body face. */
	if ( '' !== $verified_on ) {
		$date_html = maars_blocks_fig_date( $verified_on );

		if ( null !== $age_days && $age_days > 0 ) {
			$age_html = sprintf(
				/* translators: %s: number of days. */
				esc_html( _n( '%s day', '%s days', $age_days, 'maars' ) ),
				maars_blocks_fig( number_format_i18n( $age_days ) )
			);

			$checked_html = sprintf(
				/* translators: 1: a formatted date. 2: a duration such as "977 days". */
				esc_html__( 'Last checked %1$s — %2$s ago.', 'maars' ),
				$date_html,
				$age_html
			);
		} else {
			$checked_html = sprintf(
				/* translators: %s: a formatted date. */
				esc_html__( 'Last checked %s.', 'maars' ),
				$date_html
			);
		}
	} else {
		$checked_html = esc_html__( 'No check on record.', 'maars' );
	}

	$classes = 'maars-fact maars-fact--' . $grade;
	if ( $stale ) {
		$classes .= ' is-stale';
	}

	$attrs = array(
		'class'      => $classes,
		'data-grade' => $grade,
	);
	if ( '' !== $verified_on ) {
		$attrs['data-verified-on'] = $verified_on;
	}

	return '<div ' . maars_blocks_wrapper_attributes( $attrs ) . '>'
		. '<div class="maars-fact__body">' . $body . '</div>'
		. maars_blocks_chip( $grade, $detail_html, $checked_html, 'p', '', $title )
		. '</div>';
}

/* -------------------------------------------------------------------------
 * maars/skywave
 * ---------------------------------------------------------------------- */

/**
 * The band selector data, straight out of the club corpus.
 *
 * The 2 m entry is the teaching point: line of sight, no skip.
 *
 * @return array<int,array<string,mixed>>
 */
function maars_blocks_skywave_bands(): array {
	return array(
		array(
			'id'    => '80m',
			'mhz'   => '3.920',
			'label' => __( 'Kansas Sideband Net', 'maars' ),
			'skip'  => true,
		),
		array(
			'id'    => '40m',
			'mhz'   => '7.260',
			'label' => __( 'Kansas Weather Net', 'maars' ),
			'skip'  => true,
		),
		array(
			'id'    => '20m',
			'mhz'   => '14.290',
			'label' => __( 'daytime DX', 'maars' ),
			'skip'  => true,
		),
		array(
			'id'    => '2m',
			'mhz'   => '147.255',
			'label' => __( 'KSØMAN repeater (line of sight — no skip)', 'maars' ),
			'skip'  => false,
		),
	);
}

/**
 * Add the one-time inline bootstrap that mounts any skywave canvas on the page.
 *
 * The theme registers and owns the 'maars-skywave' handle; this only attaches
 * an inline mount call to it. The mount is idempotent: if skywave.js has
 * already claimed a canvas (data-maars-mounted or data-maars-ready) it is left
 * alone, so an auto-mounting build of the script cannot be double-mounted.
 *
 * @return void
 */
function maars_blocks_skywave_bootstrap(): void {
	static $done = false;

	if ( $done || ! function_exists( 'wp_add_inline_script' ) ) {
		return;
	}

	$done = true;

	$js = <<<'JS'
( function () {
	function mountOne( root ) {
		var canvas = root.querySelector( 'canvas.maars-skywave__canvas' );
		if ( ! canvas ) {
			return;
		}
		if ( '1' === canvas.dataset.maarsMounted || '1' === canvas.dataset.maarsReady ) {
			return;
		}
		var opts = {};
		try {
			opts = JSON.parse( canvas.getAttribute( 'data-maars-skywave' ) || '{}' );
		} catch ( err ) {
			opts = {};
		}
		canvas.dataset.maarsMounted = '1';
		try {
			root.maarsSkywave = window.MAARSSkywave.mount( canvas, opts );
		} catch ( err ) {
			canvas.dataset.maarsMounted = '';
			canvas.dataset.maarsFallbackReason = 'mount-threw';
			root.classList.add( 'maars-skywave--fallback' );
			if ( window.console && window.console.error ) { window.console.error( 'maars/skywave failed to mount:', err ); }
		}
	}

	/* The theme registers maars-skywave with the defer strategy, so on a normal
	   page load this inline script runs BEFORE skywave.js has executed. The
	   DOMContentLoaded path below covers that. The retry covers the remaining
	   case -- this bootstrap arriving after the document is already parsed, e.g.
	   injected markup -- so a slow script cannot strand a working canvas in the
	   fallback state permanently. Ten tries, then give up honestly. */
	var tries = 0;

	function boot() {
		if ( ! window.MAARSSkywave || 'function' !== typeof window.MAARSSkywave.mount ) {
			if ( tries++ < 10 ) {
				window.setTimeout( boot, 100 );
				return;
			}
			var orphans = document.querySelectorAll( '.maars-skywave[data-maars-autostart="1"]' );
			for ( var j = 0; j < orphans.length; j++ ) {
				orphans[ j ].classList.add( 'maars-skywave--fallback' );
				var oc = orphans[ j ].querySelector( 'canvas.maars-skywave__canvas' );
				if ( oc ) { oc.dataset.maarsFallbackReason = 'script-missing'; }
				var on = orphans[ j ].querySelector( '.maars-skywave__fallback-title' );
				if ( on ) {
					on.textContent = 'The 3-D scene’s script did not load, so here is the same thing in words. This is usually a site configuration problem, not a browser one — check the browser console for a failed request.';
				}
			}
			return;
		}
		var nodes = document.querySelectorAll( '.maars-skywave[data-maars-autostart="1"]' );
		for ( var i = 0; i < nodes.length; i++ ) {
			mountOne( nodes[ i ] );
		}
	}

	function schedule() {
		window.setTimeout( boot, 0 );
	}

	if ( 'loading' === document.readyState ) {
		document.addEventListener( 'DOMContentLoaded', schedule );
	} else {
		schedule();
	}
}() );
JS;

	wp_add_inline_script( 'maars-skywave', $js, 'after' );
}

/**
 * Render the WebGL2 skywave canvas, its static fallback and its noscript.
 *
 * Enqueues (never registers) the theme's 'maars-skywave' handle.
 *
 * @param array         $attributes Block attributes.
 * @param string        $content    Inner content (unused).
 * @param WP_Block|null $block      Block instance (unused).
 * @return string HTML.
 */
function maars_render_skywave_block( $attributes = array(), $content = '', $block = null ): string {
	unset( $content, $block );

	$attributes = is_array( $attributes ) ? $attributes : array();

	$bands    = maars_blocks_skywave_bands();
	$band_ids = wp_list_pluck( $bands, 'id' );

	$band = isset( $attributes['band'] ) ? strtolower( trim( (string) $attributes['band'] ) ) : '';
	if ( ! in_array( $band, $band_ids, true ) ) {
		$band = '80m';
	}

	$width  = isset( $attributes['width'] ) ? (int) $attributes['width'] : 1280;
	$height = isset( $attributes['height'] ) ? (int) $attributes['height'] : 720;
	$width  = min( 4096, max( 320, $width ) );
	$height = min( 4096, max( 180, $height ) );

	$autostart = ! isset( $attributes['autostart'] ) || (bool) $attributes['autostart'];

	$caption = isset( $attributes['caption'] ) ? trim( (string) $attributes['caption'] ) : '';
	if ( '' === $caption ) {
		$caption = __( 'HF signals leaving Manhattan, Kansas, bending off the D, E, F1 and F2 layers and coming back down. Switch to 2 m and the ray leaves through the top: VHF does not skip.', 'maars' );
	}

	$have_script = function_exists( 'wp_script_is' ) && wp_script_is( 'maars-skywave', 'registered' );
	if ( $have_script ) {
		wp_enqueue_script( 'maars-skywave' );
		if ( $autostart ) {
			maars_blocks_skywave_bootstrap();
		}
	}

	$opts = array(
		'band'   => $band,
		'bands'  => $bands,
		'origin' => array(
			'label' => __( 'Manhattan, Kansas', 'maars' ),
			'lat'   => 39.1836,
			'lon'   => -96.5717,
		),
	);

	$json = function_exists( 'wp_json_encode' ) ? wp_json_encode( $opts ) : json_encode( $opts );
	$json = is_string( $json ) ? $json : '{}';

	$aria = __( 'Animated diagram of skywave propagation from Manhattan, Kansas: rays leave the transmitter, refract off the ionospheric layers and return to earth. A text description follows.', 'maars' );

	/* Static band list. This is the teaching content, and it is readable with
	   no JavaScript, no WebGL2 and no CSS. Each line is a log line: band,
	   frequency and what the club does there — the band and the frequency are
	   figures, the purpose is prose. */
	$list = '<ul class="maars-skywave__bands maars-log">';
	foreach ( $bands as $entry ) {
		$line_html = sprintf(
			/* translators: 1: band name such as 80m, 2: frequency in MHz, 3: what the club uses it for. */
			esc_html__( '%1$s — %2$s MHz — %3$s', 'maars' ),
			maars_blocks_fig( $entry['id'] ),
			maars_blocks_fig( $entry['mhz'] ),
			maars_blocks_mark_callsign( esc_html( $entry['label'] ) )
		);

		$list .= '<li class="maars-skywave__band maars-log__line maars-skywave__band--' . esc_attr( $entry['id'] ) . '"'
			. ( $band === $entry['id'] ? ' data-current="1"' : '' )
			. '>' . $line_html . '</li>';
	}
	$list .= '</ul>';

	/* Live band selector. skywave.js delegates clicks on the canvas's parent and
	   switches band from any element carrying data-maars-band, so without real
	   controls here the 2 m teaching point — the ray that leaves and does not
	   come back — is unreachable in a browser that does have WebGL2. These are
	   buttons, not links: they change what is drawn, they do not navigate. */
	$controls = '';
	if ( $have_script ) {
		$controls = '<ul class="maars-skywave__controls">';
		foreach ( $bands as $entry ) {
			$current = ( $band === $entry['id'] );

			$controls .= '<li>'
				. '<button type="button" class="maars-skywave__control"'
				. ' data-maars-band="' . esc_attr( $entry['id'] ) . '"'
				. ' aria-pressed="' . ( $current ? 'true' : 'false' ) . '">'
				. '<span class="maars-skywave__control-band maars-fig">' . esc_html( $entry['id'] ) . '</span> '
				. '<span class="maars-skywave__control-freq maars-fig">' . esc_html( $entry['mhz'] ) . '</span>'
				. '<span class="screen-reader-text"> '
				. esc_html(
					sprintf(
						/* translators: 1: frequency in MHz, 2: what the club uses the band for. */
						__( 'megahertz — %1$s', 'maars' ),
						$entry['label']
					)
				)
				. '</span>'
				. '</button>'
				. '</li>';
		}
		$controls .= '</ul>';
	}

	$prose = '<p class="maars-skywave__prose">'
		. esc_html__( 'On 80, 40 and 20 metres the signal is refracted back to earth by the ionosphere and lands hundreds of miles away. On 2 metres it passes straight through and keeps going, which is why the repeater covers line of sight and nothing more.', 'maars' )
		. '</p>';

	$fallback = '<div class="maars-skywave__fallback">'
		. '<p class="maars-skywave__fallback-title">' . esc_html__( 'The propagation diagram is not being drawn, so here is the same thing in words.', 'maars' ) . '</p>'
		. $prose
		. $list
		. '</div>';

	$noscript = '<noscript>'
		. '<div class="maars-skywave__noscript">'
		. '<p class="maars-skywave__fallback-title">' . esc_html__( 'JavaScript is off, so the propagation diagram is not drawn. Here is the same thing in words.', 'maars' ) . '</p>'
		. $prose
		. $list
		. '</div>'
		. '</noscript>';

	/* The scene is drawn from archive figures nobody has re-measured, and it
	   says so in the same calm chip the rest of the site uses. */
	$chip = maars_blocks_chip(
		'unverified',
		esc_html__( 'The 2 m repeater figures come from the archive and have not been confirmed on the air.', 'maars' ),
		'',
		'span',
		'maars-skywave__chip'
	);

	$canvas = '<canvas class="maars-skywave__canvas"'
		. ' width="' . esc_attr( (string) $width ) . '"'
		. ' height="' . esc_attr( (string) $height ) . '"'
		. ' role="img"'
		. ' aria-label="' . esc_attr( $aria ) . '"'
		. ' data-maars-band="' . esc_attr( $band ) . '"'
		. ' data-maars-skywave="' . esc_attr( $json ) . '"'
		. '></canvas>';

	$attrs = array(
		'class'                => 'maars-skywave',
		'data-maars-autostart' => $autostart && $have_script ? '1' : '0',
		'data-maars-band'      => $band,
	);

	if ( ! $have_script ) {
		$attrs['class'] .= ' maars-skywave--fallback';
	}

	return '<figure ' . maars_blocks_wrapper_attributes( $attrs ) . '>'
		. $canvas
		. $controls
		. $fallback
		. $noscript
		. '<figcaption class="maars-skywave__caption">' . esc_html( $caption ) . ' ' . $chip . '</figcaption>'
		. '</figure>';
}

/* -------------------------------------------------------------------------
 * maars/masthead — THE HEAD OF THE SITE IS A RECEIVER.
 *
 * Revision 2's masthead was four lines of type over white. It was honest and
 * it was dull, and the owner's instruction for revision 3 was to scrap it and
 * find a new idea: modern, for a club that expects something new, soft and
 * smooth.
 *
 * The idea is the one picture every licensed amateur alive can read without
 * being taught it — the spectrum trace with a waterfall scrolling underneath,
 * the display on the front of an IC-7300 and the output of a twenty-dollar
 * RTL-SDR dongle. It is soft and smooth by its own nature: a continuous heat
 * map with no hard edge in it anywhere. So the masthead becomes an
 * instrument, tuned to 147.255 MHz — the Society's own repeater — and the
 * identity rests in it.
 *
 * WHAT THIS BLOCK IS CAREFUL ABOUT.
 *
 *   1. IT DOES NOT CLAIM TO BE A RECEIVER. Nothing here is live. The canvas
 *      is a drawing of a noise floor with one marked carrier in it, and the
 *      line under the band says exactly that in words a member can read. This
 *      site's whole argument is that a page must never look more current than
 *      it is; a fake live receiver in the masthead would be the largest lie on
 *      the page.
 *
 *   2. THE IDENTITY IS REAL TEXT. The old club site set its own name in a GIF
 *      with no alt attribute, so the Society was invisible to a screen reader
 *      and to search. The canvas here is decorative and says so — aria-hidden
 *      — and every word over it is a paragraph.
 *
 *   3. THE CALLSIGN IS A FIGURE, AND IT IS THE WORDMARK. KSØMAN is set in
 *      Fira Code, whose zero is natively slashed — that is how the Society
 *      writes it, and it is the entire reason that face is in the system.
 *      Section 10b puts the face on .maars-masthead__call directly rather than
 *      through a nested .maars-fig, so the wordmark is one element and not a
 *      span inside a paragraph inside a link. The frequency in the readout
 *      DOES go through maars_blocks_fig(), like every other frequency on the
 *      site. The Society's name between them is prose and gets neither.
 *
 *   4. IT WORKS WITH THE SCRIPT MISSING, WITH JAVASCRIPT OFF AND WITH NO
 *      CANVAS AT ALL. In each case the strip is a soft navy gradient and the
 *      identity is exactly where it was. There is no error state.
 *
 * MARKUP CONTRACT. Section 10 of assets/css/maars.css is written against
 * exactly this tree and says so at the head of the section; the two files have
 * to be read together.
 *
 *   <div class="maars-masthead">                  <- direct child of .maars-header
 *     <canvas class="maars-masthead__canvas" aria-hidden="true"></canvas>
 *     <div class="maars-masthead__identity">
 *       <p class="maars-masthead__call"><a href="/">KSØMAN</a></p>
 *       <p class="maars-masthead__long">Manhattan Area Amateur Radio Society</p>
 *       <p class="maars-masthead__tuned">… <span class="maars-fig">147.255 MHz</span> …</p>
 *     </div>
 *   </div>
 * ---------------------------------------------------------------------- */

/**
 * The receiver the masthead is tuned to.
 *
 * One array so the picture and the sentence underneath it cannot drift apart:
 * the canvas is handed these numbers and the caption prints the same ones.
 *
 * @return array<string, float> centre, start and end of the span, in MHz.
 */
function maars_blocks_masthead_span(): array {
	return array(
		'centre' => 147.255,
		'start'  => 147.0,
		'end'    => 147.5,
	);
}

/**
 * Add the one-time inline bootstrap that mounts the masthead canvas.
 *
 * The theme registers and owns the 'maars-waterfall' handle; this only
 * attaches an inline mount call to it, exactly as the skywave bootstrap does
 * for its own handle. The mount is idempotent, and if the script never arrives
 * the retry gives up honestly and leaves the strip in its CSS fallback rather
 * than leaving a dead canvas that nothing will ever paint.
 *
 * @return void
 */
function maars_blocks_masthead_bootstrap(): void {
	static $done = false;

	if ( $done || ! function_exists( 'wp_add_inline_script' ) ) {
		return;
	}

	$done = true;

	$js = <<<'JS'
( function () {
	function mountOne( root ) {
		var canvas = root.querySelector( 'canvas.maars-masthead__canvas' );
		if ( ! canvas ) {
			return;
		}
		if ( '1' === canvas.dataset.maarsMounted || '1' === canvas.dataset.maarsReady ) {
			return;
		}
		var opts = {};
		try {
			opts = JSON.parse( canvas.getAttribute( 'data-maars-waterfall' ) || '{}' );
		} catch ( err ) {
			opts = {};
		}
		canvas.dataset.maarsMounted = '1';
		try {
			root.maarsWaterfall = window.MAARSWaterfall.mount( canvas, opts );
		} catch ( err ) {
			canvas.dataset.maarsMounted = '';
			canvas.dataset.maarsFallbackReason = 'mount-threw';
			root.classList.add( 'maars-masthead--fallback' );
			if ( window.console && window.console.error ) { window.console.error( 'maars/masthead failed to mount:', err ); }
		}
	}

	/* The theme registers maars-waterfall with the defer strategy, so on a
	   normal page load this inline script runs BEFORE waterfall.js has
	   executed; the DOMContentLoaded path covers that. The retry covers the
	   remaining case -- this bootstrap arriving after the document is already
	   parsed -- so a slow script cannot strand a working canvas in the
	   fallback state permanently. Ten tries, then give up quietly: unlike the
	   skywave scene there is nothing to explain to the reader here, because
	   the fallback IS the design with the animation taken out of it. */
	var tries = 0;

	function boot() {
		if ( ! window.MAARSWaterfall || 'function' !== typeof window.MAARSWaterfall.mount ) {
			if ( tries++ < 10 ) {
				window.setTimeout( boot, 100 );
				return;
			}
			var orphans = document.querySelectorAll( '.maars-masthead[data-maars-autostart="1"]' );
			for ( var j = 0; j < orphans.length; j++ ) {
				orphans[ j ].classList.add( 'maars-masthead--fallback' );
				var oc = orphans[ j ].querySelector( 'canvas.maars-masthead__canvas' );
				if ( oc ) { oc.dataset.maarsFallbackReason = 'script-missing'; }
			}
			return;
		}
		var nodes = document.querySelectorAll( '.maars-masthead[data-maars-autostart="1"]' );
		for ( var i = 0; i < nodes.length; i++ ) {
			mountOne( nodes[ i ] );
		}
	}

	function schedule() {
		window.setTimeout( boot, 0 );
	}

	if ( 'loading' === document.readyState ) {
		document.addEventListener( 'DOMContentLoaded', schedule );
	} else {
		schedule();
	}
}() );
JS;

	wp_add_inline_script( 'maars-waterfall', $js, 'after' );
}

/**
 * Render the masthead: the receiver strip, the identity in it, and the line
 * that says what the strip is.
 *
 * Enqueues (never registers) the theme's 'maars-waterfall' handle, the same
 * way maars/skywave enqueues 'maars-skywave'.
 *
 * @param array         $attributes Block attributes.
 * @param string        $content    Inner content (unused).
 * @param WP_Block|null $block      Block instance (unused).
 * @return string HTML.
 */
function maars_render_masthead_block( $attributes = array(), $content = '', $block = null ): string {
	unset( $content, $block );

	$attributes = is_array( $attributes ) ? $attributes : array();

	$span = maars_blocks_masthead_span();

	$callsign = isset( $attributes['callsign'] ) ? trim( (string) $attributes['callsign'] ) : '';
	if ( '' === $callsign ) {
		$callsign = 'KSØMAN';
	}

	$society = isset( $attributes['society'] ) ? trim( (string) $attributes['society'] ) : '';
	if ( '' === $society ) {
		$society = __( 'Manhattan Area Amateur Radio Society', 'maars' );
	}

	/* The strip's height. The design brief fixes the band between 150 and 190
	   CSS pixels: under 150 the two regions stop being two regions, and over
	   190 the masthead costs a phone screen more than the content under it is
	   worth. The height at any given width is settled in CSS (section 10a);
	   this is the pre-layout backing-store hint on the element, so a canvas
	   painted before the stylesheet lands is never wildly wrong. */
	$height = isset( $attributes['height'] ) ? (int) $attributes['height'] : 180;
	$height = min( 190, max( 150, $height ) );

	$autostart = ! isset( $attributes['autostart'] ) || (bool) $attributes['autostart'];

	$have_script = function_exists( 'wp_script_is' ) && wp_script_is( 'maars-waterfall', 'registered' );
	if ( $have_script ) {
		wp_enqueue_script( 'maars-waterfall' );
		if ( $autostart ) {
			maars_blocks_masthead_bootstrap();
		}
	}

	$opts = array(
		'centreMhz' => $span['centre'],
		'startMhz'  => $span['start'],
		'endMhz'    => $span['end'],
	);

	$json = function_exists( 'wp_json_encode' ) ? wp_json_encode( $opts ) : json_encode( $opts );
	$json = is_string( $json ) ? $json : '{}';

	$home = function_exists( 'home_url' ) ? home_url( '/' ) : '/';

	/* The canvas is decorative and says so. Everything it means is in the
	   readout underneath, in real text, in the accessibility tree. It carries
	   no role, no tabindex and no label: a reader must never be stopped by a
	   picture of a noise floor. */
	$canvas = '<canvas class="maars-masthead__canvas"'
		. ' aria-hidden="true"'
		. ' width="1600"'
		. ' height="' . esc_attr( (string) $height ) . '"'
		. ' data-maars-waterfall="' . esc_attr( $json ) . '"'
		. '></canvas>';

	/* The readout. One sentence saying what the band is tuned to, and one
	   saying what it is -- because it is a drawing of a band and not a
	   receiver, and a masthead that looked live on a site whose whole argument
	   is "never look more current than you are" would be the largest untrue
	   thing on the page. The frequency is a figure and goes through the same
	   helper every frequency on this site goes through; the words around it
	   are prose and do not. */
	$tuned_html = sprintf(
		/* translators: %s: the repeater frequency, already marked up as a figure. */
		esc_html__( 'Tuned to %s, the Society’s own repeater. Drawn, not received.', 'maars' ),
		maars_blocks_fig( number_format_i18n( $span['centre'], 3 ) . ' MHz' )
	);

	$identity = '<div class="maars-masthead__identity">'
		. '<p class="maars-masthead__call"><a href="' . esc_url( $home ) . '">' . esc_html( $callsign ) . '</a></p>'
		. '<p class="maars-masthead__long">' . esc_html( $society ) . '</p>'
		. '<p class="maars-masthead__tuned">' . $tuned_html . '</p>'
		. '</div>';

	$attrs = array(
		'class'                => 'maars-masthead',
		'data-maars-autostart' => $autostart && $have_script ? '1' : '0',
	);

	if ( ! $have_script ) {
		$attrs['class'] .= ' maars-masthead--fallback';
	}

	return '<div ' . maars_blocks_wrapper_attributes( $attrs ) . '>'
		. $canvas
		. $identity
		. '</div>';
}
