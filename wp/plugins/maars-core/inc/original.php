<?php
/**
 * MAARS Core — the original file behind an archive record.
 *
 * Why this file exists
 * --------------------
 * Every archive record page has a section headed "The original file". Until
 * this file it was static template text written for the public demonstration,
 * which shipped the archive's SHAPE without its contents, saying the files were
 * not part of it, with a button to the maintenance policy. Then the Society
 * published the record in full, every document went into the media library,
 * and that sentence stayed on 243 live pages -- each one now false, each one a
 * dead end.
 * A reader landing on the February 2023 minutes saw a title, a dash and no way
 * to open the minutes.
 *
 * maars/original-file renders what the record actually has: the file, its
 * format and size, a real link to it, and the same document in any other
 * format the club kept. An issue from the years when the newsletter was a web
 * page has no file of its own; its original is the page, and that page is in
 * ks0man-com-pages-as-served.zip (tools/bundle_served_pages.py), byte for byte
 * as ks0man.com served it. The record links the bundle and names its page.
 *
 * @package MAARS
 */

defined( 'ABSPATH' ) || exit;

/**
 * Attachment IDs for a record: the file that IS the document, then the same
 * document in other formats.
 *
 * Found in this order, because each source can be missing on a given site:
 *   1. _maars_attachment, written by tools/import_media.php and the REST tools;
 *   2. an attachment parented to the record;
 *   3. an attachment whose slug is the shipped name of _maars_source_file --
 *      tools/push_media.py uploads "newsletter_02-23.pdf" as
 *      "newsletter-02-23.pdf", and WordPress derives the slug from that.
 * What it never does is match on the stored file name: WordPress renames a
 * large upload to <name>-scaled.jpg, and matching on disk names is what put
 * fifteen duplicate photographs in the production library.
 *
 * @param int $post_id Publication ID.
 * @return array{primary:int,alternates:int[]} Attachment IDs; primary 0 when there is none.
 */
function maars_publication_files( int $post_id ): array {
	$out = array(
		'primary'    => 0,
		'alternates' => array(),
	);

	if ( $post_id < 1 || ! function_exists( 'get_post_meta' ) ) {
		return $out;
	}

	$is_attachment = static function ( $id ): bool {
		$id = (int) $id;
		return $id > 0 && 'attachment' === get_post_type( $id );
	};

	$primary = (int) get_post_meta( $post_id, '_maars_attachment', true );
	if ( ! $is_attachment( $primary ) ) {
		$primary = 0;
	}

	if ( 0 === $primary ) {
		$children = get_posts(
			array(
				'post_type'      => 'attachment',
				'post_status'    => 'inherit',
				'post_parent'    => $post_id,
				'posts_per_page' => 1,
				'orderby'        => 'ID',
				'order'          => 'ASC',
				'fields'         => 'ids',
			)
		);
		if ( $children ) {
			$primary = (int) $children[0];
		}
	}

	if ( 0 === $primary ) {
		$source = basename( (string) get_post_meta( $post_id, '_maars_source_file', true ) );
		$stem   = pathinfo( $source, PATHINFO_FILENAME );
		if ( '' !== $stem && ! preg_match( '/\.html?$/i', $source ) ) {
			$found = get_posts(
				array(
					'post_type'      => 'attachment',
					'post_status'    => 'inherit',
					'name'           => sanitize_title( $stem ),
					'posts_per_page' => 1,
					'fields'         => 'ids',
				)
			);
			if ( $found ) {
				$primary = (int) $found[0];
			}
		}
	}

	$out['primary'] = $primary;

	$listed = array_filter( explode( ',', (string) get_post_meta( $post_id, '_maars_alternates', true ) ) );
	foreach ( $listed as $id ) {
		$id = (int) $id;
		if ( $id !== $primary && $is_attachment( $id ) && ! in_array( $id, $out['alternates'], true ) ) {
			$out['alternates'][] = $id;
		}
	}

	return $out;
}

/**
 * The bundle of every page ks0man.com served, as it served them.
 *
 * Looked up by the name it shipped under (_maars_media_file, written by
 * tools/import_media.php) and then by slug, which is how a REST upload of
 * "ks0man-com-pages-as-served.zip" is named.
 *
 * @return int Attachment ID, 0 when the bundle is not on this site.
 */
function maars_served_pages_bundle(): int {
	static $found = null;
	if ( null !== $found ) {
		return $found;
	}
	$found = 0;

	$by_meta = get_posts(
		array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'meta_key'       => '_maars_media_file',
			'meta_value'     => 'ks0man-com-pages-as-served.zip',
		)
	);
	if ( $by_meta ) {
		$found = (int) $by_meta[0];
		return $found;
	}

	$by_slug = get_posts(
		array(
			'post_type'      => 'attachment',
			'post_status'    => 'inherit',
			'posts_per_page' => 1,
			'fields'         => 'ids',
			'name'           => 'ks0man-com-pages-as-served',
		)
	);
	if ( $by_slug ) {
		$found = (int) $by_slug[0];
	}

	return $found;
}

