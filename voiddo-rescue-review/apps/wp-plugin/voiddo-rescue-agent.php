<?php
/**
 * Plugin Name: Vøiddo Rescue Agent
 * Description: Read-only connection agent for Vøiddo Rescue health checks.
 * Version: 0.1.0
 * Author: vøiddo
 */

if (!defined('ABSPATH')) {
    exit;
}

define('VOIDDO_RESCUE_AGENT_VERSION', '0.1.0');

add_action('admin_menu', function () {
    add_options_page('Vøiddo Rescue Agent', 'Vøiddo Rescue', 'manage_options', 'voiddo-rescue-agent', 'voiddo_rescue_agent_settings_page');
});

function voiddo_rescue_agent_settings_page() {
    if (!current_user_can('manage_options')) {
        return;
    }
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && check_admin_referer('voiddo_rescue_agent_save')) {
        update_option('voiddo_rescue_agent_token', sanitize_text_field($_POST['voiddo_rescue_agent_token'] ?? ''));
        echo '<div class="updated"><p>Saved.</p></div>';
    }
    $token = esc_attr(get_option('voiddo_rescue_agent_token', ''));
    echo '<div class="wrap"><h1>Vøiddo Rescue Agent</h1>';
    echo '<p>Read-only MVP connector. No auto-updates, file edits, database edits, or destructive actions.</p>';
    echo '<form method="post">';
    wp_nonce_field('voiddo_rescue_agent_save');
    echo '<table class="form-table"><tr><th scope="row"><label for="voiddo_rescue_agent_token">Connect token</label></th><td><input class="regular-text" id="voiddo_rescue_agent_token" name="voiddo_rescue_agent_token" value="' . $token . '"></td></tr></table>';
    submit_button('Save token');
    echo '</form></div>';
}

add_action('rest_api_init', function () {
    register_rest_route('voiddo-rescue/v1', '/health', array(
        'methods' => 'GET',
        'callback' => 'voiddo_rescue_agent_health',
        'permission_callback' => '__return_true',
    ));
    register_rest_route('voiddo-rescue/v1', '/version', array(
        'methods' => 'GET',
        'callback' => 'voiddo_rescue_agent_version',
        'permission_callback' => '__return_true',
    ));
    register_rest_route('voiddo-rescue/v1', '/inventory', array(
        'methods' => 'GET',
        'callback' => 'voiddo_rescue_agent_inventory',
        'permission_callback' => 'voiddo_rescue_agent_authorized',
    ));
    register_rest_route('voiddo-rescue/v1', '/scan', array(
        'methods' => 'GET',
        'callback' => 'voiddo_rescue_agent_read_only_scan',
        'permission_callback' => 'voiddo_rescue_agent_authorized',
    ));
});

function voiddo_rescue_agent_authorized($request) {
    $saved = get_option('voiddo_rescue_agent_token', '');
    $provided = $request->get_header('x-voiddo-rescue-token');
    return $saved && $provided && hash_equals($saved, $provided);
}

function voiddo_rescue_agent_health() {
    return array('ok' => true, 'plugin' => 'voiddo-rescue-agent', 'read_only' => true);
}

function voiddo_rescue_agent_version() {
    return array('version' => VOIDDO_RESCUE_AGENT_VERSION, 'wordpress' => get_bloginfo('version'));
}

function voiddo_rescue_agent_inventory() {
    return array(
        'plugins' => get_plugins(),
        'theme' => wp_get_theme()->get('Name'),
        'read_only' => true,
    );
}

function voiddo_rescue_agent_read_only_scan() {
    return array(
        'site_url' => site_url(),
        'home_url' => home_url(),
        'name' => get_bloginfo('name'),
        'description' => get_bloginfo('description'),
        'read_only' => true,
    );
}
