#!/usr/bin/env python
# -*- coding: utf-8 -*- 

import os
from PIL import Image
import time
import random

#turn warning to error
Image.warnings.simplefilter('error', Image.DecompressionBombWarning)

class BlobHandler :

	def __init__ (self, blob_file) :
		self.blob_file = blob_file
		
		self.blob_thumb = None

		#default values
		self.dimension = (0, 0)		

		self.filename = None
		self.save_path = None
		


	def verify(self, save_path) :
		filename = self.blob_file.filename
		if len(filename) == 0 :
			return 'file name error', 0

		self.filename = os.path.splitext(filename)[0]
		self.save_path = save_path

		verify_image_res = self.verify_image()

		if verify_image_res == 1 :	
			return 1
		elif verify_image_res[1] == -1 : # incase is not an image 
			return self.verify_video()
		else :
			return verify_image_res




	# returns 1 on success, tuple on failure
	def verify_video(self) :
		import subprocess
		import json

		file_type_not_supported_tuple = 'file type not supported', 0
		video_seems_to_be_corrupt_tuple = 'video seems to be corrupt', 0

		
		self.blob_file.flush() #it is weird but files are not streamed into ffprobe properly without this call
		self.blob_file.seek(0) #seek to zero since verify_image has seeked ahead already

		proc = subprocess.Popen(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-i', '-' ], stdin=self.blob_file , stdout = subprocess.PIPE)
					
		std_out, std_err = proc.communicate()			

		probe_info = json.loads(std_out)

		try :
			proc.terminate()
		except Exception as e :				
			pass
		

		if 'format' not in probe_info :
			return file_type_not_supported_tuple
		if probe_info['format']['format_name'] != "matroska,webm" :
			return file_type_not_supported_tuple
		if 'streams' not in probe_info :
			return video_seems_to_be_corrupt_tuple

		video_stream_index = -1

		for stream in probe_info['streams'] :
			if (stream['codec_name'] == 'vp8' or stream['codec_name'] == 'vp9') and stream['codec_type'] == 'video' :
				video_stream_index = int(stream['index'])
				break

		if video_stream_index == -1 :
			return video_seems_to_be_corrupt_tuple

		video_stream_info = probe_info['streams'][video_stream_index]
		self.dimension = int(video_stream_info['width']), int(video_stream_info['height'])

		if self.dimension[0] < 10 or self.dimension[1] < 10 :
			return 'video dimension too small', 0
		if self.dimension[0] > 8000 or self.dimension[1] > 8000 :
			return 'video dimension too large', 0

		self.save_type = 'webm' #webm only for now

		#get filesize by seeking to end
		self.blob_file.seek(0, os.SEEK_END)
		self.filesize = BlobHandler.bytes_2_human_readable( self.blob_file.tell() )


		self.savename_utc = str(int(time.time()*1000000))
		#making sure filename doesn't exist already
		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		if os.path.isfile( os.path.join(self.save_path, savename_original) ) :
			rand = str(random.randint(1,1000000))
			self.savename_utc = '%s_%s' %(self.savename_utc, rand)

		# saving thumbnail now because that may reveal some video errors if it exists
		self.blob_file.seek(0)

		savename_tmp = 'tmp_%s.%s' %(self.savename_utc, 'jpg' )
		savepath_tmp = os.path.join(self.save_path, savename_tmp)

		self.blob_file.seek(0) #seek to zero since verify_image has seeked ahead already

		scale_option = 'scale=130:-1'
		if self.dimension[0] < self.dimension[1] :
			scale_option = 'scale=-1:130'

		proc = subprocess.Popen(['ffmpeg', '-v', 'quiet', '-i', '-', '-vframes', '1', '-filter:v', scale_option, savepath_tmp ], stdin=self.blob_file , stdout = subprocess.PIPE)
						
		std_out, std_err = proc.communicate()
		try :
			proc.terminate()
		except Exception as e :
			pass

		#check if thumbnail was actually saved
		if not os.path.isfile( savepath_tmp ) :
			return video_seems_to_be_corrupt_tuple

		return 1



	# returns 1 on success, tuple on failure
	def verify_image(self) :		
		try : 
			self.img = Image.open(self.blob_file.stream)
			self.img.verify()
			
			#exceptions can be thrown from here too because verify() doesn't do full load
			self.blob_file.seek(0)
			size_tuple = (130,130)
			
			#reopen again because of verify
			self.img = Image.open(self.blob_file.stream)			

			if self.img.mode == 'RGBA' :
				self.img_thumb = Image.new('RGBA', self.img.size, (220,220,220,255))

				#https://stackoverflow.com/questions/5324647/how-to-merge-a-transparent-png-image-with-another-image-using-pil				
				self.img_thumb.paste(self.img, (0,0), self.img)
				self.img_thumb = self.img_thumb.convert('RGB')
			else :
				self.img_thumb = self.img.convert('RGB')

			self.img_thumb.thumbnail(size_tuple, Image.ANTIALIAS )

		except Exception as e :	
			#print 'verify_image exception : %s' %e
			return 'image seems to be corrupt', -1

		
		self.dimension = self.img.size
		self.img_format = self.img.format
		

		if self.img_format != 'PNG' and self.img_format != 'JPEG' and self.img_format != 'GIF' :
			return 'image type not allowed', 0

		if self.dimension[0] < 10 or self.dimension[1] < 10 :
			return 'image dimension too small', 0
		if self.dimension[0] > 8000 or self.dimension[1] > 8000 :
			return 'image dimension too large', 0

		#setting variables
		self.savename_utc = str(int(time.time()*1000000))
		self.save_type = self.img_format.lower()
		if self.save_type == 'jpeg' :
			self.save_type = 'jpg'

		#making sure filename doesn't exist already
		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		if os.path.isfile( os.path.join(self.save_path, savename_original) ) :
			rand = str(random.randint(1,1000000))
			self.savename_utc = '%s_%s' %(self.savename_utc, rand)

		#saving as tmp_ here itself because to know exact file_size it has to be done.
		#it will be moved in save_image() call in next step
		self.filesize = BlobHandler.bytes_2_human_readable( self.save_tmp_image_and_return_img_size() )		

		return 1

	def save_tmp_image_and_return_img_size(self) :
		savename_tmp = 'tmp_%s.%s' %(self.savename_utc, self.save_type)
		savepath_tmp = os.path.join(self.save_path, savename_tmp)
		if self.img_format == 'GIF' :
			self.blob_file.seek(0)
			self.blob_file.save( savepath_tmp )
		else : 
			self.img.save( savepath_tmp, self.img_format )

		return os.stat(savepath_tmp).st_size



	def save(self) :
		if self.save_type == 'webm' :
			return self.save_video()
		else :
			return self.save_image()

	def save_video( self ) :		
		self.blob_file.seek(0)

		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		savepath_original = os.path.join(self.save_path, savename_original)

		#save original vid
		self.blob_file.save(savepath_original)

		#save thumbnail by renaming tmp_ file
		savename_tmp = 'tmp_%s.%s' %(self.savename_utc, 'jpg' )
		savepath_tmp = os.path.join(self.save_path, savename_tmp)

		savename_thumb = '%s_s.%s' %(self.savename_utc, 'jpg')
		savepath_thumb = os.path.join(self.save_path, savename_thumb)

		os.rename(savepath_tmp, savepath_thumb)


	def save_image( self ) :

		#save the thumbnail
		savename_thumb = '%s_s.jpg' %(self.savename_utc)
		self.img_thumb.save( os.path.join(self.save_path, savename_thumb), 'JPEG' )

		#save the original file (image) by renaming tmp_ file		
		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		savename_tmp = 'tmp_%s' %savename_original
		
		savepath_original = os.path.join(self.save_path, savename_original)
		savepath_tmp = os.path.join(self.save_path, savename_tmp)

		os.rename(savepath_tmp, savepath_original)

		return 1

	@staticmethod
	def bytes_2_human_readable(number_of_bytes):
		if number_of_bytes <= 0:
			raise ValueError("!!! numberOfBytes can't be smaller than 0 !!!")

		step_to_greater_unit = 1024.

		number_of_bytes = float(number_of_bytes)
		unit = 'bytes'

		if (number_of_bytes / step_to_greater_unit) >= 1:
			number_of_bytes /= step_to_greater_unit
			unit = 'KB'

		if (number_of_bytes / step_to_greater_unit) >= 1:
			number_of_bytes /= step_to_greater_unit
			unit = 'MB'

		precision = 1
		number_of_bytes = round(number_of_bytes, precision)

		return '%s%s' %(number_of_bytes, unit)
		


	def __del__(self):
		if self.blob_file :
			self.blob_file.close()
			
			if hasattr(self, 'savename_utc') : #'savename_utc' in self : 

				if self.save_type == 'webm' :
					savename_tmp = 'tmp_%s.%s' %(self.savename_utc, 'jpg') #is thumbnail in case of video
				else :
					savename_tmp = 'tmp_%s.%s' %(self.savename_utc, self.save_type)

				savepath_tmp = os.path.join(self.save_path, savename_tmp)

				#delete tmp file if it exists 
				if os.path.isfile(savepath_tmp) :
					os.remove(savepath_tmp)




