<?php
define('ABSPATH', __DIR__ . '/');
@mkdir(__DIR__ . '/out', 0777, true);
define('HOUR_IN_SECONDS',3600);
// --- minimal WordPress surface -------------------------------------------
function __($s,$d=''){return $s;} function _x($s,$c,$d=''){return $s;}
function _n($a,$b,$n,$d=''){return $n==1?$a:$b;}
function esc_html($s){return htmlspecialchars((string)$s,ENT_QUOTES,'UTF-8');}
function esc_attr($s){return htmlspecialchars((string)$s,ENT_QUOTES,'UTF-8');}
function esc_url($s){return $s;} function wp_kses_post($s){return $s;}
function esc_html__($s,$d=''){return esc_html($s);} function esc_attr__($s,$d=''){return esc_attr($s);}
function esc_html_e($s,$d=''){echo esc_html($s);} function esc_attr_e($s,$d=''){echo esc_attr($s);}
function esc_html_x($s,$c,$d=''){return esc_html($s);} function number_format_i18n($n,$d=0){return number_format($n,$d);}
function wp_parse_args($a,$d=array()){return array_merge($d,is_array($a)?$a:array());}
function wp_strip_all_tags($s){return strip_tags((string)$s);}
function is_string_($v){return is_string($v);}
function wp_json_encode($v,$f=0){return json_encode($v,$f);}
function wp_list_pluck($a,$k){return array_map(fn($x)=>is_array($x)?($x[$k]??null):($x->$k??null),$a);}
function wp_date($f,$t=null,$tz=null){return date($f,$t??time());}
function get_option($k,$d=false){return ['timezone_string'=>'America/Chicago','date_format'=>'F j, Y','blogname'=>'MAARS'][$k]??$d;}
function get_posts($a=[]){return [];} function get_post_meta($id,$k='',$s=false){return $s?'':[];}
function get_post_field($f,$p=0){return '';}
function get_block_wrapper_attributes($e=[]){
  $c=trim(($e['class']??'')); $s=trim(($e['style']??''));
  return 'class="wp-block-maars-skywave'.($c?' '.esc_attr($c):'').'"'.($s?' style="'.esc_attr($s).'"':'');
}
$GLOBALS['__inline']=[]; $GLOBALS['__enq']=[];
$GLOBALS['__registered']=['maars-skywave']; // the maars theme registers this handle
function wp_script_is($h,$l='enqueued'){
  if($l==='registered') return in_array($h,$GLOBALS['__registered'],true);
  return in_array($h,$GLOBALS['__enq'],true);}
function wp_enqueue_script($h,...$r){$GLOBALS['__enq'][]=$h;}
function wp_add_inline_script($h,$js,$pos='after'){$GLOBALS['__inline'][]=$js;return true;}
function register_block_type($n,$a=[]){$GLOBALS['__blocks'][$n]=$a;return true;}
function add_action($h,$c,$p=10,$n=1){return true;} function add_filter(...$a){return true;}
function apply_filters($t,$v,...$r){return $v;} function absint($v){return abs((int)$v);}
function sanitize_text_field($v){return trim(strip_tags((string)$v));}
function sanitize_key($v){return strtolower(preg_replace('/[^a-z0-9_\-]/i','',(string)$v));}
function get_transient($k){return false;} function set_transient($k,$v,$e=0){return true;}
function current_time($t,$g=0){return time();} function wp_timezone(){return new DateTimeZone('America/Chicago');}
function wp_timezone_string(){return 'America/Chicago';}
function trailingslashit($s){return rtrim($s,'/').'/';}
function get_template_directory_uri(){return 'THEMEURI';}
require __DIR__ . '/../wp/plugins/maars-core/inc/freshness.php';
require __DIR__ . '/../wp/plugins/maars-core/inc/blocks.php';

// run the real registration + bootstrap, then the real render callback
if (function_exists('maars_register_blocks')) maars_register_blocks();
if (function_exists('maars_blocks_skywave_bootstrap')) maars_blocks_skywave_bootstrap();
$html = maars_render_skywave_block(['band'=>'80m','caption'=>'Schematic, not a propagation prediction.']);
file_put_contents(__DIR__ . '/out/block.html', $html);
file_put_contents(__DIR__ . '/out/inline.js', implode("\n", $GLOBALS['__inline']));
fwrite(STDERR, "rendered ".strlen($html)." bytes; inline scripts: ".count($GLOBALS['__inline']).
  "; enqueued: ".implode(',', $GLOBALS['__enq'])."\n");
