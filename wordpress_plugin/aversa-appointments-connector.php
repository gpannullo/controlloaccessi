<?php
/**
 * Plugin Name: Aversa Appointments Connector
 * Description: Espone gli appuntamenti DCI a ControlloAccessi mediante Web Service REST firmato HMAC.
 * Version: 1.0.0
 */

defined('ABSPATH') || exit;

const AVERSA_APPOINTMENTS_ROUTE = 'aversa/v1';

function aversa_appointments_secret() {
    return defined('AVERSA_APPOINTMENTS_CONNECTOR_SECRET') ? AVERSA_APPOINTMENTS_CONNECTOR_SECRET : '';
}

function aversa_appointments_authorized(WP_REST_Request $request) {
    $secret = aversa_appointments_secret();
    $timestamp = $request->get_header('x-aversa-timestamp');
    $signature = $request->get_header('x-aversa-signature');
    if (!$secret || !$timestamp || !$signature || !ctype_digit($timestamp) || abs(time() - (int) $timestamp) > 300) {
        return new WP_Error('aversa_forbidden', 'Autorizzazione WS non valida.', array('status' => 401));
    }
    $expected = hash_hmac('sha256', $timestamp, $secret);
    if (!hash_equals($expected, $signature)) {
        return new WP_Error('aversa_forbidden', 'Firma WS non valida.', array('status' => 401));
    }
    return true;
}

function aversa_appointments_meta($post_ids) {
    global $wpdb;
    if (!$post_ids) {
        return array();
    }
    $keys = array(
        '_dci_appuntamento_codice_fiscale',
        '_dci_appuntamento_data_ora_fine_appuntamento',
        '_dci_appuntamento_data_ora_inizio_appuntamento',
        '_dci_appuntamento_data_ora_prenotazione',
        '_dci_appuntamento_dettaglio_richiesta',
        '_dci_appuntamento_email_richiedente',
        '_dci_appuntamento_id_place',
        '_dci_appuntamento_id_unita_organizzativa',
        '_dci_appuntamento_servizio',
        '_dci_appuntamento_unita_organizzativa',
    );
    $placeholders = implode(',', array_fill(0, count($post_ids), '%d'));
    $key_placeholders = implode(',', array_fill(0, count($keys), '%s'));
    $sql = "SELECT post_id, meta_key, meta_value FROM {$wpdb->postmeta} WHERE post_id IN ({$placeholders}) AND meta_key IN ({$key_placeholders})";
    $rows = $wpdb->get_results($wpdb->prepare($sql, array_merge($post_ids, $keys)), ARRAY_A);
    $result = array();
    foreach ($rows as $row) {
        $result[$row['post_id']][$row['meta_key']] = $row['meta_value'];
    }
    return $result;
}

function aversa_appointments_list(WP_REST_Request $request) {
    global $wpdb;
    $page = max(1, (int) $request->get_param('page'));
    $per_page = min(100, max(1, (int) $request->get_param('per_page') ?: 100));
    $updated_after = $request->get_param('updated_after');
    $where = $wpdb->prepare("post_type = %s AND post_status <> %s", 'appuntamento', 'trash');
    if ($updated_after) {
        $date = date_create($updated_after);
        if (!$date) {
            return new WP_Error('aversa_bad_date', 'updated_after non valida.', array('status' => 400));
        }
        $where .= $wpdb->prepare(' AND post_modified_gmt > %s', $date->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s'));
    }
    $offset = ($page - 1) * $per_page;
    $sql = "SELECT ID, post_status, post_modified_gmt FROM {$wpdb->posts} WHERE {$where} ORDER BY post_modified_gmt ASC, ID ASC LIMIT %d OFFSET %d";
    $posts = $wpdb->get_results($wpdb->prepare($sql, $per_page + 1, $offset), ARRAY_A);
    $has_more = count($posts) > $per_page;
    $posts = array_slice($posts, 0, $per_page);
    $meta = aversa_appointments_meta(wp_list_pluck($posts, 'ID'));
    $items = array();
    foreach ($posts as $post) {
        $data = isset($meta[$post['ID']]) ? $meta[$post['ID']] : array();
        $items[] = array(
            'id' => (int) $post['ID'],
            'stato' => $post['post_status'],
            'aggiornato_il' => str_replace(' ', 'T', $post['post_modified_gmt']) . 'Z',
            'prenotato_il' => $data['_dci_appuntamento_data_ora_prenotazione'] ?? null,
            'data_ora_inizio' => $data['_dci_appuntamento_data_ora_inizio_appuntamento'] ?? null,
            'data_ora_fine' => $data['_dci_appuntamento_data_ora_fine_appuntamento'] ?? null,
            'unita_organizzativa_id' => $data['_dci_appuntamento_id_unita_organizzativa'] ?? null,
            'unita_organizzativa' => $data['_dci_appuntamento_unita_organizzativa'] ?? null,
            'luogo_id' => $data['_dci_appuntamento_id_place'] ?? null,
            'servizio' => $data['_dci_appuntamento_servizio'] ?? null,
            'email' => $data['_dci_appuntamento_email_richiedente'] ?? null,
            'codice_fiscale' => $data['_dci_appuntamento_codice_fiscale'] ?? null,
            'dettaglio_richiesta' => $data['_dci_appuntamento_dettaglio_richiesta'] ?? null,
        );
    }
    return rest_ensure_response(array('items' => $items, 'page' => $page, 'per_page' => $per_page, 'has_more' => $has_more));
}

add_action('rest_api_init', function () {
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/appuntamenti', array(
        'methods' => WP_REST_Server::READABLE,
        'callback' => 'aversa_appointments_list',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
});
