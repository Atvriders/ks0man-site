<?php
/**
 * MAARS Core — freshness, meeting arithmetic, and the staleness clock.
 *
 * This module is the anti-rot design. The site it replaces looked current for
 * twenty months while its newest content was dated 16 January 2024: nothing on
 * the page ever admitted the gap. Here, age is a first-class value that the
 * templates are obliged to render.
 *
 * Three public entry points, all named by the locked contract:
 *   - maars_freshness_state()            what one record's evidence is worth today
 *   - maars_next_meeting()               a date computed from the governing rule
 *   - maars_days_since_last_publication() how long the club has been quiet
 *
 * Two rules the whole file obeys:
 *   1. Time is always America/Chicago via an explicit DateTimeZone. Never the
 *      server's local zone. The container's clock is UTC and the club is not.
 *   2. Every function returns a sane value on a completely empty site. That is
 *      exactly how the image boots before the seed importer has run, and a
 *      fatal on first paint would be a poor demonstration of durability.
 *
 * @package MAARS
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * The club's timezone, as an explicit object.
 *
 * Manhattan, Kansas is America/Chicago. Everything in this file — meeting
 * times, day counts, "today" — is computed in it, so a UTC container and a
 * developer's laptop agree on which day it is at 7 P.M. on a Friday.
 *
 * @return DateTimeZone
 */
function maars_club_timezone() {
	$tz = 'America/Chicago';

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter the club's timezone identifier.
		 *
		 * @param string $tz PHP timezone identifier.
		 */
		$tz = (string) apply_filters( 'maars_club_timezone', $tz );
	}

	try {
		return new DateTimeZone( $tz );
	} catch ( Exception $e ) {
		return new DateTimeZone( 'America/Chicago' );
	}
}

/**
 * "Now" in club time, or an injected instant in club time.
 *
 * Taking an optional timestamp is what makes every date calculation in this
 * file testable without freezing the system clock.
 *
 * @param int|null $ts Unix timestamp, or null for the current moment.
 * @return DateTimeImmutable Instant expressed in the club's timezone.
 */
function maars_now_local( $ts = null ) {
	$tz = maars_club_timezone();

	if ( null === $ts ) {
		return new DateTimeImmutable( 'now', $tz );
	}

	return ( new DateTimeImmutable( '@' . (int) $ts ) )->setTimezone( $tz );
}

/**
 * Validate a YYYY-MM-DD string, returning '' when it is not a real day.
 *
 * @param mixed $value Candidate date.
 * @return string Valid YYYY-MM-DD date, or ''.
 */
function maars_valid_ymd( $value ) {
	$value = is_scalar( $value ) ? trim( (string) $value ) : '';

	if ( ! preg_match( '/^(\d{4})-(\d{2})-(\d{2})$/', $value, $m ) ) {
		return '';
	}

	if ( ! checkdate( (int) $m[2], (int) $m[3], (int) $m[1] ) ) {
		return '';
	}

	return $value;
}

/**
 * Whole days from a YYYY-MM-DD date to today, in club time.
 *
 * Uses a calendar diff rather than dividing seconds by 86400 so the two
 * daylight-saving days a year do not produce an off-by-one. Dates in the
 * future clamp to 0 — a record verified tomorrow is not minus-one days old.
 *
 * @param string   $ymd     Date in YYYY-MM-DD form.
 * @param int|null $from_ts Instant to measure from, or null for now.
 * @return int|null Whole days elapsed, or null when the date is unusable.
 */
function maars_days_since_date( $ymd, $from_ts = null ) {
	$ymd = maars_valid_ymd( $ymd );

	if ( '' === $ymd ) {
		return null;
	}

	$tz   = maars_club_timezone();
	$then = DateTimeImmutable::createFromFormat( '!Y-m-d', $ymd, $tz );

	if ( ! $then instanceof DateTimeImmutable ) {
		return null;
	}

	$today = maars_now_local( $from_ts )->setTime( 0, 0, 0 );
	$diff  = $then->diff( $today );

	if ( $diff->invert ) {
		return 0;
	}

	return (int) $diff->days;
}

