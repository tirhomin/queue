# queue
queue service time and wait time estimation

source video for examples: https://www.youtube.com/watch?v=M56Ps6C7guU

code based in part on 
https://github.com/marvis/pytorch-yolo3/tree/python3

which itself is based on work from

https://pjreddie.com/darknet/yolo/

To run, you'll need to download https://pjreddie.com/media/files/yolov3.weights and place it in the `marvis3` directory

(I would commit it here, but it is a few hundred megabytes)

requirements include scikit-learn, pytorch, flask, opencv, matplotlib, pillow, and youtube-dl

for background task processing, rq and and redis are required

To install all of those, it's recommended you use miniconda as it makes configuring opencv FAR easier on all platforms.

This is available from https://conda.io/miniconda.html

I can provide an updated requirements.txt file so you can "pip install -r requirements.txt" to make the installation process painless,
however I don't have time this evening, so please just email if that's desired and I will provide it.

Aside from python modules, redis-server is also required for background task processing (e.g. to process videos in the background without
stopping webpages from loading, etc). It is a trivial change to disable rq scheduling, you would simply comment out lines 59-61 of `vproc.py`
and then uncomment line 62. That would be it, aside from commenting out the import at the top of the file, then RQ would no longer be required.

