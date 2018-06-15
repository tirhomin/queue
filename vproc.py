'''process video to find various pieces of information about people in the queue, such as wait time'''
#deep learning
import torch, numpy
from marvis3 import darknet# import Darknet
from marvis3 import utils

#image and video handling
from PIL import Image, ImageDraw
import cv2, math, colorsys, time
from sklearn.cluster import KMeans

#dominant color computation
import matplotlib.pyplot as plt
from scipy.stats import itemfreq

#youtube download
import os, youtube_dl, pickle #pickle to store reports

#background job processing queue
from rq import Queue
from redis import Redis

MAXFRAMES = 90
VIDEO_SPEED = 1
NTHFRAME = 3 #remember to divide distance travelled by this to find the real distance per frame
FINALSIZE = (640,360)
FINALWIDTH = FINALSIZE[0]
FINALHEIGHT = FINALSIZE[1]
# max distance allowed for a person to travel to indicate theyre in line, not just walking past
# also useful for stripping outliers and algorithm misses
MAXDIST = FINALWIDTH // 6 
recognizer = darknet.Darknet('marvis3/cfg/yolov3.cfg')
recognizer.print_network()
recognizer.load_weights('marvis3/yolov3.weights')

image_class_names = {20:'marvis3/data/voc.names', 80:'marvis3/data/coco.names'}
class_names = utils.load_class_names(image_class_names[recognizer.num_classes])

def video_exists(mvars):
    '''check if video is already downloaded'''
    #if any of this is true, video doesnt exist
    if not os.path.exists('static/video/%s.%s' %(mvars['id'], mvars['ext'])):
        return False
    if not os.path.exists('static/analyzed/%s/1.jpg' %mvars['id']) \
        or \
        not os.path.exists('static/analyzed/%s/analysis.pickle' %mvars['id']):
        return False
    #---video exists
    return True

def proc_link(link, video_speed=1, video_scale=15):
    '''add video to job queue for processing in background'''
    mvars = get_duration(link)
    mvars['video_speed'] = video_speed
    mvars['video_scale'] = video_scale #how many meters wide is the viewport -- guess from people height on camera? good idea.
    if video_exists(mvars):
        return True
    if mvars['duration'] < 10*60: #dont do vids longer than 10 mins
        redis_conn = Redis()
        q = Queue(connection=redis_conn)  # no args implies the default queue
        job = q.enqueue(get_and_proc_video, mvars)
        #get_and_proc_video(mvars)
        return True
    else:
        return False

def get_dominant_hue(image):
    '''takes RGB image and returns dominant hue (0-1 range, i.e. a percentage of the 360 degree hue wheel), 
        e.g. returns .97 meaning 349.2 degrees, 0.97*360 = 349.2'''
    #make image list of pixels rather than matrix
    sim = image.reshape((image.shape[0] * image.shape[1], 3))
    clt = KMeans(n_clusters = 3)
    clt.fit(sim)

    numLabels = numpy.arange(0, len(numpy.unique(clt.labels_)) + 1)
    hist, _ = numpy.histogram(clt.labels_, bins = numLabels)
    hist = hist.astype("float")
    hist /= hist.sum()

    d = {hist[n]:clt.cluster_centers_[n] for n in range(len(hist))}
    return d[max(d.keys())] #return (h,s,v)

