CREATE TABLE IF NOT EXISTS boards (
    board text PRIMARY KEY,    
    extra_text text,
    display_name text,
    settings jsonb  -- stuff like threads_per_board goes here
);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    board text REFERENCES boards(board) ON DELETE CASCADE ON UPDATE CASCADE,  -- add index
    thread_id int NOT NULL,  -- add index
    user_id text NOT NULL,  -- add index
    ts timestamp with time zone default (now() at time zone 'utc'),
    name text NOT NULL,
    text text,
    blob_savename text,
    blob_type text,
    blob_info jsonb,  -- filename img_size file_size
    delete_status int NOT NULL DEFAULT 0,
    mod_post int NOT NULL DEFAULT 0    
);

CREATE INDEX posts_board_idx ON posts (board);
CREATE INDEX posts_thread_idx ON posts (thread_id);
CREATE INDEX posts_user_idx ON posts (user_id);

ALTER SEQUENCE posts_id_seq RESTART WITH 100;


CREATE TABLE IF NOT EXISTS threads (
    post_id int REFERENCES posts(id) ON DELETE CASCADE ON UPDATE CASCADE,
    board text REFERENCES boards(board) ON DELETE CASCADE ON UPDATE CASCADE,   -- add index
    user_id text NOT NULL,
    ts timestamp with time zone default (now() at time zone 'utc'),
    --title text,
    post_count int NOT NULL,
    posters_count int NOT NULL,
    bump_ts timestamp with time zone NOT NULL,
    delete_status int NOT NULL DEFAULT 0,
    locked int NOT NULL DEFAULT 0,
    pinned int NOT NULL DEFAULT 0
);

CREATE INDEX threads_board_idx ON threads (board);


CREATE TABLE IF NOT EXISTS report_src (
    id SERIAL PRIMARY KEY,
    reporter_id text NOT NULL,  -- add index
    post_id int REFERENCES posts(id) ON DELETE CASCADE ON UPDATE CASCADE,  -- add index
    ts timestamp with time zone default (now() at time zone 'utc'),
    reported_id text NOT NULL,
    reason int NOT NULL,
    consumed boolean NOT NULL
);

CREATE INDEX reportsrc_idsrc_idx ON report_src (reporter_id);
CREATE INDEX reportsrc_postid_idx ON report_src (post_id);


CREATE TABLE IF NOT EXISTS ban_ptr (
    user_id text PRIMARY KEY,
    ts timestamp with time zone default (now() at time zone 'utc'),
    ban_till_ts timestamp with time zone default (now() at time zone 'utc'),
    ban_reason int NOT NULL,
    ban_post_id int
);


-- tables for moderator things

create extension if not exists "uuid-ossp";  -- this is only required for unique session_id.

CREATE TABLE IF NOT EXISTS moderator_list (
    username text PRIMARY KEY,
    password_md5 text NOT NULL UNIQUE,
    session_id uuid UNIQUE,
    expire_ts timestamp with time zone,
    actions_per_hour int NOT NULL DEFAULT 10
);

CREATE TABLE IF NOT EXISTS moderator_log (
    id SERIAL PRIMARY KEY,
    moderator_username text, -- REFERENCES moderator_list(username)
    ts timestamp with time zone default (now() at time zone 'utc'),  -- add index
    action text NOT NULL,

    info jsonb
);

CREATE INDEX moderator_log_ts_idx ON moderator_log(ts);

CREATE TABLE IF NOT EXISTS mod_login_attempt_log (
    id SERIAL PRIMARY KEY,
    user_id text NOT NULL, -- create index
    ts timestamp with time zone default (now() at time zone 'utc')
);

CREATE INDEX mod_login_attempt_user_idx  ON mod_login_attempt_log(user_id);

