<?php
/* Reproduce the wordpress image's wp-config-docker.php path:
   it eval()s the WORDPRESS_CONFIG_EXTRA value. That eval is where the site died. */
function getenv_docker($k,$d){ $v=getenv($k); return ($v!==false && $v!=='')?$v:$d; }
$compose_value = trim(shell_exec("cd " . escapeshellarg(dirname(__DIR__)) . " && python3 -c \"import yaml;print(yaml.safe_load(open('docker-compose.yml'))['services']['wordpress']['environment']['WORDPRESS_CONFIG_EXTRA'],end='')\""));
echo "compose value : " . var_export($compose_value, true) . "\n";
// point the require at the repo copy rather than the in-image path
$compose_value = str_replace('/usr/src/maars/site-url.php', dirname(__DIR__).'/docker/site-url.php', $compose_value);
$_SERVER = ['HTTP_HOST' => '192.168.0.10:3039'];
$r = @eval($compose_value);
if ($r === false && error_get_last()) { echo "EVAL FAILED: ".error_get_last()['message']."\n"; exit(1); }
echo "WP_HOME       : " . (defined('WP_HOME') ? WP_HOME : '(undefined)') . "\n";
echo "WP_SITEURL    : " . (defined('WP_SITEURL') ? WP_SITEURL : '(undefined)') . "\n";
echo "FILE_EDIT off : " . (defined('DISALLOW_FILE_EDIT') && DISALLOW_FILE_EDIT ? 'yes' : 'no') . "\n";
exit(defined('WP_HOME') && WP_HOME === 'http://192.168.0.10:3039' ? 0 : 1);
