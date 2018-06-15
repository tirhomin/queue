(function() {
    
  // The width and height of the captured photo. We will set the
  // width to the value defined here, but the height will be
  // calculated based on the aspect ratio of the input stream.
  var PAUSE = false;
  var width = 400;    // We will scale the photo width to this
  var height = 0;     // This will be computed based on the input stream
  
  var IMAGELIST = new Array();

  function zip_and_download(){
    var zip = new JSZip();
    var arrlen = IMAGELIST.length;
    for (var idx = 0; idx < arrlen; idx++) {
    //for (var nimage in IMAGELIST) {
      zip.file("image"+idx+".jpg",IMAGELIST[idx], {base64:true});
    }
    //zip.file("smile.jpg", bdata, {base64: true});
    zip.generateAsync({type:"blob"})
    .then(function(content) {
        // see FileSaver.js
        saveAs(content, "garbage-data.zip");
    });
  }

  // |streaming| indicates whether or not we're currently streaming
  // video from the camera. Obviously, we start at false.

  var streaming = false;

  // The various HTML elements we need to configure or control. These
  // will be set by the startup() function.

  var video = null;
  var canvas = null;
  var photo = null;
  var startbutton = null;
  var LOCK = false; 
  var OUTSTANDING_FRAMES = 0;
  //TODO, note, LOCK is just a temporary hack to wait on async calls
  //so that essentially we are pretending to be synchronous;
  //in the longer term, we will run async + buffer and sort the
  //buffer as new frames come in so that things are a little more fluid
  //and faster

  function starthandler(e){
    IMAGELIST.length=0;
    video.play();
    PAUSE=false; LOCK = false; 
    startbtn = document.getElementById('START');
    startbtn.style.textDecoration='underline';
    stopbtn = document.getElementById('STOP');
    stopbtn.style.textDecoration='none';

    console.log('starthandler clicked');
  }
  function stophandler(e){
    video.pause();
    PAUSE = true;
    startbtn = document.getElementById('START');
    startbtn.style.textDecoration='none';
    stopbtn = document.getElementById('STOP');
    stopbtn.style.textDecoration='underline';
    console.log('stophandler clicked');
  }

  function downloadhandler(e){
    zip_and_download();
  }

  function setbinempty(){
    // everything will be handled server-side
    $.get( "/emptybin", function( data ) {});
  }

  function sendform(event){
    //send new settings to server
      event.preventDefault();
      $.ajax({
          type: 'POST',
          url: $("#settingsform").attr("action"),
          data: $("#settingsform").serialize(), 
          success: function(response) { },
        });
        $('#changemsg').fadeIn(1500);
        $('#changemsg').fadeOut(1500);
      }

  function startup() {
    document.getElementById('setbinempty').addEventListener('click', setbinempty, false);    
    document.getElementById('settings').addEventListener('click', sendform, false);    

    document.getElementById('START').addEventListener('click', starthandler, false);    
    document.getElementById('STOP').addEventListener('click', stophandler, false);
    document.getElementById('DOWNLOAD').addEventListener('click', downloadhandler, false);

    video = document.getElementById('video');
    canvas = document.getElementById('canvas');
    photo = document.getElementById('photo');
    startbutton = document.getElementById('startbutton');
    /*
    navigator.getMedia =  navigator.mediaDevices.getUserMedia;
    navigator.getMedia({video: true,audio: false},
      function(stream) {
        if (navigator.getUserMedia) {video.mozSrcObject = stream;}
        else {
          var vendorURL = window.URL || window.webkitURL;
          video.src = vendorURL.createObjectURL(stream);
        }
        video.play();
      },
      function(err) {console.log("An error occured! " + err);}
    );
    */
    navigator.mediaDevices.getUserMedia({ video: true, audio: false })
    .then(stream => video.srcObject = stream)
    .catch(e => console.log(e.name + ": "+ e.message));
    video.play();
      //-------------------------------
    video.addEventListener('canplay', function(ev){
      if (!streaming) {
        height = video.videoHeight / (video.videoWidth/width);     
        // Firefox currently has a bug where the height can't be read from
        // the video, so we will make assumptions if this happens.
        if (isNaN(height)) {height = width / (4/3);}
        video.setAttribute('width', width);
        video.setAttribute('height', height);
        canvas.setAttribute('width', width);
        canvas.setAttribute('height', height);
        streaming = true;
      }
    }, false);

    window.setInterval(function(){takepicture();},50)
    //note, code is currently synchronous, 100ms will
    //probably only be hit by east coast US users, otherwise
    //network latency means they wont have heard back on last request in
    //the 100ms


    clearphoto();
  }//END OF STARTUP FUNCTION

  // Fill the photo with an indication that none has been captured.
  // perhaps unnecessary now and can probably be deleted
  function clearphoto() {
    var context = canvas.getContext('2d');
    context.fillStyle = "#AAA";
    context.fillRect(0, 0, canvas.width, canvas.height);
  }
  
  // SEND IMAGE TO SERVER, GET RESPONSE IMAGE, DISPLAY IMAGE
  function sendPic(blob) {
        if(!LOCK && OUTSTANDING_FRAMES<3){
            //console.log('sending pic');
            OUTSTANDING_FRAMES += 1;
            if (OUTSTANDING_FRAMES >= 3){LOCK = true;}
            var data = new FormData();
            data.append("imagefile", blob, ("camera.png"));
            var oReq = new XMLHttpRequest();
            oReq.open("POST", "/data");
            oReq.send(data);
            oReq.onload = function(oEvent) {
                if (oReq.status == 200) {
                    //console.log("Uploaded");
                    //console.log(oReq.response);
                    OUTSTANDING_FRAMES -= 1;
                    LOCK = false;
                    //pause is down here so that we decrement the counter when we receive the frame,
                    //but dont update the window so it stays "paused"
                    if(PAUSE){return 0;}
                    else{
                      //HANDLE INCOMING PHOTO
                      photo.setAttribute('src', oReq.response);
                      //formatting stuff, server expects this format for now
                      var base64PrefixLength = ('data:image/jpeg;base64,').length;
                      var bdata = oReq.response.slice(base64PrefixLength);
                      
                      //add image to list, which will be zipped up as individual images when user clicks 'download'
                      IMAGELIST.push(bdata);

                    }
                } else {
                    //console.log("Error " + oReq.status + " occurred uploading your file.");
                    LOCK = false;
                }
            };

        }
        else{
          //console.log('locked');
        }
    }

  // TAKE A PHOTO FROM WEBCAM; 
  // SEND WEBCAM IMAGE TO SERVER;
  // WAIT FOR RESPONSE WITH A PROCESSED IMAGE;
  // UPDATE CANVAS WITH THAT IMAGE
  // IF NO PHOTO WAS CAPTURED, CLEAR THE FRAME TO SHOW USER IT IS FROZEN / WEBCAM FAILURE
  function takepicture() {
    if(PAUSE){console.log('doing nothing while paused'); return 0;}
    else{
        console.log('not paused, proceeding');
    }
    var context = canvas.getContext('2d');
    if (width && height) {
      canvas.width = width;
      canvas.height = height;
      context.drawImage(video, 0, 0, width, height);
    
      //formatting stuff, server expects this format for now
      var iformat = 'image/jpeg';
      var data = canvas.toDataURL(iformat);
      var base64PrefixLength = ('data:'+iformat+';base64,').length;
      var bdata = data.slice(base64PrefixLength);
      
      var blob = new Blob([bdata,], {type: iformat});
      sendPic(blob);

    } else {
      clearphoto();
    }
  }

  window.addEventListener('load', startup, false);



})();
