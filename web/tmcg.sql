CREATE TABLE user_roles (
    id BIGSERIAL NOT NULL PRIMARY KEY,
    cdate TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_role TEXT NOT NULL UNIQUE,
    descr text DEFAULT ''
);
CREATE TABLE user_role_permissions (
    id bigserial NOT NULL PRIMARY KEY,
    user_role BIGINT NOT NULL REFERENCES user_roles ON DELETE CASCADE ON UPDATE CASCADE,
    Sys_module TEXT NOT NULL, -- the name of the module - defined above this level
    sys_perms VARCHAR(16) NOT NULL,
    created timestamptz DEFAULT current_timestamp,
    updated timestamptz DEFAULT current_timestamp,
    UNIQUE(sys_module, user_role)
);

CREATE TABLE users (
    id bigserial NOT NULL PRIMARY KEY,
    cdate timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
    firstname TEXT NOT NULL DEFAULT '',
    lastname TEXT NOT NULL DEFAULT '',
    telephone TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL, -- blowfish hash of password
    email TEXT,
    user_role  BIGINT NOT NULL REFERENCES user_roles ON DELETE RESTRICT ON UPDATE CASCADE,
    transaction_limit TEXT DEFAULT '0/'||to_char(NOW(),'yyyymmdd'),
    is_active BOOLEAN NOT NULL DEFAULT 't',
    is_system_user BOOLEAN NOT NULL DEFAULT 'f',
    created timestamptz DEFAULT current_timestamp,
    updated timestamptz DEFAULT current_timestamp

);

