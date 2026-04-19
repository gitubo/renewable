-- 009: Create cross-selling opportunities RPC function
-- Requirements: 6.1, 6.3, 6.4, 8.6
-- Returns companies that are 'customer' for source topic and have 'new' or no association for target topic

CREATE OR REPLACE FUNCTION get_cross_selling_opportunities(
    p_source_topic_id INTEGER,
    p_target_topic_id INTEGER
) RETURNS JSON AS $$
DECLARE result JSON;
BEGIN
    SELECT json_agg(row_to_json(sub)) INTO result
    FROM (
        SELECT c.id, c.name, c.city, c.region,
               ct_src.crm_status AS source_status
        FROM companies c
        JOIN company_topics ct_src ON ct_src.company_id = c.id
            AND ct_src.topic_id = p_source_topic_id
            AND ct_src.crm_status = 'customer'
        LEFT JOIN company_topics ct_tgt ON ct_tgt.company_id = c.id
            AND ct_tgt.topic_id = p_target_topic_id
        WHERE ct_tgt.id IS NULL
           OR ct_tgt.crm_status = 'new'
        ORDER BY c.name
    ) sub;
    RETURN COALESCE(result, '[]'::json);
END;
$$ LANGUAGE plpgsql;
