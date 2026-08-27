<?php
/**
 * Plugin Name: Aversa Appointments Connector
 * Description: Espone gli appuntamenti DCI a ControlloAccessi mediante Web Service REST firmato HMAC.
 * Version: 1.3.0
 */

defined('ABSPATH') || exit;

const AVERSA_APPOINTMENTS_ROUTE = 'aversa/v1';

function aversa_appointments_secret() {
    static $secret = null;
    if ($secret !== null) {
        return $secret;
    }
    $config_file = __DIR__ . '/aversa-appointments-connector-config.php';
    if (is_readable($config_file)) {
        $config = require $config_file;
        if (is_array($config) && !empty($config['shared_secret'])) {
            $secret = (string) $config['shared_secret'];
            return $secret;
        }
    }
    // Compatibilità con eventuali installazioni che usano wp-config.php.
    $secret = defined('AVERSA_APPOINTMENTS_CONNECTOR_SECRET') ? AVERSA_APPOINTMENTS_CONNECTOR_SECRET : '';
    return $secret;
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

function aversa_appointments_datetime($value) {
    if (!$value || strpos($value, '0000-00-00') === 0) {
        return null;
    }
    return str_replace(' ', 'T', $value) . 'Z';
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
    $sql = "SELECT ID, post_status, post_modified_gmt, post_date_gmt FROM {$wpdb->posts} WHERE {$where} ORDER BY post_modified_gmt ASC, ID ASC LIMIT %d OFFSET %d";
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
            'aggiornato_il' => aversa_appointments_datetime($post['post_modified_gmt']) ?: aversa_appointments_datetime($post['post_date_gmt']) ?: '1970-01-01T00:00:00Z',
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

function aversa_appointments_posts($post_type) {
    $posts = get_posts(array(
        'post_type' => $post_type,
        'post_status' => array('publish', 'private'),
        'numberposts' => -1,
        'orderby' => 'title',
        'order' => 'ASC',
    ));
    return array_map(function ($post) {
        return array('id' => (int) $post->ID, 'nome' => $post->post_title, 'stato' => $post->post_status);
    }, $posts);
}

function aversa_appointments_anagrafiche(WP_REST_Request $request) {
    global $wpdb;
    $calendari = $wpdb->get_results(
        "SELECT p.ID,
                MAX(CASE WHEN pm.meta_key = '_elios_gestione_caledario_ufficio' THEN pm.meta_value END) AS ufficio_id,
                MAX(CASE WHEN pm.meta_key = '_elios_gestione_caledario_luogo' THEN pm.meta_value END) AS sede_id
           FROM {$wpdb->posts} p
           LEFT JOIN {$wpdb->postmeta} pm ON pm.post_id = p.ID
          WHERE p.post_type = 'elios_calendario' AND p.post_status <> 'trash'
          GROUP BY p.ID
         HAVING ufficio_id IS NOT NULL AND sede_id IS NOT NULL",
        ARRAY_A
    );
    return rest_ensure_response(array(
        'sedi' => aversa_appointments_posts('luogo'),
        'uffici' => aversa_appointments_posts('unita_organizzativa'),
        'persone_pubbliche' => aversa_appointments_persone_pubbliche(),
        'calendari' => array_map(function ($calendario) {
            return array(
                'id' => (int) $calendario['ID'],
                'ufficio_id' => (string) $calendario['ufficio_id'],
                'sede_id' => (string) $calendario['sede_id'],
            );
        }, $calendari),
    ));
}

function aversa_appointments_persone_pubbliche() {
    $persone = get_posts(array(
        'post_type' => 'persona_pubblica',
        'post_status' => array('publish', 'private'),
        'numberposts' => -1,
        'orderby' => 'title',
        'order' => 'ASC',
    ));
    return array_map(function ($persona) {
        $organizzazioni = get_post_meta($persona->ID, '_dci_persona_pubblica_organizzazioni', true);
        if (!is_array($organizzazioni)) {
            $organizzazioni = array();
        }
        return array(
            'id' => (int) $persona->ID,
            'titolo' => $persona->post_title,
            'nome' => (string) get_post_meta($persona->ID, '_dci_persona_pubblica_nome', true),
            'cognome' => (string) get_post_meta($persona->ID, '_dci_persona_pubblica_cognome', true),
            'competenze' => (string) get_post_meta($persona->ID, '_dci_persona_pubblica_competenze', true),
            'attivo' => $persona->post_status === 'publish',
            'uffici' => array_values(array_map('strval', $organizzazioni)),
        );
    }, $persone);
}

function aversa_appointments_salva_organizzazioni_persona(WP_REST_Request $request) {
    $persona_id = (int) $request->get_param('persona_id');
    if (!$persona_id || get_post_type($persona_id) !== 'persona_pubblica') {
        return new WP_Error('aversa_person_not_found', 'Persona pubblica WordPress non trovata.', array('status' => 404));
    }
    $parametri = $request->get_json_params();
    $organizzazioni = isset($parametri['organizzazioni']) && is_array($parametri['organizzazioni']) ? $parametri['organizzazioni'] : array();
    $organizzazioni_valide = array();
    foreach ($organizzazioni as $ufficio_id) {
        $ufficio_id = (int) $ufficio_id;
        if (!$ufficio_id || get_post_type($ufficio_id) !== 'unita_organizzativa') {
            return new WP_Error('aversa_bad_office', 'Una delle unità organizzative non è valida.', array('status' => 400));
        }
        $organizzazioni_valide[] = $ufficio_id;
    }
    update_post_meta($persona_id, '_dci_persona_pubblica_organizzazioni', array_values(array_unique($organizzazioni_valide)));
    return rest_ensure_response(array('id' => $persona_id, 'aggiornato' => true));
}

function aversa_appointments_salva_persona_pubblica(WP_REST_Request $request) {
    $persona_id = (int) $request->get_param('persona_id');
    if (!$persona_id || get_post_type($persona_id) !== 'persona_pubblica') {
        return new WP_Error('aversa_person_not_found', 'Persona pubblica WordPress non trovata.', array('status' => 404));
    }
    $parametri = $request->get_json_params();
    $organizzazioni = isset($parametri['organizzazioni']) && is_array($parametri['organizzazioni']) ? $parametri['organizzazioni'] : array();
    $organizzazioni_valide = array();
    foreach ($organizzazioni as $ufficio_id) {
        $ufficio_id = (int) $ufficio_id;
        if (!$ufficio_id || get_post_type($ufficio_id) !== 'unita_organizzativa') {
            return new WP_Error('aversa_bad_office', 'Una delle unità organizzative non è valida.', array('status' => 400));
        }
        $organizzazioni_valide[] = $ufficio_id;
    }
    $attivo = !empty($parametri['attivo']);
    $esito = wp_update_post(array(
        'ID' => $persona_id,
        'post_title' => sanitize_text_field($parametri['titolo'] ?? ''),
        'post_status' => $attivo ? 'publish' : 'private',
    ), true);
    if (is_wp_error($esito)) {
        return $esito;
    }
    update_post_meta($persona_id, '_dci_persona_pubblica_nome', sanitize_text_field($parametri['nome'] ?? ''));
    update_post_meta($persona_id, '_dci_persona_pubblica_cognome', sanitize_text_field($parametri['cognome'] ?? ''));
    update_post_meta($persona_id, '_dci_persona_pubblica_competenze', wp_kses_post($parametri['competenze'] ?? ''));
    update_post_meta($persona_id, '_dci_persona_pubblica_organizzazioni', array_values(array_unique($organizzazioni_valide)));
    return rest_ensure_response(array('id' => $persona_id, 'aggiornato' => true));
}

function aversa_appointments_crea_persona_pubblica(WP_REST_Request $request) {
    $parametri = $request->get_json_params();
    $nome = sanitize_text_field($parametri['nome'] ?? '');
    $cognome = sanitize_text_field($parametri['cognome'] ?? '');
    $titolo = sanitize_text_field($parametri['titolo'] ?? trim($nome . ' ' . $cognome));
    if (!$titolo) {
        return new WP_Error('aversa_bad_person_name', 'Indicare almeno nome, cognome o titolo della Persona pubblica.', array('status' => 400));
    }
    $organizzazioni = isset($parametri['organizzazioni']) && is_array($parametri['organizzazioni']) ? $parametri['organizzazioni'] : array();
    $organizzazioni_valide = array();
    foreach ($organizzazioni as $ufficio_id) {
        $ufficio_id = (int) $ufficio_id;
        if (!$ufficio_id || get_post_type($ufficio_id) !== 'unita_organizzativa') {
            return new WP_Error('aversa_bad_office', 'Una delle unità organizzative non è valida.', array('status' => 400));
        }
        $organizzazioni_valide[] = $ufficio_id;
    }
    $persona_id = wp_insert_post(array(
        'post_type' => 'persona_pubblica',
        'post_status' => !empty($parametri['attivo']) ? 'publish' : 'private',
        'post_title' => $titolo,
    ), true);
    if (is_wp_error($persona_id)) {
        return $persona_id;
    }
    update_post_meta($persona_id, '_dci_persona_pubblica_nome', $nome);
    update_post_meta($persona_id, '_dci_persona_pubblica_cognome', $cognome);
    update_post_meta($persona_id, '_dci_persona_pubblica_competenze', wp_kses_post($parametri['competenze'] ?? ''));
    update_post_meta($persona_id, '_dci_persona_pubblica_organizzazioni', array_values(array_unique($organizzazioni_valide)));
    return rest_ensure_response(array(
        'id' => (int) $persona_id,
        'titolo' => get_the_title($persona_id),
        'nome' => $nome,
        'cognome' => $cognome,
        'attivo' => get_post_status($persona_id) === 'publish',
        'aggiornato' => true,
    ));
}

function aversa_appointments_crea_unita_organizzativa(WP_REST_Request $request) {
    $parametri = $request->get_json_params();
    $nome = sanitize_text_field($parametri['nome'] ?? '');
    if (!$nome) {
        return new WP_Error('aversa_bad_office_name', 'Il nome dell’unità organizzativa è obbligatorio.', array('status' => 400));
    }
    $unita_id = wp_insert_post(array(
        'post_type' => 'unita_organizzativa',
        'post_status' => 'publish',
        'post_title' => $nome,
    ), true);
    if (is_wp_error($unita_id)) {
        return $unita_id;
    }
    return rest_ensure_response(array(
        'id' => (int) $unita_id,
        'nome' => get_the_title($unita_id),
        'stato' => get_post_status($unita_id),
        'aggiornato' => true,
    ));
}

function aversa_appointments_salva_calendario(WP_REST_Request $request) {
    global $wpdb;
    $parametri = $request->get_json_params();
    $ufficio_id = isset($parametri['ufficio_id']) ? (string) $parametri['ufficio_id'] : '';
    $sede_id = isset($parametri['sede_id']) ? (string) $parametri['sede_id'] : '';
    $disponibilita = isset($parametri['disponibilita']) && is_array($parametri['disponibilita']) ? $parametri['disponibilita'] : array();
    if (!$ufficio_id || !$sede_id || !isset($disponibilita['durata_minuti']) || !isset($disponibilita['slot_per_giorno'])) {
        return new WP_Error('aversa_bad_calendar', 'Configurazione calendario non valida.', array('status' => 400));
    }

    $sql = "SELECT p.ID FROM {$wpdb->posts} p
            INNER JOIN {$wpdb->postmeta} u ON u.post_id = p.ID
            INNER JOIN {$wpdb->postmeta} s ON s.post_id = p.ID
            WHERE p.post_type = 'elios_calendario'
              AND p.post_status <> 'trash'
              AND u.meta_key = '_elios_gestione_caledario_ufficio' AND u.meta_value = %s
              AND s.meta_key = '_elios_gestione_caledario_luogo' AND s.meta_value = %s
            ORDER BY p.ID ASC LIMIT 1";
    $calendario_id = (int) $wpdb->get_var($wpdb->prepare($sql, $ufficio_id, $sede_id));
    $titolo = sanitize_text_field($parametri['titolo'] ?? 'Calendario appuntamenti');
    if (!$calendario_id) {
        $calendario_id = wp_insert_post(array(
            'post_type' => 'elios_calendario',
            'post_status' => 'publish',
            'post_title' => $titolo,
        ), true);
        if (is_wp_error($calendario_id)) {
            return $calendario_id;
        }
    } elseif ($titolo) {
        wp_update_post(array('ID' => $calendario_id, 'post_title' => $titolo));
    }

    $prefisso = '_elios_gestione_caledario_';
    $campi_giorno = array(
        '0' => 'disp_lunedi', '1' => 'disp_martedi', '2' => 'disp_mercoledi', '3' => 'disp_giovedi',
        '4' => 'disp_venerdi', '5' => 'disp_sabato', '6' => 'disp_domenica',
    );
    $configurazione = array($prefisso . 'disp_minuti' => max(5, (int) $disponibilita['durata_minuti']));
    foreach ($campi_giorno as $giorno => $campo) {
        $slot = isset($disponibilita['slot_per_giorno'][$giorno]) && is_array($disponibilita['slot_per_giorno'][$giorno])
            ? array_values(array_filter(array_map('sanitize_text_field', $disponibilita['slot_per_giorno'][$giorno])))
            : array();
        if ($slot) {
            $configurazione[$prefisso . $campo] = $slot;
        }
    }
    $eccezioni = array();
    foreach (($disponibilita['eccezioni'] ?? array()) as $eccezione) {
        $timestamp = strtotime($eccezione);
        if ($timestamp) {
            $eccezioni[] = $timestamp;
        }
    }
    update_post_meta($calendario_id, $prefisso . 'ufficio', $ufficio_id);
    update_post_meta($calendario_id, $prefisso . 'luogo', $sede_id);
    update_post_meta($calendario_id, $prefisso . 'box_disponibilita', array($configurazione));
    update_post_meta($calendario_id, $prefisso . 'group_eccezioni', array(array($prefisso . 'eccezioni' => $eccezioni)));
    return rest_ensure_response(array('id' => (int) $calendario_id, 'aggiornato' => true));
}

add_action('rest_api_init', function () {
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/anagrafiche', array(
        'methods' => WP_REST_Server::READABLE,
        'callback' => 'aversa_appointments_anagrafiche',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/calendari', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'aversa_appointments_salva_calendario',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/persone-pubbliche/(?P<persona_id>\d+)/organizzazioni', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'aversa_appointments_salva_organizzazioni_persona',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/persone-pubbliche/(?P<persona_id>\d+)', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'aversa_appointments_salva_persona_pubblica',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/persone-pubbliche', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'aversa_appointments_crea_persona_pubblica',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
    register_rest_route(AVERSA_APPOINTMENTS_ROUTE, '/unita-organizzative', array(
        'methods' => WP_REST_Server::CREATABLE,
        'callback' => 'aversa_appointments_crea_unita_organizzativa',
        'permission_callback' => 'aversa_appointments_authorized',
    ));
});
