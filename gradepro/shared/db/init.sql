-- GradePro Database Initialization Script
-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Roles & Users Setup
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_rw') THEN
        CREATE ROLE app_rw WITH LOGIN PASSWORD 'gradepro_dev_password';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_ro') THEN
        CREATE ROLE app_ro WITH LOGIN PASSWORD 'gradepro_readonly_password';
    END IF;
END $$;

-- 1. Organizations & Hierarchy
CREATE TABLE IF NOT EXISTS colleges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    centre_patterns TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS awarding_bodies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    awarding_body_id UUID NOT NULL REFERENCES awarding_bodies(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id UUID REFERENCES courses(id) ON DELETE SET NULL,
    awarding_body_id UUID REFERENCES awarding_bodies(id) ON DELETE CASCADE,
    unit_code TEXT NOT NULL,
    unit_name TEXT NOT NULL,
    level TEXT NOT NULL,
    tier SMALLINT NOT NULL DEFAULT 0, -- 0=cold, 1=warm, 2=trained, 3=mature
    submission_count INTEGER NOT NULL DEFAULT 0,
    has_training_data BOOLEAN NOT NULL DEFAULT FALSE,
    active_model_version INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_units_lookup ON units(unit_code, awarding_body_id, level);

-- 2. Versioned Criteria & Context
CREATE TABLE IF NOT EXISTS unit_criteria_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    criteria_json JSONB NOT NULL,
    lo_count INTEGER NOT NULL DEFAULT 0,
    ac_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    changed_by UUID,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    change_notes TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (unit_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_criteria_active ON unit_criteria_versions(unit_id) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS unit_contexts (
    unit_id UUID PRIMARY KEY REFERENCES units(id) ON DELETE CASCADE,
    criteria_version_id UUID REFERENCES unit_criteria_versions(id) ON DELETE SET NULL,
    few_shot_examples JSONB DEFAULT '[]'::jsonb,
    tone_guide TEXT DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Versioned Models
CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    storage_path_r2 TEXT NOT NULL,
    f1_score FLOAT DEFAULT 0.0,
    refer_recall FLOAT DEFAULT 0.0,
    refer_precision FLOAT DEFAULT 0.0,
    accuracy FLOAT DEFAULT 0.0,
    auc FLOAT DEFAULT 0.0,
    training_samples INTEGER DEFAULT 0,
    criteria_version_id UUID REFERENCES unit_criteria_versions(id) ON DELETE SET NULL,
    tier SMALLINT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW', -- PENDING_REVIEW, ACTIVE, RETIRED
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    promoted_by UUID,
    promoted_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (unit_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_model_active_per_unit ON model_registry(unit_id) WHERE is_active = TRUE;

-- 4. Versioned Feedback Templates
CREATE TABLE IF NOT EXISTS feedback_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    college_id UUID NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    storage_path_r2 TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    uploaded_by UUID,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (unit_id, college_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_template_active ON feedback_templates(unit_id, college_id) WHERE is_active = TRUE;

-- 5. Versioned Format Rules
CREATE TABLE IF NOT EXISTS format_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    college_id UUID NOT NULL REFERENCES colleges(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    rules_json JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notes TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (college_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_format_rules_active ON format_rules(college_id) WHERE is_active = TRUE;

-- 6. Users & Authentication
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'MAIN_ASSESSOR', 'ASSESSOR')),
    college_id UUID REFERENCES colleges(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_unit_assignments (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, unit_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(refresh_token_hash);

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    provider TEXT NOT NULL, -- openai, anthropic, gemini, groq
    key_encrypted TEXT NOT NULL,
    daily_limit INTEGER DEFAULT 1000,
    requests_today INTEGER DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    rate_limit_cooldown_until TIMESTAMPTZ,
    added_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_apikeys_provider_active ON api_keys(provider) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS ollama_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    context_window INTEGER DEFAULT 8192,
    is_active BOOLEAN NOT NULL DEFAULT FALSE
);

-- 7. Grading Pipeline Jobs & Results
CREATE TABLE IF NOT EXISTS grading_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    assessor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
    college_id UUID REFERENCES colleges(id) ON DELETE SET NULL,
    student_name TEXT NOT NULL,
    student_id TEXT DEFAULT '',
    file_hash TEXT NOT NULL,
    file_path_r2 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, parsing, evaluating, complete, failed
    overall_verdict TEXT, -- pass, refer
    model_version_id UUID REFERENCES model_registry(id) ON DELETE SET NULL,
    criteria_version_id UUID REFERENCES unit_criteria_versions(id) ON DELETE SET NULL,
    format_rules_version_id UUID REFERENCES format_rules(id) ON DELETE SET NULL,
    error_message TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_jobs_assessor_status ON grading_jobs(assessor_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_pending ON grading_jobs(created_at ASC) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_jobs_fts ON grading_jobs USING GIN(to_tsvector('english', student_name));

CREATE TABLE IF NOT EXISTS grading_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES grading_jobs(id) ON DELETE CASCADE,
    task_number SMALLINT NOT NULL,
    task_heading TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL, -- pass, refer
    confidence FLOAT DEFAULT 0.0,
    submodel_pass_prob FLOAT DEFAULT 0.0,
    submodel_criterion_scores JSONB DEFAULT '[]'::jsonb,
    reasoning_text TEXT NOT NULL DEFAULT '',
    feedback_text TEXT NOT NULL DEFAULT '',
    weak_areas JSONB DEFAULT '[]'::jsonb,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_detection_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES grading_jobs(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    score FLOAT NOT NULL,
    flagged BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_detection_job ON ai_detection_results(job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS plagiarism_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES grading_jobs(id) ON DELETE CASCADE,
    model_version TEXT NOT NULL,
    overall_similarity_pct FLOAT NOT NULL,
    top_matches JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_plagiarism_job ON plagiarism_results(job_id, created_at DESC);

CREATE TABLE IF NOT EXISTS final_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL UNIQUE REFERENCES grading_jobs(id) ON DELETE CASCADE,
    overall_verdict TEXT NOT NULL,
    overall_comment TEXT NOT NULL DEFAULT '',
    template_version_id UUID REFERENCES feedback_templates(id) ON DELETE SET NULL,
    pdf_path_r2 TEXT NOT NULL,
    pdf_url_expires_at TIMESTAMPTZ,
    assessor_override BOOLEAN NOT NULL DEFAULT FALSE,
    override_by UUID REFERENCES users(id) ON DELETE SET NULL,
    override_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 8. Immutable Audit Log
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id UUID,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_log(resource_type, resource_id);

-- 9. Initial Seed Data
INSERT INTO colleges (name, code, centre_patterns) VALUES
    ('International Learning College', 'ILC', ARRAY['international learning', 'ilc']),
    ('UK Professional Development Academy', 'UKPDA', ARRAY['uk professional development', 'ukpda'])
ON CONFLICT (code) DO NOTHING;

INSERT INTO awarding_bodies (name, code) VALUES
    ('Qualifi', 'QUALIFI'),
    ('OTHM Qualifications', 'OTHM'),
    ('NOCN', 'NOCN'),
    ('ATHE', 'ATHE')
ON CONFLICT (code) DO NOTHING;

-- Seed default admin user (Password: Admin123! hashed with bcrypt)
INSERT INTO users (email, password_hash, name, role) VALUES
    ('admin@gradepro.ai', '$2a$12$e8rGgH6y1k6kX0T3bW2mKe7k0j8k5Z2g7W5f5v4q9t3j1r2s3t4u5', 'System Administrator', 'ADMIN')
ON CONFLICT (email) DO NOTHING;

-- Seed default HSC301 unit
DO $$
DECLARE
    ab_id UUID;
    u_id UUID;
    c_ilc_id UUID;
    c_ukpda_id UUID;
BEGIN
    SELECT id INTO ab_id FROM awarding_bodies WHERE code = 'QUALIFI' LIMIT 1;
    SELECT id INTO c_ilc_id FROM colleges WHERE code = 'ILC' LIMIT 1;
    SELECT id INTO c_ukpda_id FROM colleges WHERE code = 'UKPDA' LIMIT 1;

    IF ab_id IS NOT NULL THEN
        INSERT INTO units (awarding_body_id, unit_code, unit_name, level, tier, has_training_data)
        VALUES (ab_id, 'HSC301', 'An Introduction to Health and Social Care', 'Level 3', 2, TRUE)
        ON CONFLICT (unit_code, awarding_body_id, level) DO NOTHING
        RETURNING id INTO u_id;

        IF u_id IS NULL THEN
            SELECT id INTO u_id FROM units WHERE unit_code = 'HSC301' LIMIT 1;
        END IF;

        IF u_id IS NOT NULL THEN
            INSERT INTO unit_criteria_versions (unit_id, version_number, criteria_json, lo_count, ac_count, is_active)
            VALUES (
                u_id,
                1,
                '{"unit_code": "HSC301", "unit_name": "An Introduction to Health and Social Care", "level": "Level 3", "tasks": [{"task_number": 1, "title": "Understand the role of the health and social care worker", "word_count_target": [450, 550], "criteria": ["1.1 Explain how a working relationship is different from a personal relationship", "1.2 Describe different working relationships in health and social care"]}, {"task_number": 2, "title": "Understand the importance of communication in adult social care settings", "word_count_target": [1450, 1550], "criteria": ["2.1 Identify different reasons people communicate", "2.2 Explain how effective communication affects all aspects of working in adult social care"]}]}'::jsonb,
                2,
                4,
                TRUE
            )
            ON CONFLICT (unit_id, version_number) DO NOTHING;
        END IF;
    END IF;

    -- Format rules seed
    IF c_ilc_id IS NOT NULL THEN
        INSERT INTO format_rules (college_id, version_number, rules_json, is_active)
        VALUES (c_ilc_id, 1, '{"font_family": "Times New Roman", "body_font_size_pt": 12.0, "heading1_font_size_pt": 14.0, "heading2_font_size_pt": 12.0, "bold_headings": true, "required_sections": ["Introduction", "Task 1", "Conclusion", "Bibliography"]}'::jsonb, TRUE)
        ON CONFLICT (college_id, version_number) DO NOTHING;
    END IF;

    IF c_ukpda_id IS NOT NULL THEN
        INSERT INTO format_rules (college_id, version_number, rules_json, is_active)
        VALUES (c_ukpda_id, 1, '{"font_family": "Times New Roman", "body_font_size_pt": 12.0, "heading1_font_size_pt": 13.0, "heading2_font_size_pt": 12.0, "bold_headings": true, "required_sections": ["Introduction", "Task 1", "Task 2", "Conclusion", "Bibliography"]}'::jsonb, TRUE)
        ON CONFLICT (college_id, version_number) DO NOTHING;
    END IF;
END $$;

-- Permissions grant to app roles
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_rw;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_ro;
