<?php
/**
 * MAARS core — server-rendered blocks.
 *
 * Four dynamic blocks, registered in plain PHP with render callbacks.
 * There is deliberately NO JavaScript build step, no block.json bundler and no
 * editor script: everything here is produced on the server so the markup is the
 * same for a browser, a screen reader and curl.
 *
 * Design rule for every block in this file: staleness is visible, never hidden.
 * A date is shown together with the rule that produced it; a fact is shown
 * together with how well it is known; an archive with nothing in it says so
 * instead of printing a confident zero.
 *
 * All output is escaped. Inner content is filtered with wp_kses_post().
 *
 * @package maars
 */

defined( 'ABSPATH' ) || exit;

/**
 * Register the four MAARS blocks.
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
 * Human label for a grade.
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

	$inner  = '<p class="maars-next-meeting__eyebrow">' . esc_html( $label ) . '</p>';
	$inner .= '<p class="maars-next-meeting__date">';
	if ( '' !== $datetime ) {
		$inner .= '<time class="maars-next-meeting__time" datetime="' . esc_attr( $datetime ) . '">' . esc_html( $text ) . '</time>';
	} else {
		$inner .= esc_html( $text );
	}
	$inner .= '</p>';

	if ( $show_rule ) {
		if ( '' === $rule ) {
			$rule = __( 'No rule was supplied by maars_next_meeting(), so this date cannot be shown as derived.', 'maars' );
		}
		$inner .= '<p class="maars-next-meeting__rule">'
			. '<span class="maars-next-meeting__rule-tag">' . esc_html__( 'Computed', 'maars' ) . '</span> '
			. '<span class="maars-next-meeting__rule-text">' . esc_html( $rule ) . '</span>'
			. '</p>';
	}

	return '<div ' . maars_blocks_wrapper_attributes( array( 'class' => $classes ) ) . '>' . $inner . '</div>';
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
			$headline = __( 'The club last published today.', 'maars' );
		} else {
			$phrase = sprintf(
				/* translators: %s: number of days. */
				_n( '%s day', '%s days', $days, 'maars' ),
				number_format_i18n( $days )
			);

			$headline = sprintf(
				/* translators: %s: a duration such as "608 days". */
				__( 'The club last published %s ago.', 'maars' ),
				$phrase
			);

			if ( $days >= 60 ) {
				$months = (int) round( $days / 30.44 );
				if ( $months > 1 ) {
					$headline .= ' ' . sprintf(
						/* translators: %s: number of months. */
						__( 'That is about %s months.', 'maars' ),
						number_format_i18n( $months )
					);
				}
			}
		}

		$inner .= '<p class="maars-dateline__headline">' . esc_html( $headline ) . '</p>';

		$detail = $stale
			? sprintf(
				/* translators: %s: number of days. */
				__( 'Past the %s-day freshness threshold. Nothing on this site should be assumed current until it has been checked.', 'maars' ),
				number_format_i18n( $threshold )
			)
			: sprintf(
				/* translators: %s: number of days. */
				__( 'Within the %s-day freshness threshold.', 'maars' ),
				number_format_i18n( $threshold )
			);

		if ( $show_date ) {
			$newest = '';

			if ( '' !== $latest_iso ) {
				$newest = maars_blocks_format_date( $latest_iso );
			} elseif ( function_exists( 'wp_date' ) ) {
				$format = function_exists( 'get_option' ) ? (string) get_option( 'date_format' ) : '';
				$format = '' !== $format ? $format : 'F j, Y';
				$newest = (string) wp_date( $format, $latest );
			}

			if ( '' !== $newest ) {
				$detail .= ' ' . sprintf(
					/* translators: %s: a formatted date. */
					__( 'Newest item: %s.', 'maars' ),
					$newest
				);
			}
		}

		$inner .= '<p class="maars-dateline__detail">' . esc_html( $detail ) . '</p>';
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
	$stale    = ! empty( $state['stale'] ) || 'unverified' === $grade;

	/* Body. */
	$body = trim( (string) $content );
	if ( '' === $body ) {
		$body = '<p>' . esc_html__( 'No fact text was supplied for this block. It still shows its grade, so an empty claim cannot pass for a checked one.', 'maars' ) . '</p>';
	} else {
		$body = wp_kses_post( $body );
	}

	/* Chip. */
	$details = array( maars_blocks_grade_meaning( $grade ) );

	if ( '' !== $verified_on ) {
		$details[] = sprintf(
			/* translators: %s: a formatted date. */
			__( 'Checked %s.', 'maars' ),
			maars_blocks_format_date( $verified_on )
		);
	} else {
		/*
		 * Any grade with no usable verification date, not just 'unverified'.
		 * maars_freshness_state() already calls that record stale; if the chip
		 * stayed silent about it, a "Sourced" badge with no date would read as
		 * checked. The chip must never be more confident than the state it was
		 * handed.
		 */
		$details[] = __( 'No check on record.', 'maars' );
	}

	if ( null !== $age_days && $age_days > 0 ) {
		$details[] = sprintf(
			/* translators: %s: number of days. */
			_n( '%s day old.', '%s days old.', $age_days, 'maars' ),
			number_format_i18n( $age_days )
		);
	}

	if ( '' !== $source ) {
		$details[] = sprintf(
			/* translators: %s: a file name from the club archive. */
			__( 'Source: %s', 'maars' ),
			$source
		);
	}

	$classes = 'maars-fact maars-fact--' . $grade;
	if ( $stale ) {
		$classes .= ' is-stale';
	}

	$chip  = '<p class="maars-fact__chip maars-fact__chip--' . esc_attr( $grade ) . '">';
	$chip .= '<span class="maars-fact__grade">' . esc_html( maars_blocks_grade_label( $grade ) ) . '</span> ';
	$chip .= '<span class="maars-fact__detail">' . esc_html( implode( ' ', $details ) ) . '</span>';
	$chip .= '</p>';

	$attrs = array(
		'class'       => $classes,
		'data-grade'  => $grade,
	);
	if ( '' !== $verified_on ) {
		$attrs['data-verified-on'] = $verified_on;
	}

	return '<div ' . maars_blocks_wrapper_attributes( $attrs ) . '>'
		. '<div class="maars-fact__body">' . $body . '</div>'
		. $chip
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
					on.textContent = 'The 3-D scene\u2019s script did not load, so here is the same thing in words. This is usually a site configuration problem, not a browser one \u2014 check the browser console for a failed request.';
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
	   no JavaScript, no WebGL2 and no CSS. */
	$list = '<ul class="maars-skywave__bands">';
	foreach ( $bands as $entry ) {
		$line = sprintf(
			/* translators: 1: band name such as 80m, 2: frequency in MHz, 3: what the club uses it for. */
			__( '%1$s — %2$s MHz — %3$s', 'maars' ),
			$entry['id'],
			$entry['mhz'],
			$entry['label']
		);

		$list .= '<li class="maars-skywave__band maars-skywave__band--' . esc_attr( $entry['id'] ) . '"'
			. ( $band === $entry['id'] ? ' data-current="1"' : '' )
			. '>' . esc_html( $line ) . '</li>';
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
				. '<span class="maars-skywave__control-band">' . esc_html( $entry['id'] ) . '</span> '
				. '<span class="maars-skywave__control-freq">' . esc_html( $entry['mhz'] ) . '</span>'
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

	$chip = '<span class="maars-skywave__chip maars-fact__chip maars-fact__chip--unverified" data-grade="unverified">'
		. '<span class="maars-fact__grade">' . esc_html( maars_blocks_grade_label( 'unverified' ) ) . '</span> '
		. '<span class="maars-fact__detail">' . esc_html__( 'The 2 m repeater figures come from the archive and have not been confirmed on the air.', 'maars' ) . '</span>'
		. '</span>';

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