CREATE TABLE kannel_stats(
    id SERIAL PRIMARY KEY NOT NULL,
    month TEXT NOT NULL DEFAULT '',
    stats JSON NOT NULL DEFAULT '{}'::json,
    created TIMESTAMP NOT NULL DEFAULT NOW(),
    updated TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE VIEW sms_stats AS
    SELECT
        id,
        month,
        stats->>'mtn_in' as mtn_in,
        stats->>'mtn_out' as mtn_out,
        stats->>'airtel_in' as airtel_in,
        stats->>'airtel_out' as airtel_out,
        stats->>'africel_in' as africel_in,
        stats->>'africel_out' as africel_out,
        stats->>'utl_in' as utl_in,
        stats->>'utl_out' as utl_out,
        stats->>'others_in' as others_in,
        stats->>'others_out' as others_out,
        stats->>'total_in' as total_in,
        stats->>'total_out' as total_out,
        created,
        updated
    FROM kannel_stats;

CREATE TABLE sessions (
    session_id CHAR(128) UNIQUE NOT NULL,
    atime TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    data TEXT
);

CREATE VIEW contacts_contactgroup_counts_view AS
    WITH t AS (
        SELECT count(*), contactgroup_id
        FROM contacts_contactgroup_contacts
        GROUP BY contactgroup_id
    )
    SELECT a.org_id, a.name, t.count, t.contactgroup_id
    FROM t, contacts_contactgroup a
    WHERE t.contactgroup_id = a.id;

--CREATE VIEW contacts_contactfield_counts_view AS
--    WITH select count(*), string_value from values_value where contact_field_id is not null group by string_value

CREATE OR REPLACE FUNCTION count_by_contactfield(fname text) RETURNS TABLE(count bigint, field text) AS
$delim$
    DECLARE
    fid int;
    -- fcount int := 0;
    BEGIN
        SELECT id INTO fid FROM contacts_contactfield WHERE label = fname;
        IF fid IS NOT NULL THEN
            RETURN QUERY SELECT count(*), string_value FROM values_value
            WHERE contact_field_id IS NOT NULL AND contact_field_id = fid
            GROUP BY string_value;
        END IF;
        RETURN;
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_event_count(idx int) RETURNS int AS
$delim$
    DECLARE
    count int;
    BEGIN
        SELECT count(*) INTO count FROM campaigns_campaignevent WHERE campaign_id = idx;
        IF count IS NOT NULL THEN
            RETURN count;
        END IF;
        RETURN 0;
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_message_event_count(idx int) RETURNS int AS
$delim$
    DECLARE
    count int;
    BEGIN
        SELECT count(*) INTO count FROM campaigns_campaignevent
        WHERE campaign_id = idx AND event_type = 'M';
        IF count IS NOT NULL THEN
            RETURN count;
        END IF;
        RETURN 0;
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_duration(idx int) RETURNS TEXT AS
$delim$
    DECLARE
    mcount interval := '00:00:00'::interval; --minute count
    hcount interval := '00:00:00'::interval;
    dcount interval := '00:00:00'::interval;
    wcount interval := '00:00:00'::interval; --week count
    BEGIN
        SELECT (max("offset") || ' minutes')::interval INTO mcount FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'M';
        SELECT (max("offset") || ' hours')::interval INTO hcount FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'H';
        SELECT (max("offset") || ' days')::interval INTO dcount FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'D';
        SELECT (max("offset") || ' weeks')::interval INTO wcount FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'W';

        IF wcount >  dcount AND wcount > hcount AND wcount > mcount THEN
            RETURN wcount::text || ' Weeks';
        ELSIF dcount > wcount AND dcount > hcount AND dcount > mcount THEN
            RETURN dcount::text || ' Days';
        ELSIF hcount > wcount AND hcount > dcount AND hcount > mcount THEN
            RETURN hcount::text || ' Hours';
        ELSE
            RETURN mcount::text || ' Minutes';
        END IF;
        RETURN '0';
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_duration_days(idx int) RETURNS TEXT AS
$delim$
    DECLARE
    dmax int = 0;
    dmin int = 0;
    BEGIN
        SELECT max("offset")  INTO dmax FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'D';

        SELECT min("offset")  INTO dmin FROM campaigns_campaignevent
        WHERE campaign_id = idx AND unit = 'D';


        IF dmax IS NOT NULL THEN
            IF dmin < 0 THEN
                dmax := dmax + (-1 * dmin);
            END IF;
            RETURN dmax || ' Days';
        END IF;
        RETURN '0 Days';
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_sent_sms_count(idx int) RETURNS int AS
$delim$
    -- counts messages in a given campaign drilling down to those in flows thereof
    DECLARE
    c int;
    d int;
    total int := 0;
    BEGIN
        -- count from the direct campaign messages
        FOR c IN SELECT count(contact_id) FROM flows_flowrun
            WHERE flow_id IN (
                SELECT flow_id FROM campaigns_campaignevent
                WHERE campaign_id = idx AND event_type = 'M') LOOP
            total := total + c;
        END LOOP;
        -- let us count from the other flows
        FOR d IN SELECT count(msg_id) FROM flows_flowstep_messages
            WHERE flowstep_id IN (SELECT id FROM flows_flowstep WHERE run_id IN
                (SELECT id FROM flows_flowrun WHERE flow_id IN (
                    SELECT flow_id FROM campaigns_campaignevent
                        WHERE campaign_id = idx AND event_type = 'F'))) LOOP
            total := total + d;
        END LOOP;
        RETURN total;
    END;
$delim$ LANGUAGE 'plpgsql';

-- select count(*) from flows_flowstep_messages where flowstep_id in (select id from flows_flowstep where run_id in (select id from flows_flowrun where flow_id = 26) and step_type ='A');

CREATE OR REPLACE FUNCTION campaign_completed_by(idx int) RETURNS int AS
$delim$
    -- assuming we're using days as the unit for the offset
    DECLARE
        max_id int; -- last step in campaign
        m int;
        ret int;
    BEGIN
        SELECT max("offset"), flow_id INTO m, max_id FROM campaigns_campaignevent
            WHERE campaign_id = idx AND unit = 'D'
            GROUP BY flow_id
            ORDER BY flow_id desc, max("offset") desc
            LIMIT 1;
        IF max_id IS NOT NULL THEN
            -- count contacts that have run this step.
            SELECT count(distinct contact_id) INTO ret FROM flows_flowrun
            WHERE flow_id = max_id;
            IF ret IS NOT NULL THEN
                RETURN ret;
            END IF;
        END IF;
        RETURN ret;
    END;
$delim$ LANGUAGE 'plpgsql';

-- number curruntly in campaign = those somewhere in the campaign minus those at last step

CREATE OR REPLACE FUNCTION campaign_total_contacts(idx int) RETURNS int AS
$delim$
    DECLARE
    c int := 0;
    BEGIN
        SELECT count(distinct contact_id) INTO c FROM flows_flowrun
        WHERE flow_id IN (SELECT flow_id FROM campaigns_campaignevent
            WHERE campaign_id = idx);
        RETURN c;
    END;
$delim$ LANGUAGE 'plpgsql';

CREATE OR REPLACE FUNCTION campaign_current_contacts(idx int) RETURNS int AS
$delim$
    DECLARE
    c int := 0;
    completed int := 0;
    BEGIN
        SELECT count(distinct contact_id) INTO c FROM flows_flowrun
        WHERE flow_id IN (SELECT flow_id FROM campaigns_campaignevent
            WHERE campaign_id = idx);
        SELECT campaign_completed_by(idx) INTO completed;
        RETURN c - completed;
    END;
$delim$ LANGUAGE 'plpgsql';

DROP VIEW IF EXISTS campaigns_view;
CREATE VIEW campaigns_view AS
    SELECT
        a.id, a.name, a.org_id, b.name group_name,
        campaign_event_count(a.id) events,
        campaign_message_event_count(a.id) msg_events,
        campaign_duration_days(a.id) duration,
        campaign_sent_sms_count(a.id) sent_sms,
        campaign_completed_by(a.id) completed_by,
        campaign_current_contacts(a.id) currently_in,
        campaign_total_contacts(a.id) total_contacts
    FROM campaigns_campaign a, contacts_contactgroup b
    WHERE a.group_id = b.id
    ORDER BY a.name;

CREATE OR REPLACE FUNCTION campaign_event_runs(event_id int) RETURNS int AS
$delim$
    DECLARE
     c int;
    completed int := 0;
    BEGIN
        SELECT count(distinct contact_id) INTO c FROM flows_flowrun
        WHERE flow_id = (SELECT flow_id FROM campaigns_campaignevent
            WHERE id = event_id);
        IF c IS NOT NULL THEN
            RETURN c;
        END IF;
        RETURN 0;
    END;
$delim$ LANGUAGE 'plpgsql';

DROP VIEW IF EXISTS campaigns_event_contacts_view;
CREATE VIEW campaigns_event_contacts_view AS
    SELECT a.campaign_id, "offset" AS day, a.unit, campaign_event_runs(a.id), b.label relative_to
    FROM campaigns_campaignevent a, contacts_contactfield b
    WHERE unit = 'D' AND a.relative_to_id = b.id
    ORDER BY campaign_id, day asc, a.id asc;

-- Data Follows
INSERT INTO user_roles(user_role, descr)
VALUES('Administrator','For the Administrators'), ('Basic', 'For the basic users');

INSERT INTO user_role_permissions(user_role, sys_module,sys_perms)
VALUES
        ((SELECT id FROM user_roles WHERE user_role ='Administrator'),'Users','rmad');

INSERT INTO users(firstname,lastname,username,password,email,user_role,is_system_user)
VALUES
        ('Samuel','Sekiwere','admin',crypt('admin',gen_salt('bf')),'sekiskylink@gmail.com',
        (SELECT id FROM user_roles WHERE user_role ='Administrator'),'t'),
        ('Guest','User','guest',crypt('guest',gen_salt('bf')),'sekiskylink@gmail.com',
        (SELECT id FROM user_roles WHERE user_role ='Basic'),'t');
