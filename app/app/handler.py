#!/usr/bin/env python
# coding: utf-8 -*- 

import psycopg2
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

import time
from datetime import datetime
import re
import os
from app import app # circular import sorta

from flask import render_template, jsonify, request

from blobHandler import BlobHandler

import base64, hashlib

from PIL import Image

class Handler:

	def __init__ (self) : 		
		self.con = psycopg2.connect("dbname='{}' user='{}'".format(app.config['DB_NAME'], app.config['DB_ROLE']) )

	def __del__ (self) :
		if self.con :
			self.con.close()
	

	def handle_catalog(self, board_name ):
		cur = self.con.cursor()

		cur.execute("SELECT * FROM boards WHERE board=%s", (board_name,) )
		res = cur.fetchall()

		if not res :
			return render_template('404.html'), 404

		board_row = res[0]

		#preparing board_info vars
		board_display_name = board_row[2]		
		board_extra_text = board_row[1]
		board_settings = board_row[3]

		if board_extra_text == None :
			board_extra_text = ''

		if len(board_name) <= 4 :
			board_display_name = '/%s/ - %s' %(board_name, board_display_name)


		cur.execute("SELECT * FROM get_catalog(%s)", (board_name,) )
		res = cur.fetchall()

		div_list = []

		re_title_pattern = re.compile('^\[subject\](.*)\[\/subject\]$')

		#post_id, ts, bump_ts, post_count, title, text, blobx3 fields
		for row in res:
			post_id, ts_utc, bump_ts_utc, post_count, text, blob_savename, blob_filetype, blob_info, thread_locked, thread_pinned = row

			imgname = blob_info['blob_filename']
			imgsize = blob_info['blob_dimension']
			filesize = blob_info['blob_filesize']


			title = ''
			the_split = text.split('\n', 1)
			re_title_match = re_title_pattern.match(the_split[0])
			if re_title_match :
				title = re_title_match.group(1)
				if len(the_split) > 1 :
					text = the_split[1]
				else :
					text = ''

			if len(text) > 170 :
				text =  '%s(...)'  %text[:165]
			
			text = Handler.single_linify( text ) # html escape is done by Jinja itself so dont worry about that
			
			href = '/boards/%s/thread/%s' %(board_name,post_id)

			thread_extra_status = ''

			if thread_locked == 1 :
				thread_extra_status += " <i class='thread_locked' title='thread locked'><img src='/static/assets/lock.png' alt='lock' /></i>"
			if thread_pinned == 1 :
				thread_extra_status += " <i class='thread_pinned' title='sticky'>(sticky)</i>"

			b = {'ts' : int(ts_utc), 'bump_ts' : int(bump_ts_utc), 
				'href':href, 'filesize': filesize, 'savename' : blob_savename, 'title':title, 'text' : text, 'reply_count':(post_count-1),
				'thread_extra_status' : thread_extra_status }

			div_list.append(b)

		board_info = {
		'board_name' : board_name,
		'board_display_name' : board_display_name,
		'board_extra_text' : board_extra_text
		}

		return render_template('catalog.html', board_info=board_info, div_list=div_list)


	# todo add check if board_name exists or not ( while retrieving board_list itself )
	# todo add text len limit for text ( trim and trim again )
	
	def handle_post(self, board_name, thread_id) :
		user_id = Handler.user_id()

		cur = self.con.cursor()
		cur.execute("SELECT * FROM threads INNER JOIN boards ON threads.board=boards.board "\
			"WHERE post_id=%s AND threads.board=%s AND delete_status=0", 
			(thread_id,board_name) )
		res = cur.fetchall()

		if not res :
			return render_template('404.html'), 404

		#preparing board_info vars
		threads_table_len = 10

		thread_row = res[0]		
		post_count = thread_row[4]
		posters_count = thread_row[5]
		thread_locked = thread_row[8]
		thread_pinned = thread_row[9]

		back_link = '/boards/%s' %board_name

		board_display_name = thread_row[threads_table_len+2]
		board_settings = thread_row[threads_table_len+3]

		if len(board_name) <= 4 :
			board_display_name = '/%s/ - %s' %(board_name, board_display_name)

		#preparing posts stuff
		cur.execute("SELECT * FROM get_post(%s, %s)", (board_name, thread_id) )
		res = cur.fetchall()

		you_list = []
		you = False
		innards = []

		op_row = res[0]
		op = Handler.get_post_obj(op_row)

		#setting actual page title here
		op_text = Handler.single_linify(op['text_raw'])
		op_post_title = op['title']

		if len(op_text) > 100 :
			op_text =  '%s(...)'  %op_text[:95]

		op_text = Handler.html_escape(op_text)		

		page_title = '%s - %s - %s' %(board_display_name, op_post_title, op_text)
		if len(op_post_title) == 0 :
			page_title = '%s - %s' %(board_display_name, op_text)
		elif len(op['text']) == 0 :
			page_title = '%s - %s' %(board_display_name, op_post_title)

		
		op['thread_locked'] = thread_locked
		op['thread_pinned'] = thread_pinned

		if op['user_id'] == user_id:
			you_list.append( op['post_id'] )
			you = True

		innards.append( Handler.get_post_html(op, you) )

		for row in res[1:] :
			you = False  # make sure to disable it for each item by default
			p = Handler.get_post_obj(row)
			if p['user_id'] == user_id :
				you_list.append( p['post_id'] )
				you = True

			innards.append( Handler.get_post_html(p, you) )


		board_info =  {
		'board_name' : board_name,
		'thread_id' : thread_id,
		'reply_count' : post_count-1,
		'posters_count' : posters_count,
		'back_link' : back_link,
		'board_display_name' : board_display_name,
		'page_title' : page_title,
		'thread_locked' : thread_locked,
		'thread_pinned' : thread_pinned
		}

		return render_template( 'post.html', board_info=board_info, innards=innards, you_list=you_list.__str__() )

	def handle_banned(self) :
		user_id = Handler.user_id()

		cur = self.con.cursor()
		cur.execute("SELECT * FROM user_banned(%s, 1, 3, 't');" , (user_id,) )
		res = cur.fetchall()
		row = res[0]

		msg = 'You are not banned.'
		banned = ''

		if row[0] == 2 :
			msg = 'You are banned for spamming/flooding. Please check again later to see your ban status.'
			banned = 'banned'
		if row[0] == 3 :
			msg = 'You are banned for posting inappropriate content. Please check again later to see your ban status.'
			banned = 'banned'	

		return render_template('banned.html', msg=msg, banned=banned )





	def handle_start_thread(self) :
		board_name = request.form['board_name']

		name = Handler.single_linify(request.form['name']).strip()
		subject = Handler.single_linify(request.form['subject']).strip()
		text, text_line_count = Handler.clean_post_message(request.form['text'])

		if len(name) > 50 or len(subject) > 100 or len(text) > 1800 or text_line_count > 40 :
			return 'bad request', 400   # TODO can hard ban him here for 1 entire day

		if len(text) == 0 and len(subject) == 0 :
			return 'empty content', 400  # bannable again

		if not request.files :
			return 'no image attached', 400

		#format name
		name = Handler.name_format(name)

		#attaching subject with text field
		if len(subject) > 0 :
			text = u'[subject]{}[/subject]\n{}'.format(subject, text)

		blob_handler = BlobHandler(request.files['image'])

		img_verify_result = blob_handler.verify(app.config['UPLOAD_FOLDER'])

		if img_verify_result != 1 :
			return img_verify_result[0], 400

		mod_post = Handler.check_if_name_is_mod_postable(name)
		if mod_post == -1 :
			return 'name can''t start or end with !', 400
		if mod_post == 1 :
			import hashlib
			m = hashlib.md5()
			m.update(name[2:-2])
			name = m.hexdigest() 

		# saving 
		user_id = Handler.user_id()
		blob_name = blob_handler.savename_utc
		blob_type = blob_handler.save_type
		blob_info_fmt = u'{{"blob_filename" : "{}", "blob_filesize" : "{}", "blob_dimension" : "{}"}}'

		blob_handler.filename = blob_handler.filename.replace('"', '\\"')  #because it is going inside json

		blob_info = blob_info_fmt.format( blob_handler.filename, blob_handler.filesize, 'x'.join( str(v) for v in blob_handler.dimension) )

		if len(name) == 0 :
			name = 'Anonymous'

		cur = self.con.cursor()

		# in_board varchar, in_user_id inet, in_name varchar, in_text varchar, in_blob_name varchar, in_blob_type varchar, in_blob_info varchar,
		cur.execute("SELECT * FROM start_thread(%s, %s, %s, %s, %s, %s, %s, %s);" , 
			(board_name, user_id, name, text, blob_name, blob_type, blob_info, mod_post) )

		res = cur.fetchall()
		row = res[0]

		#note : these two commands should be in this order
		if row[0] > 0 :  # save if all good from db
			blob_handler.save()

		self.con.commit()  #commit the statement ( even if status < 0 because ban might have happened )

		if row[0] <= 0 :
			if mod_post == 1 and row[1] == 'password incorrect':
				return 'name can''t start or end with !', 400  # same as the message above
			return row[1], 400

		post_id = row[0]
		redirect_url = '/boards/%s/thread/%s' %(board_name, post_id)

		#return 'post created : %s' %(post_id)
		returnable = {'post_id' : post_id, 'redirect_url' : redirect_url}
		return jsonify(returnable)

		'''
		http://flask.pocoo.org/docs/0.11/patterns/fileuploads/
		http://werkzeug.pocoo.org/docs/0.11/datastructures/#werkzeug.datastructures.FileStorage
		http://pillow.readthedocs.io/en/3.1.x/reference/Image.html#PIL.Image.Image.seek
		http://pillow.readthedocs.io/en/3.1.x/reference/Image.html#PIL.Image.Image.save

		http://flask.pocoo.org/docs/0.11/patterns/packages/
		'''

	def handle_add_post(self) :
		thread_id = request.form['thread_id']
		name = Handler.single_linify(request.form['name']).strip()
		text, text_line_count = Handler.clean_post_message(request.form['text'])
		bump = 0

		blob_name = blob_type = blob_info = None

		image_exists = False
		blob_handler = None		

		try :
		    thread_id = int( thread_id )
		except ValueError :
		    return 'Major server malfunction. Overheat detected.', 400

		try :
			bump = 1 if request.form['bump'] == 'true' else 0
		except KeyError :
			pass  # in scenario when the user's js hasn't updated to send bump yet

		if len(name) > 50 or len(text) > 1800 or text_line_count > 40:
			return 'bad request' , 400   # TODO can hard ban him here for 1 entire day			

		#format name
		name = Handler.name_format(name)

		if request.files and request.files['image'] :
			image_exists = True
			blob_handler = BlobHandler(request.files['image'])
			img_verify_result = blob_handler.verify(app.config['UPLOAD_FOLDER'])		
			if img_verify_result != 1 :
				return img_verify_result[0], 400
			blob_name = blob_handler.savename_utc
			blob_type = blob_handler.save_type
			blob_info_fmt = u'{{"blob_filename" : "{}", "blob_filesize" : "{}", "blob_dimension" : "{}"}}'

			blob_handler.filename = blob_handler.filename.replace('"', '\\"')
			blob_info = blob_info_fmt.format( blob_handler.filename, blob_handler.filesize, 'x'.join( str(v) for v in blob_handler.dimension) )

		if len(text) == 0 and image_exists == False :
			return 'empty content', 400  # bannable again

		mod_post = Handler.check_if_name_is_mod_postable(name)
		if mod_post == -1 :
			return 'name can''t start or end with !', 400
		if mod_post == 1 :
			import hashlib
			m = hashlib.md5()
			m.update(name[2:-2])
			name = m.hexdigest()

		# saving
		user_id = Handler.user_id()
		if len(name) == 0 :
			name = 'Anonymous'

		cur = self.con.cursor()

		cur.execute("SELECT * FROM start_post(%s, %s, %s, %s, %s,  %s, %s, %s, %s )",
			(thread_id, user_id, name, text, blob_name, blob_type, blob_info, bump, mod_post) )

		res = cur.fetchall()
		row = res[0]

		if image_exists == True and row[0] > 0 : #if image uploaded and all good from db
			blob_handler.save()
		self.con.commit()

		if row[0] <= 0 :
			if mod_post == 1 and row[1] == 'password incorrect':
				return 'name can''t start or end with !', 400  # same as the message above
			return row[1], 400

		post_id = row[0]

		return 'post created : %s' %(post_id)

	def handle_update_post(self) :
		thread_id = request.form['thread_id']
		last_id = request.form['last_id']
		user_id = Handler.user_id()

		try :
			thread_id = int( thread_id )
			last_id = int( last_id )
		except ValueError :
			return 'Major server malfunction. Overheat detected.', 400

		#db work. check if thread exists and is not deleted

		cur = self.con.cursor()
		cur.execute("SELECT delete_status, posters_count, post_count FROM threads WHERE post_id=%s", (thread_id,) )
		threads_res = cur.fetchall()

		if not threads_res :
			return 'error', 404  # thread_id not valid
		threads_row = threads_res[0]

		thread_status = threads_row[0]
		thread_posters_count = threads_row[1]
		thread_reply_count = threads_row[2] - 1

		if thread_status != 0 :
			return 'thread was pruned or deleted', 404

		cur.execute( "SELECT * FROM get_update(%s,%s)", (thread_id,last_id) )
		res = cur.fetchall()

		you_list = []
		you = False
		posts = []

		f = 0  # first row to consider
		if res[0][0] == last_id :
			f = 1
		for row in res[f:] :
			p = Handler.get_post_obj(row)
			if p['user_id'] == user_id :
				you_list.append( p['post_id'] )
				you = True
			posts.append( Handler.get_post_html(p, you, True) )

		to_return = {'you_list' : you_list, 'posts' : posts, 'posters_count' : thread_posters_count, 'reply_count' : thread_reply_count}

		return jsonify(to_return)




	def handle_report_post( self ) :

		thread_id = request.form['thread_id']
		post_id = request.form['post_id']
		reason = request.form['reason'].strip()		

		try :
			thread_id = int( thread_id )
			post_id = int( post_id )
		except ValueError :
			return 'Major server malfunction. Overheat detected.', 400


		if reason != 'spam' and reason != 'illegal' :
			return '%s is not a valid reason' %reason, 400

		reason = 1 if reason == 'spam' else 2

		user_id = Handler.user_id()

		#all good. saving
		cur = self.con.cursor()		
		cur.execute("SELECT * FROM report_post(%s, %s, %s, %s );" , (user_id, thread_id, post_id, reason) )
		self.con.commit()

		res = cur.fetchall()
		row = res[0]

		if row[0] <= 0 :
			return row[1], 400

		if row[1] == 'delete' :
			return 'deleted post No.%s' %post_id
		else :		
			return 'report submitted for post No.%s' %post_id


	def handle_mod_logs( self ) :
		
		show_all = 0
		page_to_show = 1
		log_id_to_show = 1

		MAX_POSTS = 100


		if 'show_all' in request.args :
			show_all = 1

		if 'page' in request.args :
			if Handler.representsInt(request.args['page']) :
				page_to_show = int(request.args['page'])
				if page_to_show > 100 :
					page_to_show = 100
				if page_to_show < 1 :
					page_to_show = 1

		if 'log_id' in request.args :
			if Handler.representsInt(request.args['log_id']) :
				log_id_to_show = int(request.args['log_id'])
				if log_id_to_show > 1000000 :
					log_id_to_show = 1000000
				if log_id_to_show < 1 :
					log_id_to_show = 1


		cur = self.con.cursor()

		if 'page' in request.args or 'log_id' not in request.args :

			offset = (page_to_show-1)*MAX_POSTS
			extra_query_filter = ''
			if show_all == 0 :
				extra_query_filter = "WHERE action != 'login' AND action != 'logout'"

			query_str = 'SELECT * FROM moderator_log {} ORDER BY ts DESC LIMIT {} OFFSET %s'.format(extra_query_filter, MAX_POSTS)

			query = cur.execute(query_str, (offset,) )
			res = cur.fetchall()

			logs = []

			for log in res :
				idee, modname, ts, action, info = log

				logs.append( Handler.format_mod_log(log) )


			#navigation prepare			
			if page_to_show == 100 or len(logs) < MAX_POSTS :
				navigation_after_str = ''
			else :
				navigation_after_str = "<a href='/mod_logs?page={}'>page{}&gt;&gt;</a>".format(page_to_show+1, page_to_show+1)

			if page_to_show == 1 :
				navigation_before_str = ''
			else :
				navigation_before_str = "<a href='/mod_logs?page={}'>&lt;&lt;page{}</a>".format(page_to_show-1, page_to_show-1)

			middle_separation = '|'		
			if len(navigation_after_str) == 0 or len(navigation_before_str) == 0 :
				middle_separation = ''

			navigation = '{} {} {}'.format(navigation_before_str, middle_separation, navigation_after_str)

			return render_template('mod_logs.html', logs=logs, navigation=navigation)
			



		if 'log_id' in request.args :
			cur.execute('SELECT * FROM moderator_log WHERE id=%s', (log_id_to_show,) )

			res = cur.fetchall()

			if not res :
				return render_template('404.html'), 404

			log = Handler.format_mod_log(res[0])

			return render_template('mod_logs.html', log=log, log_id_mode=True)

		
		return 'Critical failure detected. Server shutting down because of this query. Unauthorized access.', 404


	@staticmethod
	def representsInt(s):
		try: 
			int(s)
			return True
		except ValueError:
			return False


	@staticmethod
	def get_post_html( post_obj, you, get_inside_only=False ) :

		op_file_info_title_fmt = u"<span class='bold title'>{} </span>"		
		
		#post_div_fmt = u"<div class='post_container'> <div class='post {}' id='p{}'>{}</div> </div>"
		post_div_container_fmt = u"<div class='post_container'>{}</div>"
		post_div_inside_fmt = u"<div class='post {}' id='p{}'>{}</div>"

		post_info_fmt = u"<div class='post_info'> {} " \
					"{}" \
					"{}" \
					"{}" \
					"<span class='small ts' data-utc='{}'>{} </span>"\
					"<button class='report_button small'>{}</button> " \
					"<button class='hide_button small'></button> " \
					"<span><a href='#p{}'>No.</a><a class='post_num'>{}</a></span>" \
					"{}" \
					"<span class='qbl small' id='qbl{}'><span> Replies: </span></span>" \
					"</div>"

		file_stuff_fmt = u"<div class='file_info small'>" \
						"File: <a href='/static/images/{}' target='_blank'>{}</a>" \
						" ({}, {})" \
						"</div>" \
						"<a class='file_thumb' href='/static/images/{}' target='_blank'>" \
						"<img src='/static/images/{}' alt='{}'/>" \
						"</a>" 

		post_msg_fmt = u"<blockquote class='post_message'>{}</blockquote>"
		post_msg_deleted_fmt = u"<blockquote class='post_message deleted'>{}</blockquote>"

		## building actual html here
		
		post_deleted = post_obj['deleted']
		mod_post = post_obj['mod_post']
		is_op = post_obj['is_op']
		title = post_obj['title'] if is_op else ''

		blob_savename = blob_savename_s = blobname = None
		if 'blob_savename' in post_obj : 
			blob_savename = post_obj['blob_savename']
			blob_savename_s = post_obj['blob_savename_s']
			blobname = post_obj['blob_filename']
			blob_size = post_obj['blob_filesize']
			blob_dim = post_obj['blob_dimension']
		
		name = Handler.name_format(post_obj['name_raw'], False)
		text = post_obj['text']
		time = post_obj['time']
		utc  = post_obj['utc']
		post_id = post_obj['post_id']


		if post_deleted :
			if post_obj['delete_status'] == 4 :
				post_msg = post_msg_deleted_fmt.format('[post deleted by submitter]')
			else :
				post_msg = post_msg_deleted_fmt.format('[post deleted]')
		else :
			post_msg = post_msg_fmt.format(post_obj['text'])

		file_info = '' if ( post_deleted or blob_savename is None ) else file_stuff_fmt.format(
			blob_savename, blobname, blob_size, blob_dim, blob_savename, blob_savename_s, blob_size	)

		title_span = op_file_info_title_fmt.format(title) if is_op else ''
		poster_uid_span = u"<span class='poster_uid'> (ID:&nbsp;<span>&nbsp;{}&nbsp;</span>) </span>".format(post_obj['poster_uid'])
		moderator_span = u"<i class='moderator_style'>&nbsp;(mod)&nbsp;</i>" if mod_post else ''

		thread_extra_status = ''
		if is_op :
			if post_obj['thread_locked'] == 1 :
				thread_extra_status += "<i class='thread_locked' title='thread locked'><img src='/static/assets/lock.png' alt='lock' /></i>"
			if post_obj['thread_pinned'] == 1 :
				thread_extra_status += " <i class='thread_pinned' title='sticky'>(sticky)</i>"

		report_button_txt = 'delete' if you else 'report'

		post_info = post_info_fmt.format( title_span, name, moderator_span, poster_uid_span, utc, time, report_button_txt, post_id, post_id, thread_extra_status, post_id )

		op_post_class = "op_post" if is_op else ''

		inn = [post_info, file_info, post_msg]

		post_div_inside = post_div_inside_fmt.format(op_post_class, post_id, ''.join( inn ))

		if get_inside_only == True :
			return post_div_inside
		else :
			return post_div_container_fmt.format( post_div_inside )

	@staticmethod
	def name_format(name_raw, input=True) :
		pattern = re.compile('^(.*?)#(.{1,})$')

		trip_hash_str = u'{}'.format(app.config['TRIP_HASH_STR']) #make it utf or else 'ascii' codec can't encode character u'whatever' in position error

		m = pattern.match(name_raw)
		trip_str = ''

		if m :
			trip_str = m.group(2).strip()

		if input == True :
			if len(trip_str) == 0 :
				return name_raw
			else :
				strr = trip_hash_str.format(trip_str)
				sha256 = hashlib.sha256()
				sha256.update(strr.encode('utf-8'))
				trip = base64.b64encode(sha256.digest())[:8]
				name_part = m.group(1).strip()
				return u'{} #{}'.format(name_part, trip)

		else :
			if len(trip_str) == 0 :
				name_formatted = Handler.wbrify_htmlify(name_raw)
				return u"<span class='bold name'>{} </span>".format(name_formatted)
			else :
				name_part_formatted = Handler.wbrify_htmlify(m.group(1) )
				trip_formatted = Handler.wbrify_htmlify(m.group(2) )
				return u"<span class='bold name'>{}</span><span class='trip'>!{}</span>".format(name_part_formatted, trip_formatted)


	@staticmethod
	def get_poster_uid(user_id, board, thread_id) :
		c = '{}|{}|{}'.format(user_id,board,thread_id)
		m = hashlib.md5()
		m.update(c)
		return base64.b64encode( m.digest() )[0:8]


	@staticmethod
	def get_post_obj( row ) :
		post_obj = {}
		post_obj['post_id'] = row[0]
		post_obj['board'] = row[1]
		post_obj['thread_id'] = row[2]
		post_obj['user_id'] = row[3]

		utc = int(row[4])

		post_obj['time'] = datetime.utcfromtimestamp(utc + 19800).strftime("%d/%m/%Y(%a)%H:%M:%S")
		post_obj['utc'] = utc

		post_obj['name_raw'] = row[5]

		post_obj['is_op'] = row[2] == row[0]

		text_raw = row[6]
		re_title_pattern = re.compile('^\[subject\](.*)\[\/subject\]$')

		
		if post_obj['is_op'] :
			the_split = row[6].split('\n', 1)
			first_line = the_split[0]			
			re_title_match = re_title_pattern.match(first_line)
			if re_title_match :
				post_obj['title'] = Handler.wbrify_line(re_title_match.group(1))
				if len(the_split) > 1 :
					text_raw = the_split[1]
				else :
					text_raw = ''
			else :
				post_obj['title'] = ''

		post_obj['text_raw'] = text_raw
		post_obj['text'] = Handler.format_post_message( text_raw )

		post_obj['delete_status'] = row[10]
		post_obj['deleted'] = row[10] > 0
		post_obj['mod_post'] = row[11] > 0

		post_obj['poster_uid'] = Handler.get_poster_uid(post_obj['user_id'], post_obj['board'], post_obj['thread_id'])

		if row[7]:  #if blob_savename field is not null			
			post_obj['blob_savename'] = "%s.%s"  %(row[7], row[8])
			post_obj['blob_savename_s'] = "%s_s.%s"  %(row[7], 'jpg')

			blob_info = row[9]			
			blob_filename = blob_info['blob_filename']
			post_obj['blob_filesize'] = blob_info['blob_filesize']
			post_obj['blob_dimension'] = blob_info['blob_dimension']

			blob_filename_trimmed = (blob_filename[:30] + '(...)') if len(blob_filename)>35 else blob_filename
			blob_filename_formatted = Handler.html_escape( u'{}.{}'.format(blob_filename_trimmed, row[8]) )
			post_obj['blob_filename'] = blob_filename_formatted

		return post_obj

	@staticmethod
	def clean_post_message(text):
		text = text.strip()

		lines = []
		for line in text.splitlines():
			#lines.append(line.strip())
			lines.append(line)
		line_count = len(lines)
		return '\n'.join(lines), line_count
		return text

	@staticmethod
	def html_escape(str) :
		html_escape_table = {
		 "&": "&amp;",
		 '"': "&#34;",
		 "'": "&#39;",
		 ">": "&gt;",
		 "<": "&lt;",
		 }
		return "".join(html_escape_table.get(c,c) for c in str)  #escape html entities

 	
	@staticmethod
	def format_post_message(text):

		quote_pattern = re.compile(r'>{2,5}(\d{3,12})')

		quote_redirect_pattern = re.compile(r'(>{2,5}/?)([a-zA-Z_]{1,6})(?:/(\d{3,12}/?)(?:#(\d{3,12}))?)?/?')

		url_pattern = re.compile(r"https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{2,256}\.[a-z]{2,6}(?:\/[-a-zA-Z0-9@:%_\/.+~#?&=]*)?", re.IGNORECASE)

		text = text.strip()

		lines = []

		for line in text.splitlines():
			words = line.split()

			greentext_line = False

			for i in range(len(words)) :
				wo = words[i]  #word original
				wm = None #word modified			

				if wo.startswith('http') :
					url_match = url_pattern.match(wo)
					if url_match :
						url_str = url_match.string[url_match.start(0):url_match.end(0)]
						leftovers = Handler.wbrify_htmlify( url_match.string[url_match.end(0):] )

						if url_str[-1] == '.' :
							url_str = url_str[:-1]
							leftovers = '.' + leftovers

						wm = u"<a href='{}' target='_blank'>{}</a>{}".format(Handler.html_escape(url_str), Handler.wbrify_htmlify(url_str), leftovers )
						

				elif wo.startswith('>') :
					if wo.startswith('>>') :
						quote_match = quote_pattern.match(wo)
						if quote_match :
							quote_gt_str = Handler.html_escape(quote_match.string[quote_match.start(0):quote_match.start(1)] )
							quote_numb_str = quote_match.string[quote_match.start(1):quote_match.end(1)]
							leftovers = '<wbr>' + Handler.wbrify_htmlify( quote_match.string[quote_match.end(1):] )

							wm = u'<a class="quote_no" href="#p{}">{}{}</a>{}'.format(quote_numb_str, quote_gt_str, quote_numb_str, leftovers)

						if quote_match == None :
							quote_match = quote_redirect_pattern.match(wo)
							if quote_match :						

								groups = quote_match.groups()

								quote_gt_str = Handler.html_escape(groups[0])

								#if thread number is present
								if groups[2] != None :
									#if post number is present
									if groups[3] != None :
										inn = '{}{}/{}#{}'.format(quote_gt_str, groups[1], groups[2], groups[3])
										href = '/boards/{}/thread/{}/#p{}'.format(groups[1], groups[2], groups[3])
									else :
										inn = '{}{}/{}'.format(quote_gt_str, groups[1], groups[2])
										href = '/boards/{}/thread/{}'.format(groups[1], groups[2])
								
									leftovers = '<wbr>' + Handler.wbrify_htmlify( quote_match.string[quote_match.end(0):] )								
									wm = u'<a class="quote_redirect" href="{}" target="_blank">{}</a>{}'.format(href, inn, leftovers)



						if wm == None and i == 0 :
							greentext_line = True

					elif i == 0 :
						greentext_line = True
				
				
				if wm is None :
					wm = Handler.wbrify_htmlify(wo)

				words[i] = wm

			new_line = ' '.join(words)

			if greentext_line == True :
				new_line = u'<span class=\'quote_txt\'>{}</span>'.format(new_line)
				
			lines.append(new_line)

		return '<br>'.join(lines)



	#@staticmethod
	#def wbrify(str) :
	#	return '<wbr>'.join( [ str[0+x:35+x] for x in range(0, len(str), 35) ] )

	@staticmethod
	def format_mod_log(log) :
		idee, mod_username, ts, action, info = log

		duration = Handler.getAgeFromDatetime(ts)

		mod_log_href = '/mod_logs/?log_id={}'.format(idee)
		action_line_fmt = u"action : <span class='action'>{{}}</span> | {} ago | <a href='{}' target='_blank'>(link)</a>"\
						.format(duration, mod_log_href)

		mod_line = u"<span>mod : {} </span>".format(mod_username)


		lines = []

		if action == 'login' or action == 'logout' :
			lines.append(action_line_fmt.format(action) )
			lines.append('<br>')
			lines.append(mod_line)

		elif action == 'start_post' :
			lines.append(action_line_fmt.format('start post'))
			lines.append('<br>')
			lines.append(mod_line)
			lines.append('<br><br>')
			lines.append(Handler.get_post_formatted_line_from_mod_log(info, True) )

		elif action == 'delete_post' :
			action_str = 'delete post'
			if info['delete_permanently'] == 1 :
				action_str += ' (hard)'
			lines.append(action_line_fmt.format(action_str) )
			lines.append('<br>')
			lines.append(mod_line)
			lines.append('<br><br>')
			lines.append(Handler.get_post_formatted_line_from_mod_log(info, False) )
			lines.append('<br>')

			reason = 'spamming / flooding'
			if info['delete_reason'] == 'illegal' :
				reason = 'illegal / improper content'

			reason_text = Handler.wbrify_line(info['delete_reason_text'] )

			lines.append('<span>reason : {}</span><br>'.format(reason) )
			lines.append(u'<span>reason text : {}</span><br>'.format(reason_text) )

			extra_actions_list = []
			if info['delete_subsequent'] == 1 :
				extra_actions_list.append('subsequent posts by poster deleted')
			if info['unbump'] == 1 :
				extra_actions_list.append('thread unbumped')
			if info['ban_duration'] != '0h' :
				extra_actions_list.append("poster was banned for '{}'".format(info['ban_duration'] ) )
			
			if len(extra_actions_list) > 0 :
				extra_actions = '<br><span>extra actions : {}</span>'.format(' and '.join(extra_actions_list) )
				lines.append(extra_actions)

			

		elif action == 'undelete_post' :
			lines.append(action_line_fmt.format('undelete post') )
			lines.append('<br>')
			lines.append(mod_line)
			lines.append('<br><br>')
			lines.append(Handler.get_post_formatted_line_from_mod_log(info, True) )

			extra_actions_list = []
			if info['unban'] == 1:
				extra_actions_list.append('poster was unbanned')
			if info['undelete_subsequent'] == 1 :
				extra_actions_list.append('subsequent posts were undeleted')

			if len(extra_actions_list) > 0 :
				extra_actions = '<br><br><span>extra actions : {}</span>'.format(' and '.join(extra_actions_list) )
				lines.append(extra_actions)


		elif action == 'update_thread' :
			lines.append(action_line_fmt.format('update thread') )
			lines.append('<br>')
			lines.append(mod_line)
			lines.append('<br><br>')
			lines.append(Handler.get_post_formatted_line_from_mod_log(info, True) )

			extra_actions_list = []
			if 'pin' in info :
				if info['pin'] == 1 :
					extra_actions_list.append('pinned')
				elif info['pin'] == 0 :
					extra_actions_list.append('unpinned')
			if 'lock' in info :
				if info['lock'] == 1 :
					extra_actions_list.append('locked')
				elif info['lock'] == 0 :
					extra_actions_list.append('unlocked')

			if len(extra_actions_list) > 0 :
				extra_actions = '<br><br><span>thread was {}</span>'.format(' and '.join(extra_actions_list) )
				lines.append(extra_actions)

		elif action == 'move_thread' :
			lines.append(action_line_fmt.format('move thread') )
			lines.append('<br>')
			lines.append(mod_line)
			lines.append('<br><br>')
			thread_element = "<a href='/boards/{}/thread/{}/' target='_blank'>thread : {}</a>" \
						.format(info['board_dst'], info['thread_id'], info['thread_id'] )
			from_board = "from : /{}/".format(info['board_src'] )
			to_board = "to : /{}/".format(info['board_dst'] )

			lines.append("{} | {} | {}".format(thread_element, from_board, to_board) )

		return u' '.join(lines)

	@staticmethod
	def get_post_formatted_line_from_mod_log(info, hrefify=True) :		

		post_element = ''
		thread_element = ''

		href_post = True	

		if 'post_id' in info :
			if info['thread_id'] == info['post_id'] :		
				href_post = False
		else :
			href_post = False
		

		if hrefify == True :
			if href_post == False :	
				thread_element = "<a href='/boards/{}/thread/{}/' target='_blank'>thread : {}</a> | "\
						.format(info['board'], info['thread_id'], info['thread_id'] )
			else :
				post_element = "<a href='/boards/{}/thread/{}/#p{}' target='_blank'>post : {}</a> | "\
						.format(info['board'], info['thread_id'], info['post_id'], info['post_id'] )


		if href_post == True and len(post_element) == 0 :
			post_element = "post : {} | ".format(info['post_id'] )

		if len(thread_element) == 0 :
			thread_element = "thread : {} | ".format(info['thread_id'] )

		board_element = 'board : /{}/'.format(info['board'] )

		return '<span>{}{}{}</span>'.format(post_element, thread_element, board_element)








	@staticmethod
	def getAgeFromDatetime(d) :
		d = d.replace(tzinfo=None)
		delta = datetime.utcnow() - d

		s = int(delta.total_seconds())

		if(s < 0) :
			return '0 s'
		if(s < 60) :
			return str(s) + 's'
		if(s < 60*60) :
			minutes = int(s/60)
			r = '{}m'.format(minutes)			
			return r
		if(s < 24*60*60) :
			hours = int(s/(60*60))
			r = '{}h'.format(hours)			
			return r

		days = int(s/(24*60*60))
		r = '{}d'.format(days)		
		return r

	@staticmethod
	def wbrify_htmlify(str) :		
		return '<wbr>'.join( [ Handler.html_escape( str[0+x:35+x] ) for x in range(0, len(str), 35) ] )


	@staticmethod
	def wbrify_line(txt) :
		lines = []
		for line in txt.splitlines():
			words = line.split()
			for i in range(len(words)) :				
				if len(words[i]) > 35 :
					words[i] = Handler.wbrify_htmlify(words[i])

			lines.append(' '.join(words))
		return ' '.join(lines)

	@staticmethod
	def single_linify(txt) :
		lines = txt.splitlines()
		return ' '.join(lines)

	@staticmethod
	def check_if_name_is_mod_postable(name) :            
		if len(name) > 9 and name.startswith('!!') and name.endswith('!!') :
			return 1
		elif name.startswith('!') or name.endswith('!') :
			return -1
		else :
			return 0


	@staticmethod
	def user_id(): 
		strr = app.config['IP_HASH_STR'].format(request.remote_addr)
		sha256 = hashlib.sha256()
		sha256.update(strr)
		return base64.b64encode(sha256.digest())[:10]



		
			
