import cv2
import numpy as np
import os
import json
import datetime
import subprocess
from subprocess import Popen, PIPE
from pathlib import Path
import threading
import time

# Json file to store hit timings
jsonFile = "HitData.json"

# Scan files in this directory.
# Vod filenames must be their twitch ID with optional prefix tags in brackets, e.x. [2-5-24][st=10443]2054414193.mp4
# where the date is 2-5-24, the file starts at 10,443 seconds into the vod, and the vod id is 2054414193
vidDir = "Vods"

# How many video files to process at once.
# Set this as high as possible without running out of memory
maxThreads = 6

# if false, will append to HitData.json
clearOldHitData = False

# if true, will start scanning after the most recent hit in HitData.json (useful for continuing after a crash)
continueAfterLastHit = True

# minimum time in seconds between hits
minSpacing = 60

# scan every x frames
frameStep = 10

# rect in normalized coordinates [xmin, ymin, xmax, ymax]
healthbarRect = [0.082929, 0.045627, 0.159724, 0.050658]

# red healthbar rgb thresholds
redLower = np.array([6, 6, 50], dtype="uint8")
redUpper = np.array([50, 50, 110], dtype="uint8")

# yellow healthbar rgb thresholds
yellowLower = np.array([10, 90, 100], dtype="uint8")
yellowUpper = np.array([50, 160, 190], dtype="uint8")

# directory to save hit clips
clipDir = "HitClips"

twitchDownloader = "TwitchDownloaderCLI/TwitchDownloaderCLI.exe"

# how many seconds before and after the hit to clip
preTime = 3
postTime = 3


def SaveData(data):
    with open(jsonFile, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent = 4)

def ProcessVid(vidFile, data):
    startTime = 0
    if continueAfterLastHit and (vidFile in data) and len(data[vidFile]) > 0:
        # start after last detected hit
        startTime = max(data[vidFile]) + 1

    cap = cv2.VideoCapture(vidDir + "/" + vidFile)
    if startTime > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, startTime * 1000)
    w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    vidLength = cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS)
    rect = [round(healthbarRect[0] * w), round(healthbarRect[1] * h), round(healthbarRect[2] * w), round(healthbarRect[3] * h)]

    lastHitTime = -minSpacing
    oldimage = []
    hitTimes = []

    print("PROCESSING: " + vidFile)
    progress = 0
    while(1):
        for i in range(frameStep):
            frame_exists, curr_frame = cap.read()
        if frame_exists:
            time = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            # crop to healthbar rect
            image = curr_frame[rect[1]:rect[3], rect[0]:rect[2]]
            if len(oldimage) > 0:
                # detect yellow in current frame and red in previous frame
                yellowMask = cv2.inRange(image, yellowLower, yellowUpper)
                redMask = cv2.inRange(oldimage, redLower, redUpper)
                # detect change from yellow to red
                delta = cv2.bitwise_and(redMask, yellowMask)
                deltaCount = cv2.sumElems(delta)[0]
                if((deltaCount > 255 * 10) and (time > lastHitTime + minSpacing)):
                    lastHitTime = time
                    hitTimes.append(time)
                    data[vidFile] = hitTimes
                    SaveData(data)
                    print('Hit detected in ' + vidFile + ' at ' + str(datetime.timedelta(seconds=time)))
            oldimage = image
            newProgress = round(time / vidLength * 100)
            if newProgress != progress:
                progress = newProgress
                print(vidFile + '   ' + str(progress) + '%')
        else:
            break

    # release the captured frame 
    cap.release() 

    data[vidFile] = hitTimes
    SaveData(data)
    print("DONE PROCESSING " + vidFile)

def ParseStartTime(clipName):
    if('[st=' in clipName):
        numStart = clipName.find('[st=') + 4
        numEnd = clipName.find(']', numStart)
        num = int(clipName[numStart:numEnd])
        print(num)
        return num
    else:
        return 0

def FindHits():
    vidFiles = os.listdir(vidDir)
    data = {}
    if not clearOldHitData and os.path.isfile(jsonFile):
        f = open(jsonFile)
        data = json.load(f)
    activeThreads = []
    for vidFile in vidFiles:
        while len(activeThreads) >= maxThreads:
            activeThreads = [t for t in activeThreads if t.is_alive()]
            time.sleep(0.1)

        t = threading.Thread(target=ProcessVid, args=(vidFile, data))
        activeThreads.append(t)
        t.start()

    for t in activeThreads:
        t.join()

    SaveData(data)

def ClipHits():
    f = open(jsonFile)
    data = json.load(f)

    for vod in data:
        id = Path(vod).stem
        startTime = ParseStartTime(id)
        if(']' in id):
            # remove tags, isolate id
            id = id[id.rindex(']')+1:]
        print('Starting downloads for ' + vod)
        hitCounter = 0
        downloads = []
        for t in data[vod]:
            call = twitchDownloader + ' videodownload --id ' + id + ' -b ' + str(round(startTime + t - preTime)) + ' -e ' + str(round(startTime + t + postTime)) + ' -o ' + clipDir + '/' + Path(vod).stem + '_' + str(hitCounter) + '.mp4'
            d = subprocess.Popen(call, stdout=PIPE, stderr=PIPE)
            downloads.append(d)
            hitCounter += 1
        for d in downloads:
            d.wait()
        print("Finished downloading clips for " + vod)

#FindHits()
ClipHits()