/**
 * The evidence grades this site is willing to print, weakest last.
 *
 * measured   — someone read it off an instrument or counted it in the archive.
 * sourced    — a document in the archive says so, and the document is cited.
 * unverified — believed true, nobody has checked it lately. Printed as such.
 *
 * @return string[] Allowed grade slugs.
 */
function maars_freshness_grades() {
	return array( 'measured', 'sourced', 'unverified' );
}

/**
 * How many days a verified fact stays fresh before the site calls it stale.
 *
 * @return int Threshold in days; 120 unless filtered.
 */
function maars_stale_threshold_days() {
	$days = 120;

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter the staleness threshold in days.
		 *
		 * @param int $days Days after which a verified fact is considered stale.
		 */
		$days = (int) apply_filters( 'maars_stale_after_days', $days );
	}

	return $days > 0 ? $days : 120;
}

/**
 * What one record's evidence is worth today.
 *
 * Reads `_maars_grade` and `_maars_verified_on` off the post and reports the
 * grade, the verification date, its age in days, and whether the site should
 * be flagging it. Deliberately pessimistic in every failure mode: an unknown
 * post, a missing grade, a garbage date and an unverified claim all come back
 * as unverified and stale. The only way to be fresh here is to have a real
 * grade and a real, recent verification date on the record.
 *
 * @param int $post_id Post ID.
 * @return array{grade:string,verified_on:string,age_days:int|null,stale:bool}
 */
function maars_freshness_state( int $post_id ): array {
	$grade       = '';
	$verified_on = '';

	if ( $post_id > 0 && function_exists( 'get_post_meta' ) ) {
		$grade       = get_post_meta( $post_id, '_maars_grade', true );
		$verified_on = get_post_meta( $post_id, '_maars_verified_on', true );
	}

	$grade = is_scalar( $grade ) ? strtolower( trim( (string) $grade ) ) : '';

	if ( ! in_array( $grade, maars_freshness_grades(), true ) ) {
		$grade = 'unverified';
	}

	$verified_on = maars_valid_ymd( $verified_on );
	$age_days    = ( '' === $verified_on ) ? null : maars_days_since_date( $verified_on );

	$stale = (
		'unverified' === $grade
		|| null === $age_days
		|| $age_days > maars_stale_threshold_days()
	);

	$state = array(
		'grade'       => $grade,
		'verified_on' => $verified_on,
		'age_days'    => $age_days,
		'stale'       => (bool) $stale,
	);

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter a record's computed freshness state.
		 *
		 * @param array $state   Freshness state as documented above.
		 * @param int   $post_id Post ID the state was computed for.
		 */
		$state = (array) apply_filters( 'maars_freshness_state', $state, $post_id );
	}

	return $state;
}

/**
 * Format a time the way the club's own minutes write it: "6:30 P.M.".
 *
 * @param DateTimeImmutable $dt Instant to format.
 * @return string Time label.
 */
function maars_club_time_label( DateTimeImmutable $dt ): string {
	$meridiem = ( 'AM' === $dt->format( 'A' ) ) ? 'A.M.' : 'P.M.';

	return $dt->format( 'g:i' ) . ' ' . $meridiem;
}

/**
 * The second Friday of the month containing $in, at the club's meeting time.
 *
 * The relative format "second friday of this month" is evaluated against the
 * month of $in and resets the clock to midnight, so the meeting time is set
 * afterwards. $in is normalised to midday first: that keeps a DST transition
 * from shifting the month underneath the calculation.
 *
 * @param DateTimeImmutable $in    Any instant inside the target month.
 * @param int               $hour  Meeting hour, 24h.
 * @param int               $min   Meeting minute.
 * @return DateTimeImmutable Second Friday at the meeting time, club-local.
 */