def analyze_frame(img, boxes, class_names=None, last_frameinfo=None):
    width, height = img.shape[1], img.shape[0]
    #people is list of X pos and dominant hue
    people = list()
    #boxes.sort()
    avg_distances = list()
    queue_length = 0
    for i in range(len(boxes)):
        box = boxes[i]
        if len(box) > 6 and class_names:
            #only detect people, not cars, handbags, dogs, etc
            if class_names[box[6]] != 'person':continue
            queue_length+=1
            x1 = int((box[0] - box[2]/2.0) * width)
            y1 = int((box[1] - box[3]/2.0) * height)
            x2 = int((box[0] + box[2]/2.0) * width)
            y2 = int((box[1] + box[3]/2.0) * height)

            #top Y of person to middle Y will be just their shirt, then we subtract a seventh so we also discard the head
            #so that we can measure primarily the HSV of their shirt, for later comparing the hue
            midpoint_y = y1+(y2-y1)//2
            midpoint_x = x1+(x2-x1)//2
            shirt = img[y1+midpoint_y//7:midpoint_y,x1:x2]

            try:
                hsv = get_dominant_hue(shirt) #hsv range is [0-179, 0-255, 0-255]
                if hsv[2]<50:continue
                img = cv2.putText(img, 'person', (x1,y2-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (64, 255, 220))#, 2)#16px font
                img = cv2.rectangle(img, (x1,y1), (x2,y2), hsv, 2) #draw rect around person
                img = cv2.rectangle(img, (x1,y1), (x1+(x2-x1)//2, y1+16), hsv, -1) #draw shirt color rect
                people.append((x1, list(hsv)))
                
                NEAREST = None
                if last_frameinfo:#len(last_frameinfos)==2:
                    last_people = last_frameinfo#last_frameinfos[1] ##[frame=0 or 1][people=1]
                    for p in last_people:
                        lf_x = p[0]
                        #if last position is in front of us, ignore, as people will be moving forward not backward
                        if lf_x>x1: continue
                        hue_dist = abs(hsv[0] - (179 - p[1][0]))
                        light_dist = abs(hsv[2] - (255 - p[1][2]))
                        x_dist = abs(x1-lf_x)
                        #36 is 20% of 180 max hue, and 72 is 20% of 255 max lightness
                        if (x_dist < MAXDIST) and (hue_dist<50) and (light_dist<100):
                            if NEAREST and x_dist < NEAREST[0]:
                                #found a nearer match, flag it
                                NEAREST = (x_dist, lf_x)
                            else:
                                #no match yet seen, set as nd
                                NEAREST = (x_dist, lf_x)
                    if isinstance(NEAREST,tuple):
                        #found a match, draw boxes:
                        avg_distances.append(NEAREST[0])
                        img = cv2.rectangle(img, (x1,y1), (x1+10, y1+10), (0,255,255), -1) #draw tracking indicator
                        img = cv2.line(img, (NEAREST[1], midpoint_y), (x1, midpoint_y), hsv, 4)

                #NOTE:
                #this expects a horizontally moving queue, if video is overhead and the queue is moving "up" the frame,
                #then we can instead rotate the video so that its again moving left to right
                #of if it is moving right to left, flip the image horizontally
            except Exception as e:
                print('err: ', str(e))
        avg_dist = 0
        if avg_distances:
            avg_dist = sum(avg_distances) / len(avg_distances) / NTHFRAME
    return (img, people, avg_dist, queue_length)


def load_image_into_numpy_array(image):
    '''convert PIL image data into numpy array for manipulation by TensorFlow'''
    (im_width, im_height) = image.size
    return numpy.array(image.getdata()).reshape((im_height, im_width, 3)).astype(numpy.uint8)

def process_video(video_id, video_ext, framelimit=None):
    '''given filepath, process video and output files to that path'''
    cap = cv2.VideoCapture('static/video/%s.%s' %(video_id, video_ext))
    framecount=0
    saved_frame=0
    last_frameinfo = None 
    QUEUE_LENGTHS = list() #list of the length of the queue in each frame
    FRAME_DISTANCES = list() #list of average distance travelled per person per frame
    try: os.mkdir('static/analyzed/%s' %video_id)
    except: pass
    
    while(cap.isOpened()):
        ret, frame = cap.read()
        if not ret: break

        #if we're only analyzing first N frames of video, break if we exceed that limit:
        if MAXFRAMES and framecount>=MAXFRAMES:break
        framecount+=1         
        t=time.time()
        if not framecount %NTHFRAME: 
            print('adding frame: ',framecount)
            sized = cv2.resize(frame, (recognizer.width, recognizer.height))
            bboxes = utils.do_detect(recognizer, sized, 0.5, 0.4, False)#dont use cuda

            viewsized = cv2.resize(frame, FINALSIZE)
            draw_img, last_frameinfo, avg_dist, queue_length = analyze_frame(viewsized, bboxes,
                                                                             class_names=class_names, 
                                                                             last_frameinfo = last_frameinfo)
            FRAME_DISTANCES.append(avg_dist)
            QUEUE_LENGTHS.append(queue_length)
            
            saved_frame+=1       
            cv2.imwrite('static/analyzed/%s/%d.jpg' %(video_id,saved_frame), draw_img)
            cv2.imwrite('static/analyzed/%s/thumb-%d.jpg' %(video_id,saved_frame), cv2.resize(draw_img, (192,108)))

            print('frametime:',time.time()-t)
    cap.release()
    avg_dist_per_frame = sum(FRAME_DISTANCES) / len(FRAME_DISTANCES)
    motion_per_frame = avg_dist_per_frame / FINALWIDTH
    avg_queue_length = sum(QUEUE_LENGTHS) / len(QUEUE_LENGTHS)
    return motion_per_frame, avg_queue_length
############################################
def get_duration(link=None):
    ydl = youtube_dl.YoutubeDL({'outtmpl': 'static/video/%(id)s.%(ext)s'})
    with ydl:
        result = ydl.extract_info(link,download=False)
        if 'entries' in result:
            video_id = result['entries'][0]['id']#playlist
            duration = result['entries'][0]['duration']
            ext = result['entries'][0]['ext']
        else:
            video_id = result['id']    #video
            duration = result['duration']
            ext = result['ext']
    return {'id':video_id, 'duration':duration,'ext':ext, 'link':link}

def get_and_proc_video(mvars):
    link = mvars['link']
    if not os.path.exists('static/video/%s.%s' %(mvars['id'], mvars['ext'])):
        print('downloading')
        ydl = youtube_dl.YoutubeDL({'outtmpl': 'static/video/%(id)s.%(ext)s'})
        with ydl: 
            ydl.download([link])
    else:
        print('already downloaded')
    #if not os.path.exists('static/analyzed/%s/1.jpg' %mvars['id']):
    if True:#process it anyway
        try: os.mkdir('static/analyzed/%s' %mvars['id'])
        except: pass

        print('processing')
        report = {'serve_time':0, 'wait_time':0, 'avg_dist':0, 'queue_length':0, 'done':False}
        with open("static/analyzed/%s/analysis.pickle" %mvars['id'],'wb') as f:pickle.dump(report,f)

        motion_per_frame, queue_length = process_video(mvars['id'], mvars['ext'])
        video_speed = mvars['video_speed']#time lapse speed factor
        video_scale = mvars['video_scale'] #meters wide viewport
        factor = motion_per_frame * video_scale / video_speed / NTHFRAME * 30#fps
        service_time = factor * video_scale
        wait_time = service_time * queue_length
        report = {'service_time':service_time, 'wait_time':wait_time, 'queue_length':queue_length, 'done':True}
        with open("static/analyzed/%s/analysis.pickle" %mvars['id'],'wb') as f:
            pickle.dump(report,f)

    else:
        print('already processed')
    return 1