/**
 * What a file is, in words a reader uses: "PDF", "Word document".
 *
 * @param string $path File path or name.
 * @return string
 */
function maars_original_kind( string $path ): string {
	$ext   = strtolower( pathinfo( $path, PATHINFO_EXTENSION ) );
	$names = array(
		'pdf'  => __( 'PDF', 'maars' ),
		'doc'  => __( 'Word document', 'maars' ),
		'docx' => __( 'Word document', 'maars' ),
		'rtf'  => __( 'Rich Text document', 'maars' ),
		'txt'  => __( 'text file', 'maars' ),
		'xls'  => __( 'spreadsheet', 'maars' ),
		'xlsx' => __( 'spreadsheet', 'maars' ),
		'csv'  => __( 'spreadsheet (CSV)', 'maars' ),
		'pptx' => __( 'PowerPoint presentation', 'maars' ),
		'jpg'  => __( 'photograph', 'maars' ),
		'jpeg' => __( 'photograph', 'maars' ),
		'png'  => __( 'image', 'maars' ),
		'gif'  => __( 'image', 'maars' ),
		'mp4'  => __( 'video', 'maars' ),
		'zip'  => __( 'zip archive', 'maars' ),
	);

	return isset( $names[ $ext ] ) ? $names[ $ext ] : strtoupper( $ext );
}

/**
 * One attachment as the facts a reader needs: URL, shipped name, kind, size.
 *
 * @param int $id Attachment ID.
 * @return array{url:string,name:string,kind:string,size:string}|null
 */
function maars_original_describe( int $id ) {
	$url = wp_get_attachment_url( $id );
	if ( ! is_string( $url ) || '' === $url ) {
		return null;
	}

	/* The name the file was uploaded under, not the -scaled copy WordPress
	   may have made of a large image. */
	$path     = (string) get_attached_file( $id );
	$meta     = wp_get_attachment_metadata( $id );
	$original = is_array( $meta ) && ! empty( $meta['original_image'] ) ? (string) $meta['original_image'] : '';
	$name     = '' !== $original ? $original : basename( $path ? $path : $url );

	$bytes = ( $path && file_exists( $path ) ) ? (int) filesize( $path ) : 0;
	if ( $bytes < 1 && is_array( $meta ) && ! empty( $meta['filesize'] ) ) {
		$bytes = (int) $meta['filesize'];
	}

	return array(
		'url'  => $url,
		'name' => $name,
		'kind' => maars_original_kind( $name ),
		'size' => $bytes > 0 ? (string) size_format( $bytes, $bytes >= 1048576 ? 1 : 0 ) : '',
	);
}

/**
 * Render maars/original-file.
 *
 * @param array         $attributes Block attributes (none used).
 * @param string        $content    Unused.
 * @param WP_Block|null $block      Block instance, for postId context.
 * @return string
 */
