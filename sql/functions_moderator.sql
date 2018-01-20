

CREATE OR REPLACE FUNCTION moderator_log_add( in_moderator_username text, in_action text, in_info text ) RETURNS void 
AS
$$
BEGIN
  INSERT INTO moderator_log (moderator_username, action, info) VALUES (
    in_moderator_username, in_action, in_info::jsonb );
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION moderator_logout ( in_session_id text,
  OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
  v_row moderator_list%ROWTYPE;
  v_session_id_input uuid;
BEGIN
  v_session_id_input = uuid(in_session_id);	
  SELECT * INTO v_row FROM moderator_list WHERE session_id=v_session_id_input;
  if FOUND THEN
    UPDATE moderator_list SET(session_id, expire_ts)=(NULL,NULL) WHERE session_id=v_session_id_input;
    out_status = 1;
    PERFORM moderator_log_add( v_row.username, 'logout', NULL );    
  else
    out_status = -1;
    out_status_text = 'error not logged in';
  end if;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION moderator_login ( in_user_id text, in_password_md5 text,
  OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
  v_row moderator_list%ROWTYPE;
  v_session_id uuid;

  v_login_attempts int := 0;
BEGIN
  SELECT COUNT(*) INTO v_login_attempts FROM mod_login_attempt_log WHERE user_id = in_user_id AND ts > now() - INTERVAL '10m';

  if v_login_attempts >= 4 THEN
    out_status = -1;
    out_status_text = 'you failed too many attempts at logging in. Try again after some time.';
    RETURN;
  end if;

  SELECT * INTO v_row FROM moderator_list WHERE password_md5=in_password_md5;
  if FOUND THEN
    -- if session is set and not expired, return it by extending expiry by +10 hours
    if v_row.expire_ts - now() > interval'1s' AND v_row.session_id IS NOT NULL THEN
      --UPDATE moderator_list SET (expiry) VALUES (v_row.expire_ts + '5m') WHERE password_md5=in_password_md5;
      out_status = 1;
      out_status_text = v_row.session_id;
    else
      v_session_id = uuid_generate_v4();
      UPDATE moderator_list SET (session_id, expire_ts)=(v_session_id, now() + '10 hours' ) WHERE password_md5=in_password_md5;
      out_status = 1;
      out_status_text = concat(v_session_id, '');
    end if;
    PERFORM moderator_log_add(v_row.username, 'login', NULL);
  else  -- incorrect pass
      INSERT INTO mod_login_attempt_log (user_id) VALUES (in_user_id);
      out_status = -1;
      out_status_text = 'can''t login with wrong password';
  end if;
END;
$$ LANGUAGE plpgsql;
  

CREATE OR REPLACE FUNCTION moderator_check_login_status_and_get_username( in_session_id text, OUT out_status integer,
  OUT out_status_text text )
AS
$$
DECLARE
  v_row moderator_list%ROWTYPE;
  v_session_id_input uuid;
BEGIN
  v_session_id_input = uuid(in_session_id);
  SELECT * INTO v_row FROM moderator_list WHERE session_id=v_session_id_input;
  if FOUND THEN
    if v_row.expire_ts - now() > interval'1s' THEN
      out_status = 1;
      out_status_text = v_row.username;
    else
      out_status = -1;
      out_status_text = 'expired';
    end if;
  else
    out_status = -1;
    out_status_text = 'no session_id';
  end if;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION moderator_delete_and_ban_post(in_session_id text, in_post_id integer, in_delete_reason text,
  in_ban_duration text, in_delete_subsequent integer, in_unbump integer, in_delete_permanently integer, in_delete_reason_text text,
  OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
  v_actions_per_hour_check integer;

  v_mod_list_row moderator_list%ROWTYPE;
  v_posts_row posts%ROWTYPE;
  v_threads_row threads%ROWTYPE;

  v_undelete_thread_id integer;

  v_delete_status_to_set integer := 3;  -- 3 is for deleted by moderator without permanency, 10 is with permanency
  v_unbump_ts timestamp with time zone;

  v_ban_reason_to_set int := 2; -- default is spam
  v_ban_duration interval;

  v_info text := '';
  v_info_fmt text := '{"post_id" : %s, "thread_id" : %s, "board" : "%s", "delete_reason" : "%s", 
                      "ban_duration" : "%s", "delete_subsequent" : %s, "unbump" : %s, "delete_permanently" : %s,
                      "delete_reason_text" : "%s" }';


BEGIN  
  -- check if actions per hour is ok
  SELECT * INTO v_mod_list_row FROM moderator_list WHERE session_id=uuid(in_session_id);

  SELECT * INTO v_actions_per_hour_check FROM moderator_check_actions_per_hour(v_mod_list_row);
  if v_actions_per_hour_check = -1 THEN
    out_status = -1;
    out_status_text = 'actions per hour exceeded';
    RETURN;
  end if;

  if in_delete_permanently = 1 THEN
    v_delete_status_to_set = 10; -- 10 for deleted by mod with permanency
  end if;

  -- all good. we would try to ban the post now.
  -- get the post. get its thread.
  SELECT * INTO v_posts_row FROM posts WHERE id = in_post_id;
  if FOUND THEN
    SELECT * INTO v_threads_row FROM threads WHERE post_id=v_posts_row.thread_id;
      
    if v_posts_row.delete_status = 0 AND v_threads_row.delete_status = 0 THEN -- if not deleted already
      if v_posts_row.id = v_posts_row.thread_id THEN -- if it is a thread
        UPDATE threads SET delete_status=v_delete_status_to_set WHERE post_id = in_post_id;  -- 3 delete_status is for deleted by moderator. 

        -- try to undelete the last thread which was pruned if it exists
        -- careful, you are getting board from the deleted post's board
        SELECT post_id INTO v_undelete_thread_id FROM threads WHERE board=v_threads_row.board AND delete_status=1 ORDER BY bump_ts DESC LIMIT 1;
        if FOUND THEN
          UPDATE threads SET delete_status=0 WHERE post_id = v_undelete_thread_id;
          UPDATE posts SET delete_status=0 WHERE id = v_undelete_thread_id;
        end if;      

      else -- when post is not OP
        if in_unbump = 1 THEN
        --unbump
        SELECT ts INTO v_unbump_ts FROM posts WHERE id < in_post_id AND thread_id=v_posts_row.thread_id ORDER BY ts DESC LIMIT 1;
          if v_threads_row.bump_ts > v_unbump_ts THEN
            UPDATE threads SET bump_ts=v_unbump_ts WHERE post_id=v_posts_row.thread_id;
          end if;
        end if;
      end if;

      UPDATE posts SET delete_status=v_delete_status_to_set WHERE id = in_post_id;

      if in_delete_subsequent = 1 THEN  -- delete subsequent posts by the user_id
        UPDATE posts SET delete_status=v_delete_status_to_set WHERE thread_id=v_posts_row.thread_id AND id > in_post_id AND user_id=v_posts_row.user_id;
      end if;

      PERFORM recalculate_poster_counts(v_posts_row.thread_id);

      
      -- banning user here
      v_ban_duration = in_ban_duration::interval;

      if in_delete_reason = 'spam' THEN
        v_ban_reason_to_set = 2;
      elsif in_delete_reason = 'illegal' THEN
        v_ban_reason_to_set = 3;
      else
        out_status = -1;
        out_status_text = 'inappropriate delete reason';
        RETURN;
      end if;


      if  v_ban_duration > interval'1s' THEN
        PERFORM ban_user(v_posts_row.user_id, v_ban_reason_to_set, v_ban_duration, v_posts_row.id);
      end if;

      --prepare v_info here
      v_info = format(v_info_fmt, v_posts_row.id, v_threads_row.post_id, v_threads_row.board, 
               in_delete_reason, in_ban_duration, in_delete_subsequent, in_unbump, in_delete_permanently, in_delete_reason_text );

      -- add moderator log
      PERFORM moderator_log_add(v_mod_list_row.username, 'delete_post', v_info );

      out_status = 1;
        
    else
      out_status = -1;
      out_status_text = 'post has been deleted already.';
    end if;
  else
    out_status = -1;
    out_status_text = 'post does not exist';
  end if;  
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION moderator_undelete_post(in_session_id text, in_post_id integer,
  in_undelete_subsequent integer, in_unban integer,
  OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
  v_actions_per_hour_check integer;

  v_mod_list_row moderator_list%ROWTYPE;
  v_posts_row posts%ROWTYPE;
  v_threads_row threads%ROWTYPE;

  v_info text := '';
  v_info_fmt text := '{"post_id" : %s, "thread_id" : %s, "board" : "%s", "undelete_subsequent" : %s, "unban" : %s }';


BEGIN  
  -- check if actions per hour is ok
  SELECT * INTO v_mod_list_row FROM moderator_list WHERE session_id=uuid(in_session_id);

  SELECT * INTO v_actions_per_hour_check FROM moderator_check_actions_per_hour(v_mod_list_row);
  if v_actions_per_hour_check = -1 THEN
    out_status = -1;
    out_status_text = 'actions per hour exceeded';
    RETURN;
  end if;

  -- get the post. get its thread.
  SELECT * INTO v_posts_row FROM posts WHERE id = in_post_id;
  if FOUND THEN
    SELECT * INTO v_threads_row FROM threads WHERE post_id=v_posts_row.thread_id;

    if v_posts_row.delete_status = 0 AND v_threads_row.delete_status = 0 THEN
      out_status = -1;
      out_status_text = 'post is already undeleted';
      RETURN;
    end if;

    if v_posts_row.id = v_posts_row.thread_id THEN -- if it is a thread
      UPDATE threads SET delete_status=0 WHERE post_id = in_post_id;
    end if;
    UPDATE posts SET delete_status=0 WHERE id = in_post_id;

    if in_undelete_subsequent = 1 THEN
      UPDATE posts SET delete_status=0 WHERE thread_id=v_posts_row.thread_id AND id > in_post_id AND user_id=v_posts_row.user_id;
    end if;

    PERFORM recalculate_poster_counts(v_posts_row.thread_id);

    if in_unban = 1 THEN
      PERFORM unban_user(v_posts_row.user_id);
    end if;

    --prepare v_info here
    v_info = format(v_info_fmt, v_posts_row.id, v_threads_row.post_id, v_threads_row.board, in_undelete_subsequent, in_unban );    

    PERFORM moderator_log_add(v_mod_list_row.username, 'undelete_post', v_info );
    out_status = 1;
      
  else
    out_status = -1;
    out_status_text = 'post does not exist';
  end if;  
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION recalculate_poster_counts(in_thread_id integer) RETURNS void 
AS
$$
DECLARE
  v_post_count integer := 0;
  v_posters_count integer := 0;

BEGIN
  SELECT COUNT(*) INTO v_post_count FROM posts WHERE thread_id=in_thread_id AND delete_status != 10;
  
  SELECT COUNT(*) INTO v_posters_count FROM ( SELECT DISTINCT user_id FROM posts WHERE thread_id=in_thread_id AND delete_status != 10 ) AS temp;

  UPDATE threads SET (post_count, posters_count)=(v_post_count, v_posters_count) WHERE post_id=in_thread_id;

END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION moderator_update_thread(in_session_id text, in_post_id int, 
  in_lock int, in_pin int, 
  OUT out_status int, OUT out_status_text text)
AS
$$
DECLARE
  v_actions_per_hour_check integer;

  v_mod_list_row moderator_list%ROWTYPE;
  v_posts_row posts%ROWTYPE;
  v_threads_row threads%ROWTYPE;

  v_bump_ts_to_set timestamp with time zone;

  v_info text := '';
  v_info_innards text := '';  -- used for lock and pin
  v_info_fmt text := '{"post_id" : %s, "thread_id" : %s, "board" : "%s" %s }';

BEGIN
  -- check if actions per hour is ok
  SELECT * INTO v_mod_list_row FROM moderator_list WHERE session_id=uuid(in_session_id);

  SELECT * INTO v_actions_per_hour_check FROM moderator_check_actions_per_hour(v_mod_list_row);
  if v_actions_per_hour_check = -1 THEN
    out_status = -1;
    out_status_text = 'actions per hour exceeded';
    RETURN;
  end if;

  SELECT * INTO v_posts_row FROM posts WHERE id = in_post_id;
  if NOT FOUND THEN
    out_status = -1;
    out_status_text = 'post does not exist';
    RETURN;
  end if;
  
  if v_posts_row.id != v_posts_row.thread_id THEN  -- if post is not a thread
    out_status = -1;
    out_status_text = 'can''t lock or pin a post which is not a thread';
    RETURN;
  end if;

  SELECT * INTO v_threads_row FROM threads WHERE post_id=v_posts_row.thread_id;

  if v_threads_row.locked = in_lock AND v_threads_row.pinned = in_pin THEN
    out_status = -1;
    out_status_text = 'nothing to update.';
    RETURN;
  end if;

  v_bump_ts_to_set = v_threads_row.bump_ts;

  if in_pin = 0 AND v_threads_row.pinned = 1 THEN
    v_bump_ts_to_set = now();
  elsif in_pin = 1 AND v_threads_row.pinned = 0 THEN
    v_bump_ts_to_set = timestamp'2030-01-01' + ( timestamp'2030-01-01' - now() );  -- good enough till the year 2030
  else
    v_bump_ts_to_set = v_threads_row.bump_ts;
  end if;

  --setting v_info_innards here
  if in_pin != v_threads_row.pinned THEN
    v_info_innards = concat( v_info_innards, format(',"pin" : %s ', in_pin ) );
  end if;

  if in_lock != v_threads_row.locked THEN
    v_info_innards = concat( v_info_innards, format(',"lock" : %s ', in_lock ) );
  end if;

  -- all good, updating now
  UPDATE threads SET (bump_ts,locked,pinned)=(v_bump_ts_to_set, in_lock, in_pin)  WHERE post_id = in_post_id;

  --prepare v_info here

  v_info = format(v_info_fmt, v_posts_row.id, v_threads_row.post_id, v_threads_row.board, v_info_innards );

  -- add moderator log
  PERFORM moderator_log_add(v_mod_list_row.username, 'update_thread', v_info );

  out_status = 1;

END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION moderator_move_thread( in_session_id text, in_thread_id int, in_board_dst text,
  OUT out_status int, OUT out_status_text text)
AS
$$
DECLARE
  v_actions_per_hour_check integer;

  v_mod_list_row moderator_list%ROWTYPE;
  v_posts_row posts%ROWTYPE;
  v_threads_row threads%ROWTYPE;

  v_boards_row boards%ROWTYPE;

  v_info text := '';
  v_info_innards text := '';  -- used for lock and pin
  v_info_fmt text := '{"thread_id" : %s, "board_src" : "%s", "board_dst" : "%s" }';

BEGIN
  -- check if actions per hour is ok
  SELECT * INTO v_mod_list_row FROM moderator_list WHERE session_id=uuid(in_session_id);

  SELECT * INTO v_actions_per_hour_check FROM moderator_check_actions_per_hour(v_mod_list_row);
  if v_actions_per_hour_check = -1 THEN
    out_status = -1;
    out_status_text = 'actions per hour exceeded';
    RETURN;
  end if;

  SELECT * INTO v_boards_row FROM boards WHERE board = in_board_dst;
  if NOT FOUND THEN
    out_status = -1;
    out_status_text = 'board dst does not exist';
    RETURN;
  end if;

  SELECT * INTO v_posts_row FROM posts WHERE id = in_thread_id;
  if NOT FOUND THEN
    out_status = -1;
    out_status_text = 'post does not exist';
    RETURN;
  end if;
  
  if v_posts_row.id != v_posts_row.thread_id THEN  -- if post is not a thread
    out_status = -1;
    out_status_text = 'can''t move a post which is not a thread';
    RETURN;
  end if;

  SELECT * INTO v_threads_row FROM threads WHERE post_id=v_posts_row.thread_id;

  if v_threads_row.board = in_board_dst THEN
    out_status = -1;
    out_status_text = 'thread is already in the board you wan''t to move it to.';
    RETURN;
  end if;

  -- all good, perform move here
  v_info = format(v_info_fmt, in_thread_id, v_threads_row.board, in_board_dst );

  UPDATE threads SET board = in_board_dst WHERE post_id = in_thread_id;
  UPDATE posts SET board = in_board_dst WHERE thread_id = in_thread_id;

  -- add moderator log
  PERFORM moderator_log_add(v_mod_list_row.username, 'move_thread', v_info );

  out_status = 1;

END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION moderator_check_actions_per_hour(in_mod_list_row moderator_list,
  OUT out_status integer)
AS
$$
DECLARE
  v_action_count integer;
BEGIN
  SELECT COUNT(*) INTO v_action_count FROM moderator_log WHERE ts > now() - interval'1 hour' AND moderator_username = in_mod_list_row.username 
  AND ( action = 'delete_post' OR action = 'undelete_post' OR action = 'start_post' OR action='update_thread');
  if v_action_count >= in_mod_list_row.actions_per_hour THEN    
    out_status = -1;
    return;
  end if;
  out_status = 1;  
END;
$$ LANGUAGE plpgsql;

-- this function checks if password_md5 matches and actions_per_hour isn't exceeded
CREATE OR REPLACE FUNCTION moderator_check_validity( in_password_md5 text,
  OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
  v_actions_per_hour_check int;
  v_row moderator_list%ROWTYPE;
 
BEGIN 

  SELECT * INTO v_row FROM moderator_list WHERE password_md5=in_password_md5 LIMIT 1;
  if FOUND THEN
    SELECT * INTO v_actions_per_hour_check FROM moderator_check_actions_per_hour(v_row);
    if v_actions_per_hour_check = 1 THEN
      out_status = 1;
      out_status_text = v_row.username;
    else 
      out_status = -1;
      out_status_text = 'actions per hour exceeded';
    end if;

  else  -- incorrect pass
      out_status = -1;
      out_status_text = 'password incorrect';
  end if;
END;
$$ LANGUAGE plpgsql;



