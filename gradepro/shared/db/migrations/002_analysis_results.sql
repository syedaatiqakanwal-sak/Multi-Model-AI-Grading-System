-- Additive integrity-analysis tables (do not alter existing criteria/model versioning).
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