function maars_second_friday_of( DateTimeImmutable $in, int $hour = 18, int $min = 30 ): DateTimeImmutable {
	return $in->setTime( 12, 0, 0 )
		->modify( 'second friday of this month' )
		->setTime( $hour, $min, 0 );
}

/**
 * The next MAARS meeting, computed from the governing rule rather than typed
 * into a page by hand.
 *
 * Second Friday of the month, 6:30 P.M., America/Chicago. Once this month's
 * meeting start has passed, it rolls to the second Friday of next month. The
 * returned 'rule' string names its source so the page can show WHY the date is
 * what it is — a date with no visible provenance is the thing that rotted on
 * the old site.
 *
 * @param int|null $from_ts Instant to compute from, or null for now. Injectable so this is testable.
 * @return array{ts:int,iso:string,label:string,rule:string}
 */
function maars_next_meeting( ?int $from_ts = null ): array {
	$now     = maars_now_local( $from_ts );
	$meeting = maars_second_friday_of( $now );

	if ( $meeting->getTimestamp() < $now->getTimestamp() ) {
		$meeting = maars_second_friday_of( $now->modify( 'first day of next month' ) );
	}

	$next = array(
		'ts'    => $meeting->getTimestamp(),
		'iso'   => $meeting->format( 'Y-m-d' ),
		'label' => $meeting->format( 'l, F j, Y' ) . ' at ' . maars_club_time_label( $meeting ),
		/*
		 * The working, written as a sentence. It used to read "2nd Friday,
		 * 6:30 P.M. — MAARS Constitution & SOP, revised 11 Dec 2021": an
		 * abbreviated ordinal, an abbreviated document name and an abbreviated
		 * date, welded together with a dash. Three of those are figures set in
		 * prose, and the dash was doing the job a clause does. It is one line
		 * under a large date and it is read once, by somebody checking the
		 * arithmetic, so it can afford to be a sentence.
		 */
		'rule'  => __( 'Second Friday of the month at 6:30 P.M., under the Society’s constitution and standing operating procedures as revised on 11 December 2021.', 'maars' ),
	);

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter the computed next-meeting payload.
		 *
		 * @param array    $next    Meeting payload as documented above.
		 * @param int|null $from_ts Instant the computation started from.
		 */
		$next = (array) apply_filters( 'maars_next_meeting', $next, $from_ts );
	}

	return $next;
}

/**
 * Transient key holding the most recent publication date.
 */
function maars_last_publication_transient_key() {
	return 'maars_last_publication_date';
}

/**
 * Ask the database for the newest publication date, ignoring any cache.
 *
 * Two cheap queries, because the two clocks disagree: a document carries its
 * own date in `_maars_doc_date` (the day the newsletter is dated), while the
 * post carries the day it was imported. The later of the two wins, so a
 * back-dated import cannot make the site look fresher than it is, and an old
 * import of a new document is still counted.
 *
 * @return string Newest publication date as YYYY-MM-DD, or '' on an empty site.
 */