function maars_render_original_file_block( $attributes = array(), $content = '', $block = null ): string {
	unset( $attributes, $content );

	$post_id = 0;
	if ( $block instanceof WP_Block && ! empty( $block->context['postId'] ) ) {
		$post_id = (int) $block->context['postId'];
	}
	if ( $post_id < 1 && function_exists( 'get_the_ID' ) ) {
		$post_id = (int) get_the_ID();
	}

	$files  = maars_publication_files( $post_id );
	$source = basename( (string) get_post_meta( $post_id, '_maars_source_file', true ) );
	$wrap   = function_exists( 'maars_blocks_wrapper_attributes' )
		? maars_blocks_wrapper_attributes( array( 'class' => 'maars-original-file' ) )
		: 'class="maars-original-file"';

	$primary = $files['primary'] ? maars_original_describe( $files['primary'] ) : null;

	if ( null === $primary ) {
		if ( preg_match( '/\.html?$/i', $source ) ) {
			/* An issue from the years when the newsletter WAS the web page. Its
			   original is that page, kept in the bundle of every page the old
			   site served -- which only holds what came from the old site. */
			$served = 0 === strpos( (string) get_post_meta( $post_id, '_maars_source_file', true ), 'mirror/ks0man.com/' )
				? maars_served_pages_bundle()
				: 0;
			$bundle = $served ? maars_original_describe( $served ) : null;

			$html  = '<div ' . $wrap . '>';
			$html .= '<p class="maars-fieldname">' . esc_html__( 'Published as', 'maars' ) . '</p>';
			$html .= '<p class="maars-original__file has-data-font-family">' . esc_html( $source ) . '</p>';
			if ( null === $bundle ) {
				return $html . '<p class="maars-original__note">'
					. esc_html__( 'This issue was published as a web page on ks0man.com, with no other file behind it. The text above is that page, carried over.', 'maars' )
					. '</p></div>';
			}

			$html .= '<p class="maars-original__detail">'
				. esc_html(
					sprintf(
						/* translators: %s: size of the zip archive, e.g. "604 KB". */
						__( 'Web page, inside a zip archive of %s', 'maars' ),
						'' !== $bundle['size'] ? $bundle['size'] : __( 'unknown size', 'maars' )
					)
				)
				. '</p>';
			$html .= '<div class="maars-original__actions"><div class="maars-original__get">'
				. '<a class="maars-original__link" href="' . esc_url( $bundle['url'] ) . '">'
				. esc_html__( 'Download the page as ks0man.com served it', 'maars' )
				. '</a></div></div>';
			$html .= '<p class="maars-original__note">'
				. esc_html(
					sprintf(
						/* translators: %s: the issue's file name, e.g. "newsletter_07-09.html". */
						__( 'This issue was published as a web page, with no other file behind it. The text above is that page, carried over. The download holds every page ks0man.com served, exactly as it served them; this issue is the file %s inside it.', 'maars' ),
						$source
					)
				)
				. '</p></div>';

			return $html;
		}

		return '<div ' . $wrap . '>'
			. '<p class="maars-original__note">'
			. esc_html__( 'The file this record describes is not on this site. If you have a copy, the Society would like it: see the contact page.', 'maars' )
			. '</p></div>';
	}

	$detail = $primary['kind'] . ( '' !== $primary['size'] ? ', ' . $primary['size'] : '' );

	$html  = '<div ' . $wrap . '>';
	$html .= '<p class="maars-fieldname">' . esc_html__( 'File', 'maars' ) . '</p>';
	$html .= '<p class="maars-original__file has-data-font-family">' . esc_html( $primary['name'] ) . '</p>';
	$html .= '<p class="maars-original__detail">' . esc_html( $detail ) . '</p>';
	$html .= '<div class="maars-original__actions"><div class="maars-original__get">'
		. '<a class="maars-original__link" href="' . esc_url( $primary['url'] ) . '">'
		. esc_html(
			sprintf(
				/* translators: %s: what the file is, e.g. "PDF", "Word document". */
				__( 'Open the original %s', 'maars' ),
				$primary['kind']
			)
		)
		. '</a></div></div>';

	$also = array();
	foreach ( $files['alternates'] as $id ) {
		$alt = maars_original_describe( (int) $id );
		if ( null === $alt ) {
			continue;
		}
		/* "a Word document", "an RTF file": the article belongs to the words
		   a reader sees, so it is chosen from them. */
		$article = preg_match( '/^[aeiou]/i', $alt['kind'] ) ? __( 'an', 'maars' ) : __( 'a', 'maars' );
		$also[]  = esc_html( $article ) . ' <a href="' . esc_url( $alt['url'] ) . '">' . esc_html( $alt['kind'] ) . '</a>'
			. ( '' !== $alt['size'] ? ' <span class="maars-original__size">(' . esc_html( $alt['size'] ) . ')</span>' : '' );
	}
	if ( $also ) {
		$last  = array_pop( $also );
		$list  = $also ? implode( ', ', $also ) . ' ' . esc_html__( 'and', 'maars' ) . ' ' . $last : $last;
		$html .= '<p class="maars-original__also">'
			. esc_html__( 'The Society also kept it as', 'maars' ) . ' ' . $list . '.</p>';
	}

	$html .= '<p class="maars-original__note">'
		. esc_html__( 'The file, not any text on this page, is the authority. Where the record above quotes it, the quotation was carried over by machine and can miss a table or a signature.', 'maars' )
		. '</p>';
	$html .= '</div>';

	return $html;
}

/**
 * Register maars/original-file.
 *
 * @return void
 */
function maars_register_original_block(): void {
	if ( ! function_exists( 'register_block_type' ) ) {
		return;
	}

	register_block_type(
		'maars/original-file',
		array(
			'api_version'     => 3,
			'title'           => __( 'Original file', 'maars' ),
			'description'     => __( 'The document an archive record describes: its file, format and size, a link to it, and the same document in any other format the club kept.', 'maars' ),
			'category'        => 'widgets',
			'icon'            => 'media-document',
			'keywords'        => array( 'archive', 'file', 'download', 'maars' ),
			'supports'        => array(
				'html'   => false,
				'anchor' => true,
			),
			'uses_context'    => array( 'postId' ),
			'render_callback' => 'maars_render_original_file_block',
		)
	);
}
add_action( 'init', 'maars_register_original_block', 10 );
