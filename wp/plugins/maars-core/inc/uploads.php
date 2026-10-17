<?php
/**
 * MAARS Core — the file types the Society's own archive is made of.
 *
 * The folder ks0man.com was built from holds the webmaster's design sources: a
 * TrueType font, two Photoshop files, an InDesign document, a PageMaker file.
 * The Society asked for every file in it to be on the site. WordPress's upload
 * list refuses all four kinds, and on this host an administrator's
 * `unfiltered_upload` capability is not honoured either -- WordPress maps it to
 * do_not_allow unless the host defines ALLOW_UNFILTERED_UPLOADS -- so the REST
 * upload failed with "Sorry, you are not allowed to upload this file type."
 *
 * This allows exactly those extensions, for users who can manage the site, and
 * nobody else. They are inert downloads: a browser does not execute a .psd or
 * a .ttf served as a file. A visitor, a contributor, or an author cannot
 * upload them.
 *
 * @package MAARS
 */

defined( 'ABSPATH' ) || exit;

/**
 * Extension => MIME type for the archive's source files.
 *
 * @return array<string,string>
 */
function maars_archive_source_types(): array {
	return array(
		'ttf'  => 'font/ttf',
		'psd'  => 'image/vnd.adobe.photoshop',
		'indd' => 'application/x-indesign',
		'pm'   => 'application/x-pagemaker',
		/* Allowed by WordPress already, then refused by its content sniff:
		   the webmaster's shirt-order list is plain text that finfo calls
		   something else. */
		'txt'  => 'text/plain',
	);
}

/**
 * Add the source types to the upload list, for site managers only.
 *
 * @param array $mimes Allowed types.
 * @return array
 */
function maars_archive_upload_mimes( $mimes ) {
	if ( ! function_exists( 'current_user_can' ) || ! current_user_can( 'manage_options' ) ) {
		return $mimes;
	}

	return array_merge( (array) $mimes, maars_archive_source_types() );
}
add_filter( 'upload_mimes', 'maars_archive_upload_mimes' );

/**
 * Trust the extension for these types, for site managers only.
 *
 * WordPress also sniffs the file's contents and refuses when the sniffed type
 * disagrees with the extension. A PageMaker file sniffs as
 * application/octet-stream and an InDesign file as nothing useful at all, so
 * the sniff would refuse what the list above allows.
 *
 * @param array  $data     What WordPress concluded.
 * @param string $file     Full path to the uploaded file.
 * @param string $filename The name it was uploaded under.
 * @return array
 */
function maars_archive_check_filetype( $data, $file, $filename ) {
	if ( ! function_exists( 'current_user_can' ) || ! current_user_can( 'manage_options' ) ) {
		return $data;
	}

	$ext   = strtolower( pathinfo( (string) $filename, PATHINFO_EXTENSION ) );
	$types = maars_archive_source_types();
	if ( isset( $types[ $ext ] ) ) {
		return array(
			'ext'             => $ext,
			'type'            => $types[ $ext ],
			'proper_filename' => false,
		);
	}

	return $data;
}
add_filter( 'wp_check_filetype_and_ext', 'maars_archive_check_filetype', 10, 3 );
