import psycopg2
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

import time
from datetime import datetime
import os

from app import app # circular import sorta

from flask import render_template, session, url_for, jsonify, request, redirect


class Handler_mod :
	def __init__ (self) :
		self.con = psycopg2.connect("dbname='{}' user='{}'".format(app.config['DB_NAME'], app.config['DB_ROLE']) )
	def __del__ (self) :
		if self.con :
			self.con.close()


	def login(self) :
		if request.method == 'GET' :
			u = self.check_session_valid_and_get_username()
			if u != -1 :
				return redirect(url_for('mod_lounge'))
			return render_template('mod_login.html')

		else :
			returnable = 'password incorrect', 400

			if 'password' in request.form :
				password = request.form['password']

				from handler import Handler
				user_id = Handler.user_id()

				if len(password) > 4 and len(password) < 40 :
					import hashlib
					m = hashlib.md5()
					m.update(password.encode('utf-8') )
					passwordmd5 = m.hexdigest()

					#get session id from the password given now
					cur = self.con.cursor()
					cur.execute("SELECT * FROM moderator_login(%s, %s)", (user_id,passwordmd5) )

					res = cur.fetchall()
					self.con.commit()

					row = res[0]
					if row[0] == 1 :
						session['session_id'] = row[1]
						return redirect(url_for('mod_lounge') )
					else :
						return row[1], 400

			return returnable

	def logout(self) :
		u = self.check_session_valid_and_get_username()		
		if u != -1 :
			cur = self.con.cursor()
			cur.execute("SELECT * FROM moderator_logout(%s)", (session['session_id'],) )

			res = cur.fetchall()
			self.con.commit()			
		
		return redirect(url_for('mod_login') )



	def lounge(self) :
		u = self.check_session_valid_and_get_username()
		if u != -1 :
			return render_template('mod_lounge.html', mod_username=u)
		return redirect(url_for('mod_login') )


	def report_list(self) :
		u = self.check_session_valid_and_get_username()
		if u == -1 :
			return redirect(url_for('mod_login') )

		cur = self.con.cursor()	
		cur.execute("SELECT report_src.post_id, posts.thread_id, posts.board, report_src.reason FROM report_src INNER JOIN posts ON posts.id=report_src.post_id WHERE posts.delete_status=0 AND report_src.ts > now()-interval'90 days' AND report_src.consumed='f' ORDER BY report_src.post_id")
		res = cur.fetchall()
	
		obj = {}

		for row in res :
			post_id, thread_id, board, reason = row

			post_id_str = '%d' %post_id

			if post_id == thread_id :                 
				post_display_str = '%s/%d' %(board,post_id)
			else :
				post_display_str = '%s/%d#%d' %(board,thread_id,post_id)

			post_url = '/boards/{}/thread/{}#p{}'.format(board,thread_id,post_id)

			idx = 0
			if reason == 2 :
				idx = 1;

			if post_id_str not in obj :
				obj[post_id_str] = {'report_tpl' : [0,0], 'display_str' : post_display_str, 'post_url' : post_url }

			obj[post_id_str]['report_tpl'][idx] += 1

		lst = obj.items()
		lst.sort( key=lambda item : int(item[0]), reverse=True )

		lines = []
		for row in lst :
			post_id, post_obj = row
			report_tpl = post_obj['report_tpl']
			str_fmt = u"<tr> <td class='post_num'><a href='{}' target='_blank'>{}</a></td> <td>{} | {}</td></tr>"
			lines.append( str_fmt.format(post_obj['post_url'], post_obj['display_str'], report_tpl[0], report_tpl[1]) )

		reports = '\n'.join(lines)
		return render_template('mod_report_list.html', reports=reports)     
	

	def update_post(self) :
		u = self.check_session_valid_and_get_username()
		if u == -1 :
			if request.method == 'GET' :
				return redirect(url_for('mod_login') )
			else :
				return 'session expired. login again please', 400

		#if session is valid

		if request.method == 'GET' :
			return render_template('mod_update_post.html', mod_username=u )
		
		#when request.method is POST and session is valid : 
		cur = self.con.cursor()	

		if 'load_post' in request.form :
			post_id = int(request.form['post_id']) 
			
			cur.execute('SELECT * FROM posts WHERE id=%s', (post_id,) )
			res = cur.fetchall()
			if not res :
				return 'post not found', 404


			post_row = res[0]
			post_obj = Handler_mod.get_post_obj(post_row)

			#fetch the thread
			cur.execute('SELECT * FROM threads WHERE post_id=%s', (post_obj['thread_id'],) )
			res = cur.fetchall()
			
			thread_row = res[0]

			if post_obj['is_op'] == 1:
				post_obj['lock'] = thread_row[8]
				post_obj['pin'] = thread_row[9]

			post_html = Handler_mod.get_post_html(post_obj)

			returnable = {'post_id': post_obj['post_id'], 'thread_id' : post_obj['thread_id'], 'board' : post_obj['board'], 
						'delete_status' : post_obj['delete_status'], 'html' : post_html }
			if 'lock' in post_obj :
				returnable['lock'] = post_obj['lock']
			if 'pin' in post_obj :
				returnable['pin'] = post_obj['pin']

			return jsonify(returnable)

		if 'delete_post' in request.form :

			try :
				post_id = int(request.form['post_id'])

				delete_reason = request.form['reason']
				duration = int(request.form['duration'])

				delete_subsequent = int(request.form['delete_subsequent'])
				unbump = int(request.form['unbump'])
				delete_permanently = int(request.form['delete_permanently'])

				delete_reason_text = '\\n'.join(request.form['delete_reason_text'].splitlines() )
				delete_reason_text = delete_reason_text.replace('"', '\\"')  #because it is going inside json
			except ValueError :
				return 'major server malfunction detected!', 400  #exaggeration 

			if delete_reason != 'spam' and delete_reason != 'illegal' :
				return 'delete reason is improper', 400

			if len(delete_reason_text) < 4 or len(delete_reason_text) > 400 :
				return 'delete reason text is wrong', 400
			if duration > 400 :
				return "can't ban the user for so long", 400


			duration_text = '{}h'.format(duration)

			
			cur.execute('SELECT * FROM moderator_delete_and_ban_post(%s,%s,%s,%s,%s,%s,%s,%s)', 
				(session['session_id'],post_id,delete_reason, duration_text, delete_subsequent,unbump,delete_permanently, delete_reason_text) )
			res = cur.fetchall() 
			self.con.commit()

			row = res[0]

			if row[0] == -1 :
				return row[1], 400
			else :
				returnable = { 'post_id' : post_id, 'duration' : duration }
				return jsonify(returnable)

		elif 'undelete_post' in request.form :
			try :
				post_id = int(request.form['post_id'])
				undelete_subsequent = int(request.form['undelete_subsequent'])
				unban = int(request.form['unban'])
			except ValueError :
				return 'major server malfunction detected!', 400

			cur.execute('SELECT * FROM moderator_undelete_post(%s, %s, %s, %s)',
				(session['session_id'], post_id, undelete_subsequent, unban) )
			res = cur.fetchall()
			self.con.commit()

			row = res[0]

			if row[0] == -1 :
				return row[1], 400
			else :
				returnable = {'post_id' : post_id}
				return jsonify(returnable)

		elif 'update_thread' in request.form :
			try :
				thread_id = int(request.form['thread_id'])
				pin = int(request.form['pin'])
				lock = int(request.form['lock'])

			except ValueError :
				return 'major server malfunction detected!', 400

			cur.execute('SELECT * FROM moderator_update_thread(%s,%s,%s,%s)',
				(session['session_id'], thread_id, lock, pin) )
			res = cur.fetchall()
			self.con.commit()

			row = res[0]

			if row[0] == -1 :
				return row[1], 400
			else :
				returnable = {'thread_id' : thread_id}
				return jsonify(returnable)

		elif 'move_thread' in request.form :
			try :
				thread_id = int(request.form['thread_id'])
				board_dst = request.form['board_dst']
			except ValueError :
				return 'major server malfunction detected!', 400

			if len(board_dst) == 0 :
				return 'board dst empty', 400

			cur.execute('SELECT * FROM moderator_move_thread(%s, %s, %s)',
				(session['session_id'], thread_id, board_dst) )
			res = cur.fetchall()
			self.con.commit()

			row = res[0]

			if row[0] == -1 :
				return row[1], 400
			else :
				returnable = {'thread_id' : thread_id}
				return jsonify(returnable)


	def recent_posts(self) :
		u = self.check_session_valid_and_get_username()
		if u == -1 :			
			return redirect(url_for('mod_login') )

		#all good, get and render page...

		MAX_POSTS = 100

		page = 1
		if 'page' in request.args :
			try :
				page = int(request.args['page'])
				if page < 1 :
					page = 1
				if page > 100 :
					page = 100
			except ValueError :
				pass

		offset = (page-1)*MAX_POSTS		

		cur = self.con.cursor()
		cur.execute('SELECT * FROM posts ORDER BY ts DESC LIMIT %s OFFSET %s', (MAX_POSTS, offset) )
		res = cur.fetchall()

		posts = []

		for row in res :
			post_obj = Handler_mod.get_post_obj(row)
			post_html = Handler_mod.get_post_html(post_obj)
			posts.append( post_html )


		''' navigation logic
		if not MAX_POSTS results returned, dont show next
		if page is 100, dont show next
		if page is 1, dont show prev
		'''
		
		if page == 100 or len(posts) < MAX_POSTS :
			navigation_after_str = ''
		else :
			navigation_after_str = "<a href='/mod_recent_posts?page={}'>page{}&gt;&gt;</a>".format(page+1, page+1)

		if page == 1 :
			navigation_before_str = ''
		else :
			navigation_before_str = "<a href='/mod_recent_posts?page={}'>&lt;&lt;page{}</a>".format(page-1, page-1)

		middle_separation = '|'		
		if len(navigation_after_str) == 0 or len(navigation_before_str) == 0 :
			middle_separation = ''

		navigation = '{} {} {}'.format(navigation_before_str, middle_separation, navigation_after_str)		

		return render_template('mod_recent_posts.html', posts=posts, navigation=navigation)



	def check_session_valid_and_get_username(self) :
		if 'session_id' in session :
			from uuid import UUID
			try :
				uuid_obj = UUID(session['session_id'], version=4)

				cur = self.con.cursor()
				cur.execute("SELECT * FROM moderator_check_login_status_and_get_username(%s)", (session['session_id'],) )

				res = cur.fetchall()
				self.con.commit()

				row = res[0]

				if row[0] == 1 :
					return row[1]				
			except :
				pass

		return -1

	@staticmethod
	def get_post_obj( row ) :
		post_obj = {}
		post_obj['post_id'] = row[0]
		post_obj['board'] = row[1]
		post_obj['thread_id'] = row[2]
		post_obj['user_id'] = row[3]

		post_obj['name'] = Handler_mod.wbrify_htmlify( row[5] )
		post_obj['text'] = Handler_mod.format_post_message( row[6] )
		post_obj['status'] = row[10]
		post_obj['delete_status'] = row[10]
		post_obj['is_op'] = row[2] == row[0]

		if row[7]:
			post_obj['blob_savename_s'] = "%s_s.%s"  %(row[7], 'jpg')

		return post_obj

	@staticmethod
	def get_post_html( post_obj ) : 

		innards_list = []  

		fmt = u"<div class='post_container {}'><div class='post'>{}</div> </div>"

		post_link_href = ''
		post_link_str = ''

		op_class_str = 'op_post'

		if post_obj['is_op'] :
			post_link_href = '/boards/{}/thread/{}/'.format(post_obj['board'], post_obj['thread_id'], '')
			post_link_str = '>>{}/{}/ (OP)'.format(post_obj['board'], post_obj['thread_id'])
		else :
			post_link_href = '/boards/{}/thread/{}/#p{}'.format(post_obj['board'], post_obj['thread_id'], post_obj['post_id'])
			post_link_str = '>>{}/{}/#{}'.format(post_obj['board'], post_obj['thread_id'], post_obj['post_id'])
			op_class_str = ''

		
		post_link = u"<a href='{}' target='_blank'>{}</a>".format(post_link_href, post_link_str)
		

		
		delete_text = ''
		if post_obj['delete_status'] > 0 :
			delete_text = ' deleted'
			delete_status = post_obj['delete_status']

			if delete_status == 4 :
				delete_text += ' (by submitter)'
			elif delete_status == 3 :
				delete_text += ' (by mod)'
			elif  delete_status == 10 :
				delete_text += ' hard (by mod)'
			
		extra_elements = ''
		extra_elements_inn = ''
		if 'lock' in post_obj and post_obj['lock'] == 1 :
			extra_elements_inn += '(locked)'
		if 'pin' in post_obj and post_obj['pin'] == 1 :
			extra_elements_inn += '(pinned)'
		if len(extra_elements_inn) > 0 :
			extra_elements = u'<span>{}</span>'.format(extra_elements_inn)

		post_info = u"<span class='poster_name'>{}</span> {} <span class='post_deleted'>{}</span> {} <br><br>".format(
					post_obj['name'], post_link, delete_text, extra_elements )

		innards_list.append(post_info)

		if 'blob_savename_s' in post_obj :
			img_fmt = u"<img class='post_img' src='/static/images/{}' />"
			innards_list.append( img_fmt.format( post_obj['blob_savename_s'] ) )

		post_text_fmt = u"<blockquote class='post_text'>{}</blockquote>"	
		post_text = post_text_fmt.format(post_obj['text'])
		innards_list.append(post_text)
			
		return fmt.format( op_class_str, '\n'.join(innards_list) )
	

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
	def wbrify_htmlify(str) :		
		return '<wbr>'.join( [ Handler_mod.html_escape( str[0+x:35+x] ) for x in range(0, len(str), 35) ] )

	@staticmethod
	def format_post_message(text):
		text = text.strip()

		lines = []

		for line in text.splitlines():
			words = line.split()
			for i in range(len(words)): 
				w = words[i]				
				words[i] = Handler_mod.wbrify_htmlify(w)

			new_line = ' '.join(words)
			lines.append(new_line)

		return '<br>'.join(lines)