function maars_query_last_publication_date() {
	if ( ! class_exists( 'WP_Query' ) ) {
		return '';
	}

	$types = array( 'maars_publication', 'post' );

	if ( function_exists( 'apply_filters' ) ) {
		/**
		 * Filter which post types count as "a publication" for the staleness clock.
		 *
		 * @param string[] $types Post type slugs.
		 */
		$types = (array) apply_filters( 'maars_publication_post_types', $types );
	}

	$base = array(
		'post_type'              => $types,
		'post_status'            => 'publish',
		'posts_per_page'         => 1,
		'fields'                 => 'ids',
		'no_found_rows'          => true,
		'ignore_sticky_posts'    => true,
		'update_post_term_cache' => false,
	);

	$best = '';

	// 1. Newest by post date; prefer that post's own document date if it has one.
	$by_date = new WP_Query( array_merge( $base, array( 'orderby' => 'date', 'order' => 'DESC' ) ) );

	if ( ! empty( $by_date->posts ) ) {
		$post_id = (int) $by_date->posts[0];
		$doc     = maars_valid_ymd( get_post_meta( $post_id, '_maars_doc_date', true ) );

		if ( '' === $doc ) {
			$doc = maars_valid_ymd( substr( (string) get_post_field( 'post_date', $post_id ), 0, 10 ) );
		}

		$best = $doc;
	}

	// 2. Newest by document date. YYYY-MM-DD sorts correctly as a string.
	$by_doc = new WP_Query(
		array_merge(
			$base,
			array(
				'meta_key' => '_maars_doc_date', // phpcs:ignore WordPress.DB.SlowDBQuery.slow_db_query_meta_key
				'orderby'  => 'meta_value',
				'order'    => 'DESC',
			)
		)
	);

	if ( ! empty( $by_doc->posts ) ) {
		$doc = maars_valid_ymd( get_post_meta( (int) $by_doc->posts[0], '_maars_doc_date', true ) );

		if ( '' !== $doc && $doc > $best ) {
			$best = $doc;
		}
	}

	return $best;
}

/**
 * The date of the club's most recent publication, cached for an hour.
 *
 * Caches the date rather than the day count, so a cached value cannot make the
 * banner claim the club published today when it published yesterday. The
 * sentinel 'none' is stored for an empty site so that "we looked and found
 * nothing" is cached too, instead of re-running two queries on every request
 * against a database with no posts in it.
 *
 * @param bool $force Skip the cache and re-query.
 * @return string YYYY-MM-DD, or '' when the site has no publications at all.
 */
function maars_last_publication_date( $force = false ) {
	$key    = maars_last_publication_transient_key();
	$cached = ( ! $force && function_exists( 'get_transient' ) ) ? get_transient( $key ) : false;

	if ( is_string( $cached ) && '' !== $cached ) {
		return ( 'none' === $cached ) ? '' : maars_valid_ymd( $cached );
	}

	$found = maars_query_last_publication_date();

	if ( function_exists( 'set_transient' ) ) {
		$hour = defined( 'HOUR_IN_SECONDS' ) ? HOUR_IN_SECONDS : 3600;
		set_transient( $key, ( '' === $found ) ? 'none' : $found, $hour );
	}

	return $found;
}

/**
 * How many days the club has gone without publishing anything.
 *
 * This is the number the dateline banner exists to print, and the number the
 * old site never showed: on the day it was surveyed the honest answer was 608.
 *
 * Returns 0 on a site with no publications at all — the state the container is
 * in for the few seconds before the seed importer runs. Zero is the value that
 * renders harmlessly; callers that need to tell "published today" apart from
 * "nothing here yet" should check maars_last_publication_date() for ''.
 *
 * @return int Whole days since the most recent publication, never negative.
 */
function maars_days_since_last_publication(): int {
	$iso = maars_last_publication_date();

	if ( '' === $iso ) {
		return 0;
	}

	$days = maars_days_since_date( $iso );

	return ( null === $days ) ? 0 : (int) $days;
}

/**
 * Drop the cached publication date whenever content changes.
 *
 * Without this, publishing a newsletter would leave the banner insisting the
 * club had been silent for another hour.
 *
 * @param int|WP_Post|null $post_id Post ID passed by the hook. Unused.
 * @return void
 */
function maars_flush_freshness_cache( $post_id = 0 ) {
	unset( $post_id );

	if ( function_exists( 'delete_transient' ) ) {
		delete_transient( maars_last_publication_transient_key() );
	}
}

if ( function_exists( 'add_action' ) ) {
	add_action( 'save_post', 'maars_flush_freshness_cache' );
	add_action( 'deleted_post', 'maars_flush_freshness_cache' );
	add_action( 'trashed_post', 'maars_flush_freshness_cache' );
	add_action( 'untrashed_post', 'maars_flush_freshness_cache' );
}
