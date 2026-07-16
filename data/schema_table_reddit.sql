-- Reddit crawler schema
-- Mục tiêu:
--   - Theo dõi bài viết mới được đăng trong vòng 24 giờ.
--   - Hỗ trợ source theo subreddit, keyword, user hoặc latest.
--   - Xếp hạng độ thảo luận theo comments_count và score.
--   - Có thể lưu comment khi source bật include_comments.

PRAGMA foreign_keys = ON;

CREATE TABLE sources (
    id INTEGER PRIMARY KEY,

    source_type VARCHAR(20) NOT NULL
        CHECK (source_type IN ('subreddit', 'keyword', 'user', 'latest')),

    -- subreddit: vozforums
    -- keyword:   memory leak
    -- user:      spez
    -- latest:    all
    identifier VARCHAR(300) NOT NULL,

    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_accessible BOOLEAN NOT NULL DEFAULT 1,

    -- 1: lấy và lưu comment; 0: chỉ dùng comments_count từ post_metrics.
    include_comments BOOLEAN NOT NULL DEFAULT 0,

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER,
    schedule_override_minutes INTEGER,

    UNIQUE (source_type, identifier)
);

CREATE INDEX idx_sources_next_scrape
    ON sources (is_active, is_accessible, next_scrape);


CREATE TABLE posts (
    id INTEGER PRIMARY KEY,

    reddit_post_id VARCHAR(20) NOT NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    subreddit_name VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    permalink TEXT NOT NULL,
    external_url TEXT,

    author_name VARCHAR(100),
    author_fullname VARCHAR(30),

    post_type VARCHAR(20) NOT NULL DEFAULT 'link'
        CHECK (post_type IN ('text', 'link', 'image', 'video', 'gallery', 'poll', 'other')),

    selftext TEXT,
    link_flair_text VARCHAR(200),

    is_self BOOLEAN NOT NULL DEFAULT 0,
    is_nsfw BOOLEAN NOT NULL DEFAULT 0,
    is_stickied BOOLEAN NOT NULL DEFAULT 0,
    is_locked BOOLEAN NOT NULL DEFAULT 0,

    post_created_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN NOT NULL DEFAULT 1,
    tracking_until DATETIME,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,
    metric_tier VARCHAR(20) NOT NULL DEFAULT 'very_low'
        CHECK (metric_tier IN (
            'hot', 'high', 'medium', 'low', 'very_low'
        )),

    UNIQUE (reddit_post_id),
    UNIQUE (permalink)
);

CREATE INDEX idx_posts_created
    ON posts (post_created_at);
CREATE INDEX idx_posts_metric_due
    ON posts (is_tracked, next_metric_update);
CREATE INDEX idx_posts_source
    ON posts (source_id);
CREATE INDEX idx_posts_subreddit
    ON posts (subreddit_name, post_created_at);


-- Một post có thể được tìm thấy từ nhiều source, ví dụ subreddit + keyword.
CREATE TABLE source_posts (
    source_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,

    first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (source_id, post_id),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (post_id)
        REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX idx_source_posts_post
    ON source_posts (post_id);


CREATE TABLE analytics_cache (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL,
    date DATE NOT NULL,

    total_posts INTEGER NOT NULL DEFAULT 0,
    total_comments INTEGER NOT NULL DEFAULT 0,
    total_score INTEGER NOT NULL DEFAULT 0,
    avg_comments_per_post FLOAT NOT NULL DEFAULT 0,
    avg_score_per_post FLOAT NOT NULL DEFAULT 0,
    top_post_id INTEGER,
    growth_rate FLOAT NOT NULL DEFAULT 0,
    cached_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (source_id, date),

    FOREIGN KEY (source_id)
        REFERENCES sources(id) ON DELETE CASCADE,
    FOREIGN KEY (top_post_id)
        REFERENCES posts(id) ON DELETE SET NULL
);

CREATE INDEX idx_analytics_cache_source_date
    ON analytics_cache (source_id, date);


CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scrape_posts'
        CHECK (job_type IN (
            'scrape_posts',
            'scrape_new_posts',
            'update_metrics',
            'scrape_comments'
        )),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    posts_found INTEGER NOT NULL DEFAULT 0,
    posts_new INTEGER NOT NULL DEFAULT 0,
    posts_updated INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_jobs_source_time
    ON pipeline_jobs (source_id, started_at);
CREATE INDEX idx_pipeline_jobs_status
    ON pipeline_jobs (status, created_at);


-- Lưu lịch sử metric để theo dõi tốc độ tăng thảo luận.
CREATE TABLE post_metrics (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,

    score INTEGER NOT NULL DEFAULT 0,
    comments_count INTEGER NOT NULL DEFAULT 0,

    recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    FOREIGN KEY (post_id)
        REFERENCES posts(id) ON DELETE CASCADE
);

CREATE INDEX idx_post_metrics_post_time
    ON post_metrics (post_id, recorded_at);
CREATE INDEX idx_post_metrics_recorded_at
    ON post_metrics (recorded_at);
CREATE INDEX idx_post_metrics_hot
    ON post_metrics (comments_count DESC, score DESC);


-- Chỉ ghi bảng này khi source tương ứng có include_comments = 1.
CREATE TABLE comments (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL,

    reddit_comment_id VARCHAR(20) NOT NULL,
    parent_reddit_id VARCHAR(30),

    author_name VARCHAR(100),
    author_fullname VARCHAR(30),

    body TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    depth INTEGER NOT NULL DEFAULT 0,

    is_submitter BOOLEAN NOT NULL DEFAULT 0,
    is_stickied BOOLEAN NOT NULL DEFAULT 0,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,

    comment_created_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (post_id)
        REFERENCES posts(id) ON DELETE CASCADE,

    UNIQUE (reddit_comment_id)
);

CREATE INDEX idx_comments_post_time
    ON comments (post_id, comment_created_at);
CREATE INDEX idx_comments_parent
    ON comments (parent_reddit_id);


CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,
    error_type VARCHAR(100),
    error_details TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_logs_job
    ON pipeline_logs (job_id, created_at);
CREATE INDEX idx_pipeline_logs_source
    ON pipeline_logs (source_id, created_at);
