from app import app

#this line would be used when running directly without uwsgi
if __name__ == '__main__':
	app.run(host='0.0.0.0', debug=True)
