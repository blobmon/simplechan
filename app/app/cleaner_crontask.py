#!/user/bin/env python
# coding: utf-8 -*-

from app import app
import psycopg2
import os
import time

def run():
    log("cleaner_crontask started")

    con = psycopg2.connect("dbname='{}' user='{}'".format(app.config['DB_NAME'], app.config['DB_ROLE']) )
	
    cur = con.cursor()

    #cleaning threads first

    #get the list of threads which have delete_status > 0 ( marked for deletion ) and had last bump > 7 days
    cur.execute("SELECT * FROM threads WHERE delete_status>0 AND now() - bump_ts > INTERVAL '7day' ")
    threads = cur.fetchall()

    thread_list = []

    #for each thread
    for thread in threads :
        thread_id = thread[0]

        #append to list so we can delete in bulk
        thread_list.append(thread_id)

        cur.execute("SELECT id, blob_savename, blob_type FROM posts WHERE thread_id=%s", (thread_id,) )
        posts = cur.fetchall()
        delete_posts(cur, posts)

    cur.execute("DELETE FROM threads WHERE post_id = ANY(%s)", (thread_list,) )

    #commit
    con.commit()

    #cleaning posts which are not threads next
    cur.execute("SELECT id, blob_savename, blob_type FROM posts WHERE delete_status>0 AND id != thread_id AND now() - ts > INTERVAL '7day' ")
    posts = cur.fetchall()

    delete_posts(cur, posts, True)

    #commit
    con.commit()
    
    con.close()
    log("cleaner_crontask finished")
    return 0


def delete_posts(cur, posts, blob_only=False) :
    post_list = []
    for post in posts :
        post_id = post[0]
        blob_savename = post[1]
        blob_savetype = post[2]

        #add post_id to list so we can delete all the items in bulk from db
        post_list.append(post_id)
        
        #delete the image associated with post if it exists
        if blob_savename is not None :
            blob_filename_actual = "{}.{}".format(blob_savename, blob_savetype)
            blob_filename_thumb = "{}_s.jpg".format(blob_savename, blob_savetype)

            blob_savepath_actual = os.path.join(app.config['UPLOAD_FOLDER'], blob_filename_actual)
            blob_savepath_thumb = os.path.join(app.config['UPLOAD_FOLDER'], blob_filename_thumb) # thumb is always jpg remember?

            if os.path.isfile( blob_savepath_actual ) :
                os.remove(blob_savepath_actual)
                os.remove(blob_savepath_thumb)
            else :
                #log(u"cleaner_crontask error finding file to delete : {}".format(blob_filename_actual))
                pass
                

    #delete the posts from db
    if blob_only == False :
        cur.execute("DELETE FROM posts WHERE id = ANY(%s)", (post_list,) )
    
    
def log(msg):
    print "{} {}".format(time.strftime("%d/%m/%Y(%a)%H:%M:%S") , msg)

