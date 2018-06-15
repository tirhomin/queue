from gevent import monkey; monkey.patch_all()
from gevent.pywsgi import WSGIServer

from flask import Flask, request, render_template
from PIL import Image, ImageOps
import threading, queue, time, pickle, vproc
import torchlib as nnlib
app = Flask(__name__)

import os
@app.route('/add', methods=['POST'])
def addurl():
    video_speed = int(request.form['video_speed'])
    video_scale = int(request.form['video_scale'])
    if not 'youtube' in request.form['url'].lower():
        msg= 'this is not a youtube URL, please provide a youtube url'
        return render_template('message.html',message=msg)
    else:
        state = vproc.proc_link('https://www.youtube.com/watch?v=M56Ps6C7guU', video_speed=video_speed, video_scale=video_scale)

    if state:
        msg= '''your video is being processed, and will be added to the site when this is complete -- 
                    this process may take several minutes, so please refresh the page after some time has elapsed to see if your video has been added yet.'''
    else:
        msg= 'this video is longer than 10 minutes, the current maximum allowed; a future version may allow longer videos.'

    return render_template('message.html',message=msg)

@app.route("/")
def home():
    '''main page / Web UI for webcam'''
    dirs = list(os.walk('static/analyzed'))
    ddict = {i[0].split('/')[-1]:len(i[2])//2 for i in dirs[1:]}
    print('ddict',ddict)
    if 'id' in request.args:
        chosen = request.args['id']
    else:
        chosen = list(ddict.keys())[0] if ddict else None
    if 'imageno' in request.args:
        imageno=request.args['imageno']
    else:
        imageno = 1

    report = {'serve_time':0, 'wait_time':0, 'avg_dist':0, 'queue_length':0, 'done':False}
    if chosen:
        with open("static/analyzed/M56Ps6C7guU/analysis.pickle",'rb') as f:
            report = pickle.load(f)
    print('report: ',report)
    return render_template('qmain.html', ddict=ddict, chosen=chosen, imageno=imageno, report=report)

#debug server which auto-reloads for live changes during development
#app.run(debug=True, port=8080, host='0.0.0.0')

#run the server with gevent to support multiple clients on AWS
server = WSGIServer(("0.0.0.0", 8080), app)
server.serve_forever()
