-- 008: Update get_dashboard_stats to accept optional p_topic_id parameter
-- When p_topic_id is NULL: aggregate across all companies (pre-migration behavior)
-- When p_topic_id is set: filter on company_topics where topic_id = p_topic_id
--   OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)
-- Requirements: 4.3, 4.6, 8.4, 9.2

DROP FUNCTION IF EXISTS get_dashboard_stats();
DROP FUNCTION IF EXISTS get_dashboard_stats(INTEGER);

CREATE OR REPLACE FUNCTION get_dashboard_stats(p_topic_id INTEGER DEFAULT NULL)
RETURNS json
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $fn$
DECLARE
    result          JSON;
    v_total         BIGINT;
    v_starred       BIGINT;
    v_with_contacts BIGINT;
    v_with_data     BIGINT;
    v_high_pot_new  BIGINT;
    v_needs_scoring BIGINT;
    v_scored_total  BIGINT;
    v_coverage      NUMERIC;
    v_by_region     JSON;
    v_by_crm        JSON;
    v_score_bkdn    JSON;
    v_by_source     JSON;
    v_starred_cos   JSON;
    v_conv_times    JSON;
    v_weekly_rates  JSON;
BEGIN
    -- ============================================================
    -- When p_topic_id is NULL: aggregate across ALL companies
    -- (equivalent to pre-migration behavior).
    -- When p_topic_id is set: only count companies that appear in
    -- company_topics for that topic or its direct children.
    -- ============================================================

    IF p_topic_id IS NULL THEN
        -- ── NULL path: pre-migration equivalent ──────────────────

        SELECT COUNT(*) INTO v_total FROM companies;
        SELECT COUNT(*) INTO v_starred FROM companies WHERE starred = true;
        SELECT COUNT(DISTINCT company_id) INTO v_with_contacts FROM contacts;
        SELECT COUNT(DISTINCT company_id) INTO v_with_data FROM company_data;

        SELECT COUNT(*) INTO v_high_pot_new
        FROM companies c
        JOIN company_topics ct ON ct.company_id = c.id
        WHERE c.crm_status = 'new' AND ct.score >= 8;

        SELECT COUNT(DISTINCT c.id) INTO v_needs_scoring
        FROM companies c
        LEFT JOIN company_topics ct ON ct.company_id = c.id
        WHERE ct.id IS NULL
           OR c.updated_at > ct.scored_at
           OR EXISTS (
               SELECT 1 FROM company_data cd
               WHERE cd.company_id = c.id AND cd.created_at > ct.scored_at
           );

        v_coverage := CASE WHEN v_total > 0
            THEN ROUND(v_with_data::NUMERIC / v_total * 100, 1)
            ELSE 0 END;

        SELECT COALESCE(json_object_agg(region, cnt), '{}')
        INTO v_by_region
        FROM (
            SELECT COALESCE(region, 'N/A') AS region, COUNT(*) AS cnt
            FROM companies GROUP BY region ORDER BY cnt DESC
        ) sub;

        SELECT COALESCE(json_object_agg(status, cnt), '{}')
        INTO v_by_crm
        FROM (
            SELECT COALESCE(crm_status, 'new') AS status, COUNT(*) AS cnt
            FROM companies GROUP BY crm_status
        ) sub;

        SELECT COUNT(*) INTO v_scored_total FROM company_topics WHERE score IS NOT NULL;

        SELECT json_agg(row_to_json(sub)) INTO v_score_bkdn
        FROM (
            SELECT label, companies FROM (
                VALUES
                    ('10', (SELECT COUNT(*) FROM company_topics WHERE score = 10)),
                    ('9',  (SELECT COUNT(*) FROM company_topics WHERE score = 9)),
                    ('8',  (SELECT COUNT(*) FROM company_topics WHERE score = 8)),
                    ('7',  (SELECT COUNT(*) FROM company_topics WHERE score = 7)),
                    ('6',  (SELECT COUNT(*) FROM company_topics WHERE score = 6)),
                    ('<6', (SELECT COUNT(*) FROM company_topics WHERE score >= 0 AND score <= 5))
            ) AS t(label, companies)
        ) sub;

        SELECT COALESCE(json_agg(row_to_json(sub)), '[]')
        INTO v_by_source
        FROM (
            SELECT source, COUNT(DISTINCT company_id) AS count
            FROM company_data GROUP BY source ORDER BY count DESC
        ) sub;

        SELECT COALESCE(json_agg(row_to_json(sub)), '[]')
        INTO v_starred_cos
        FROM (
            SELECT c.id, c.name, c.city, c.region, c.crm_status, c.starred,
                   COALESCE(ct_best.score, 0) AS score,
                   COALESCE(dc.cnt, 0) AS data_count
            FROM companies c
            LEFT JOIN LATERAL (
                SELECT score FROM company_topics
                WHERE company_id = c.id
                ORDER BY score DESC NULLS LAST LIMIT 1
            ) ct_best ON true
            LEFT JOIN (SELECT company_id, COUNT(*) AS cnt FROM company_data GROUP BY company_id) dc ON dc.company_id = c.id
            ORDER BY c.starred DESC, ct_best.score DESC NULLS LAST
            LIMIT 10
        ) sub;

        -- Conversion times (avg days between status transitions)
        SELECT json_build_object(
            'new_to_contacted',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cs_to.created_at - cs_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'new' AND s_to.name = 'contacted'
               AND cs_to.created_at > cs_from.created_at),
            'contacted_to_interested',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cs_to.created_at - cs_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'contacted' AND s_to.name = 'interested'
               AND cs_to.created_at > cs_from.created_at),
            'interested_to_negotiating',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cs_to.created_at - cs_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'interested' AND s_to.name = 'negotiating'
               AND cs_to.created_at > cs_from.created_at),
            'negotiating_to_customer',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cs_to.created_at - cs_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'negotiating' AND s_to.name = 'customer'
               AND cs_to.created_at > cs_from.created_at)
        ) INTO v_conv_times;

        -- Weekly rates
        SELECT json_build_object(
            'new_to_contacted',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cs_to.created_at) IS NOT NULL AND MAX(cs_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cs_to.created_at) - MIN(cs_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'new' AND s_to.name = 'contacted'
               AND cs_to.created_at > cs_from.created_at),
            'contacted_to_interested',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cs_to.created_at) IS NOT NULL AND MAX(cs_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cs_to.created_at) - MIN(cs_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'contacted' AND s_to.name = 'interested'
               AND cs_to.created_at > cs_from.created_at),
            'interested_to_negotiating',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cs_to.created_at) IS NOT NULL AND MAX(cs_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cs_to.created_at) - MIN(cs_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'interested' AND s_to.name = 'negotiating'
               AND cs_to.created_at > cs_from.created_at),
            'negotiating_to_customer',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cs_to.created_at) IS NOT NULL AND MAX(cs_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cs_to.created_at) - MIN(cs_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_statuses cs_from
             JOIN statuses s_from ON s_from.id = cs_from.status_id
             JOIN company_statuses cs_to ON cs_to.company_id = cs_from.company_id
             JOIN statuses s_to ON s_to.id = cs_to.status_id
             WHERE s_from.name = 'negotiating' AND s_to.name = 'customer'
               AND cs_to.created_at > cs_from.created_at)
        ) INTO v_weekly_rates;

    ELSE
        -- ── Topic-filtered path ──────────────────────────────────
        -- Resolve topic IDs: the selected topic + its direct children
        -- company_topics rows matching these topic IDs define the
        -- filtered company set.

        SELECT COUNT(DISTINCT ct.company_id) INTO v_total
        FROM company_topics ct
        WHERE ct.topic_id = p_topic_id
           OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id);

        SELECT COUNT(DISTINCT ct.company_id) INTO v_starred
        FROM company_topics ct
        JOIN companies c ON c.id = ct.company_id
        WHERE c.starred = true
          AND (ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id));

        SELECT COUNT(DISTINCT co.company_id) INTO v_with_contacts
        FROM contacts co
        JOIN company_topics ct ON ct.company_id = co.company_id
        WHERE ct.topic_id = p_topic_id
           OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id);

        SELECT COUNT(DISTINCT cd.company_id) INTO v_with_data
        FROM company_data cd
        JOIN company_topics ct ON ct.company_id = cd.company_id
        WHERE ct.topic_id = p_topic_id
           OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id);

        SELECT COUNT(DISTINCT ct.company_id) INTO v_high_pot_new
        FROM company_topics ct
        WHERE ct.crm_status = 'new' AND ct.score >= 8
          AND (ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id));

        SELECT COUNT(DISTINCT ct.company_id) INTO v_needs_scoring
        FROM company_topics ct
        JOIN companies c ON c.id = ct.company_id
        WHERE (ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))
          AND (ct.score IS NULL
               OR c.updated_at > ct.scored_at
               OR EXISTS (
                   SELECT 1 FROM company_data cd
                   WHERE cd.company_id = c.id AND cd.created_at > ct.scored_at
               ));

        v_coverage := CASE WHEN v_total > 0
            THEN ROUND(v_with_data::NUMERIC / v_total * 100, 1)
            ELSE 0 END;

        -- By region (filtered)
        SELECT COALESCE(json_object_agg(region, cnt), '{}')
        INTO v_by_region
        FROM (
            SELECT COALESCE(c.region, 'N/A') AS region, COUNT(DISTINCT c.id) AS cnt
            FROM companies c
            JOIN company_topics ct ON ct.company_id = c.id
            WHERE ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)
            GROUP BY c.region ORDER BY cnt DESC
        ) sub;

        -- By CRM status (use company_topics.crm_status when filtering by topic)
        SELECT COALESCE(json_object_agg(status, cnt), '{}')
        INTO v_by_crm
        FROM (
            SELECT COALESCE(ct.crm_status, 'new') AS status, COUNT(DISTINCT ct.company_id) AS cnt
            FROM company_topics ct
            WHERE ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)
            GROUP BY ct.crm_status
        ) sub;

        -- Score breakdown (filtered, using company_topics.score)
        SELECT COUNT(*) INTO v_scored_total
        FROM company_topics
        WHERE score IS NOT NULL
          AND (topic_id = p_topic_id
               OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id));

        SELECT json_agg(row_to_json(sub)) INTO v_score_bkdn
        FROM (
            SELECT label, companies FROM (
                VALUES
                    ('10', (SELECT COUNT(*) FROM company_topics WHERE score = 10
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))),
                    ('9',  (SELECT COUNT(*) FROM company_topics WHERE score = 9
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))),
                    ('8',  (SELECT COUNT(*) FROM company_topics WHERE score = 8
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))),
                    ('7',  (SELECT COUNT(*) FROM company_topics WHERE score = 7
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))),
                    ('6',  (SELECT COUNT(*) FROM company_topics WHERE score = 6
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))),
                    ('<6', (SELECT COUNT(*) FROM company_topics WHERE score >= 0 AND score <= 5
                            AND (topic_id = p_topic_id OR topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))))
            ) AS t(label, companies)
        ) sub;

        -- By source (filtered)
        SELECT COALESCE(json_agg(row_to_json(sub)), '[]')
        INTO v_by_source
        FROM (
            SELECT cd.source, COUNT(DISTINCT cd.company_id) AS count
            FROM company_data cd
            JOIN company_topics ct ON ct.company_id = cd.company_id
            WHERE ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)
            GROUP BY cd.source ORDER BY count DESC
        ) sub;

        -- Starred / most relevant companies (top 10, filtered)
        SELECT COALESCE(json_agg(row_to_json(sub)), '[]')
        INTO v_starred_cos
        FROM (
            SELECT c.id, c.name, c.city, c.region,
                   ct.crm_status, c.starred,
                   COALESCE(ct.score, 0) AS score,
                   COALESCE(dc.cnt, 0) AS data_count
            FROM company_topics ct
            JOIN companies c ON c.id = ct.company_id
            LEFT JOIN (SELECT company_id, COUNT(*) AS cnt FROM company_data GROUP BY company_id) dc ON dc.company_id = c.id
            WHERE ct.topic_id = p_topic_id
               OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)
            ORDER BY c.starred DESC, ct.score DESC NULLS LAST
            LIMIT 10
        ) sub;

        -- Conversion times (filtered via company_topic_statuses)
        SELECT json_build_object(
            'new_to_contacted',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cts_to.created_at - cts_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'new' AND s_to.name = 'contacted'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'contacted_to_interested',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cts_to.created_at - cts_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'contacted' AND s_to.name = 'interested'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'interested_to_negotiating',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cts_to.created_at - cts_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'interested' AND s_to.name = 'negotiating'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'negotiating_to_customer',
            (SELECT ROUND(AVG(EXTRACT(EPOCH FROM (cts_to.created_at - cts_from.created_at)) / 86400)::NUMERIC, 1)
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'negotiating' AND s_to.name = 'customer'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))
        ) INTO v_conv_times;

        -- Weekly rates (filtered via company_topic_statuses)
        SELECT json_build_object(
            'new_to_contacted',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cts_to.created_at) IS NOT NULL AND MAX(cts_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cts_to.created_at) - MIN(cts_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'new' AND s_to.name = 'contacted'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'contacted_to_interested',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cts_to.created_at) IS NOT NULL AND MAX(cts_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cts_to.created_at) - MIN(cts_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'contacted' AND s_to.name = 'interested'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'interested_to_negotiating',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cts_to.created_at) IS NOT NULL AND MAX(cts_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cts_to.created_at) - MIN(cts_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'interested' AND s_to.name = 'negotiating'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id))),
            'negotiating_to_customer',
            (SELECT CASE WHEN COUNT(*) > 0 AND MIN(cts_to.created_at) IS NOT NULL AND MAX(cts_to.created_at) IS NOT NULL
                THEN ROUND(COUNT(*)::NUMERIC / GREATEST(1, EXTRACT(EPOCH FROM (MAX(cts_to.created_at) - MIN(cts_to.created_at))) / 604800), 1)
                ELSE NULL END
             FROM company_topic_statuses cts_from
             JOIN statuses s_from ON s_from.id = cts_from.status_id
             JOIN company_topic_statuses cts_to ON cts_to.company_topic_id = cts_from.company_topic_id
             JOIN statuses s_to ON s_to.id = cts_to.status_id
             JOIN company_topics ct ON ct.id = cts_from.company_topic_id
             WHERE s_from.name = 'negotiating' AND s_to.name = 'customer'
               AND cts_to.created_at > cts_from.created_at
               AND (ct.topic_id = p_topic_id
                    OR ct.topic_id IN (SELECT id FROM topics WHERE parent_id = p_topic_id)))
        ) INTO v_weekly_rates;

    END IF;

    -- ── Assemble final JSON (same structure for both paths) ──────
    result := json_build_object(
        'total_companies',     v_total,
        'by_region',           v_by_region,
        'by_crm_status',       v_by_crm,
        'with_contacts',       v_with_contacts,
        'starred_count',       v_starred,
        'high_potential_new',   v_high_pot_new,
        'needs_scoring',       v_needs_scoring,
        'overall_coverage',    v_coverage,
        'with_data',           v_with_data,
        'score_breakdown',     v_score_bkdn,
        'scored_total',        v_scored_total,
        'by_source',           v_by_source,
        'not_interested_count', COALESCE((v_by_crm->>'not_interested')::BIGINT, 0),
        'starred_companies',   v_starred_cos,
        'conversion_times',    v_conv_times,
        'weekly_rates',        v_weekly_rates
    );

    RETURN result;
END;
$fn$;
