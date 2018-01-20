function init() {
	board_select_set_callbacks(board_name)
	theme_select_set_callbacks()

	//start_thread_click
	var start_thread_link_container = document.getElementById('start_thread_link_container')
	var start_thread_form = document.getElementById('start_thread_form')

	var on_start_thread_click_call = function(evnt) {
		start_thread_link_container.style.display = 'none'
		start_thread_form.style.display = 'block'
		evnt.stopPropagation()
	}

	start_thread_link.addEventListener('click', on_start_thread_click_call, false)

	//set sort listener

	var sort_select = document.getElementById('select_sort_method')
	sort_select.onchange = function(){
		var v = sort_select.value
		//save in local store
		window.localStorage.setItem('ich_sort_order', v);
		on_sort_select_set(v)
	}

	//get sort value and set
	var stored_sort_order = window.localStorage.getItem('ich_sort_order');
	if(stored_sort_order != null) {
		sort_select.value = stored_sort_order
		on_sort_select_set(stored_sort_order)
	}

}

function on_thread_submit(button) {

	var form_element = document.forms.start_thread_form
	var form_data = new FormData()

	var eee = form_element.elements

	var name_e = eee.name
	var subject_e = eee.subject
	var text_e = eee.text
	var image = eee.image.files[0]

	//cleaning form values
	var name = name_e.value = name_e.value.trim()
	var subject = subject_e.value = subject_e.value.trim()
	var text = text_e.value = text_e.value.trim()

	if(name.length > 50 || name.split(/\r\n|\r|\n/).length > 1 ) {
		start_thread_status_set('Error : Name too long', 'bad')
		return
	}
	if(subject.length > 100 || subject.split(/\r\n|\r|\n/).length > 1 ) {
		start_thread_status_set('Error : Subject too long', 'bad')
		return
	}

	if(text.length > 1800 || text.split(/\r\n|\r|\n/).length > 40 ) {
		start_thread_status_set('Error : Text too long', 'bad');
		return
	}

	if (text.length === 0 && subject.length === 0 ) {
		start_thread_status_set('Error : Empty content', 'bad');
		return
	}

	if( image == null ) {
		start_thread_status_set('Error : No image attached', 'bad')
		return
	}

	// adding to form
	form_data.append('name', name)
	form_data.append('subject', subject)
	form_data.append('text', text)
	form_data.append('board_name', board_name)
	form_data.append('image', image)

	// all good. time to post it
	button.disabled = true;
	start_thread_status_set('', '')

	function on_ok(d) {
		var json = JSON.parse(d)
		var post_id = json.post_id
		var redirect = json.redirect_url

		var msg = 'post #' + post_id + ' created. Redirecting...'
		start_thread_status_set(msg, 'good')

		var redirect_call = function(){			
			window.location = redirect
		}

		setTimeout(redirect_call, 1500)
	}

	function on_progress(d) {
		if (d.lengthComputable) {
			var percentComplete = Math.round((d.loaded / d.total)*100);			
			if(percentComplete > 0) {
				button.innerHTML = percentComplete + '%'
			}
		}
	}

	function on_fail(status, d) {
		if(status == 500 || status == 400) {
			start_thread_status_set('Error : ' + d, 'bad')
		} 
		else if(status == 413) {
			start_thread_status_set('Error : image size too large', 'bad')
		}
		else {
			start_thread_status_set('Error : ' + status, 'bad')
		}
		button.disabled = false
		button.innerHTML = 'Post'
	}

	send_form(form_data, '/engine/start_thread/', on_ok, on_progress, on_fail); 	
	
}

function start_thread_status_set(msg, className) {	
	e = document.getElementById('start_thread_status_div')
	e.innerHTML = msg
	e.className = className
}

function on_sort_select_set(value) {
	
	var data_attrib = 'bump_ts'
	var low = -1
	if(value === 'creation_date') {
		data_attrib = 'ts'		
	}
	else if(value === 'reply_count') {
		data_attrib = 'reply_count'
	}

	var sort_func = function(a,b) {
		var one = parseInt(a.dataset[data_attrib])
		var two = parseInt(b.dataset[data_attrib])	

		return one == two ? 0: (one > two ? low : -low)
	}

	var div_list = document.getElementById('div_list')
	var items_arr = []
	var items = div_list.children  // this is not an array

	//flling up items_arr
	for(var i=0; i<items.length; i++){
		items_arr.push(items[i])
	}

	items_arr.sort(sort_func)	

	//empty it first
	while (div_list.firstChild) {
		div_list.removeChild(div_list.firstChild)
	}

	for (var i = 0; i < items_arr.length; i++) {
  		div_list.appendChild(items_arr[i])
	}
}


document.addEventListener("DOMContentLoaded", init);

// util functions
function send_form(form_data, endpoint, on_ok, on_progress, on_fail) {
	var xhr = new XMLHttpRequest();
	if(on_progress != null) { xhr.upload.addEventListener('progress', on_progress) }
	
	xhr.open('POST', endpoint );
	xhr.onreadystatechange = function() {
		if(xhr.readyState === 4 ) {
			if(xhr.status == 200 ) {
				on_ok(xhr.responseText);
			}
			else {				
				console.log('failed with status : ' + xhr.status + ' and readyState : ' + xhr.readyState);
				on_fail(xhr.status, xhr.responseText)
			}
		}
	}

	xhr.send(form_data);
}


// trim polyfill
if (!String.prototype.trim) {
  String.prototype.trim = function () {
    return this.replace(/^[\s\uFEFF\xA0]+|[\s\uFEFF\xA0]+$/g, '');
  };
}


function board_select_set_callbacks(default_select) {
	var select = document.getElementById('board_select')

	if(default_select) {
		select.value = default_select
	}

	select.onchange = function(){
		window.location = '/boards/' + select.value + '/' ; // redirect
	}
}

function theme_select_set_callbacks() {
	var select = document.getElementById('theme_select')
	var stored_theme = window.localStorage.getItem('ich_theme')
	if(stored_theme != null) {
		select.value = stored_theme
		document.getElementById('theme_stylesheet').href = '/static/style_' + stored_theme + '.css'
	}

	select.onchange = function(){
		window.localStorage.setItem('ich_theme', select.value)
		document.getElementById('theme_stylesheet').href = '/static/style_' + select.value + '.css'
	}
}
