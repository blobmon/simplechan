
Simplechan is a chan software where you can create a chan similar to notorious 4chan (similar not exactly same). It is designed simply as the name suggests and is designed to not track users and to be very fast. 

Software development shouldn't be something vague and complicated. It is supposed to be fun and simple. The resulting software should never be bloated and slow. It has to be simple and fast. Therefore, functional. So Simplechan is an attempt at keeping the whole thing that way. 

This readme might feel too conversational. But I feel it is a nice approach to write it in this manner. And also, this readme might feel inadequate at some places. I will update it as per feedback I receive. Let us begin.

###How to go about setting up things and doing things?

This tutorial is for linux or linux like machines. I use `python2.7` throughout the code.

I have used `virtualenv` to set up python virtual environment. I have used /venv/ folder to set up a python `virtualenv`. `virtualenv` isn't really needed but it keeps all the python related installations in that location and not system wide. So install `virtualenv`.

Install `postgresql` database server in your machine. Make sure it is version 9.5 or great.

After installing `postgresql`, open command line and enter these commands line-by-line making sure you are doing correctly every time...
This command is for opening `psql` with default `postgres` user. Just typing `psql` while being normal user will fail because `postgres` user requires `postgres` db to open. It is extra step which postgresql people might have avoided. But it is needed for security I think.
```
$sudo su - postgres
$psql
```

Once you are inside `psql`, create a role and a database with your desired name. In default case, I have used `simplech_role` and `simplech_db` for role and database name respectively. Type these commands...

```
CREATE ROLE simplech_role WITH SUPERUSER CREATEDB LOGIN;
CREATE DB simplech_db WITH OWNER simplech_role;
```

Come out of `psql` by pressing ctrl+D and also come out of `postgres` user by pressing ctrl+D again. 

Now, once you are back again being the normal, default user, `cd` into `/sql/` directory in Simplechan repository. We are going to create tables and functions now.

Try opening `psql` with the latest created db and role. In my default case, I try opening psql with `simplech_db` and `simplech_role`. 

```
$psql -d simplech_db -U simplech_role
```

Create tables by importing those sql files now. Type these commands...

```
\i create_table_query.sql
\i functions.sql
\i functions_moderator.sql
```

Make sure those sql statements were imported and executed without errors. If there are errors, make sure to fix them. I think an error might come when you type `\i create_table_query.sql` with extension `uuid-ossp`. It can be easily fixed by installing some extra postgres package. Any other error you might encounter, should be easily fixable.

Now, we need to create boards for the chan. In my example case, I have created two boards.

```
INSERT INTO boards (board, display_name) VALUES ('board1', 'Board 1');
INSERT INTO boards (board, display_name) VALUES ('board2', 'Board 2');
```

Now, database work is done (the basic parts at least). Now, we need to set up `virtualenv` inside `/venv/` directory. 
`cd` into `/venv/` directory in Simplechan repository. 
Type this command below to set up `virtualenv` with `python` version 2.7

```
$virtualenv --python=/path/to/python2.7 .
```
Now, activate the `virtualenv` by typing
```
$source bin/activate
```

A `(venv)` prefix should appear in your command line. This means the python virtual environment is active now. Any result of `python` commands will use this folder as a base folder. So, we install the required python libraries required to run this chan by typing
```
$pip install -r requirements.txt
```
Make sure all requirements are successfully installed without errors.

Now, in case you want webm support, you might also want to install `ffmpeg` in your machine. Because python app will call `ffmpeg` to check validity of uploaded video. If you don't want webm support, comment out those lines in `blobHandler.py` where verify video happens and replace it with `pass`

Finally, rename `appconfig_template.cfg` to `appconfig.cfg` and update proper `UPLOAD_PATH`, `DB_NAME,` `DB_ROLE`, and hash values as required.

Now, we `cd` into `/app/` directory and run
```
$python runserver.py
```
Simplechan should be running in localhost port 5000



