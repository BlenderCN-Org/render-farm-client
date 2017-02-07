#!/usr/bin/env python

import bpy, subprocess, os, sys
from .setupServerVars import *

def jobIsValid(jobType, classObject):
    """ verifies that the job is valid before sending it to the host server """

    # verify that project has been saved
    if classObject.projectName == "":
        jobValidityDict = {"valid":False, "errorType":"WARNING", "errorMessage":"RENDER FAILED: You have not saved your project file. Please save it before attempting to render."}

    # verify that project name contains no spaces
    elif " " in classObject.projectName:
        jobValidityDict = {"valid":False, "errorType":"ERROR", "errorMessage":"RENDER ABORTED: Please remove ' ' (spaces) from the project file name."}

    # verify that a camera exists in the scene
    elif bpy.context.scene.camera is None:
        jobValidityDict = {"valid":False, "errorType":"ERROR", "errorMessage":"RENDER FAILED: No camera in scene."}

    # verify image file format
    elif bpy.context.scene.render.image_settings.file_format in ["AVI_JPEG", "AVI_RAW", "FRAMESERVER", "H264", "FFMPEG", "THEORA", "QUICKTIME", "XVID"]:
        jobValidityDict = {"valid":False, "errorType":"ERROR", "errorMessage":"RENDER FAILED: Movie file formats not supported. Please choose an image file format in the 'Render > Output' panel"}

    # verify that sampling is high enough to provide expected results
    elif jobType == "image":
        if bpy.context.scene.cycles.progressive == "PATH":
            samples = bpy.context.scene.cycles.samples
            if bpy.context.scene.cycles.use_square_samples:
                samples = samples**2
            if samples < 10:
                jobValidityDict = {"valid":True, "errorType":"WARNING", "errorMessage":"RENDER ALERT: Render result may be inaccurate at {samples} samples. Try 10 or more samples for a more accurate render.".format(samples=str(samples))}
        elif bpy.context.scene.cycles.progressive == "BRANCHED_PATH":
            samples = bpy.context.scene.cycles.aa_samples
            if bpy.context.scene.cycles.use_square_samples:
                samples = samples**2
            if samples < 5:
                jobValidityDict = {"valid":True, "errorType":"WARNING", "errorMessage":"RENDER ALERT: Render result may be inaccurate at {samples} AA samples. Try 5 or more AA samples for a more accurate render.".format(samples=str(samples))}

    # else, the job is valid
    jobValidityDict = {"valid":True, "errorType":None, "errorMessage":None}

    # if error detected, report error in Blender UI
    if jobValidityDict["errorType"] != None:
        classObject.report({jobValidityDict["errorType"]}, jobValidityDict["errorMessage"])

    # if job is invalid, return false
    if not jobValidityDict["valid"]:
        return False

    # alert user that render job has started
    if jobType == "image":
        jobType = "current frame"
    classObject.report({"INFO"}, "Rendering {jobType} on {numAvailable} servers.".format(jobType=jobType, numAvailable=str(len(bpy.context.scene["availableServers"]))))

    # job is valid, return true
    return True

def getFrames(projectName):
    """ rsync rendered frames from host server to local machine """

    scn = bpy.context.scene
    basePath = bpy.path.abspath("//")
    dumpLocation = os.path.join(basePath, "render-dump")

    # move old render files to backup directory
    archiveRsyncCommand = "rsync -qx --rsync-path='mkdir -p {basePath}/backups/ && rsync' --remove-source-files --exclude='{projectName}_average.*' {dumpLocation}/* {dumpLocation}/backups/;".format(basePath=basePath, dumpLocation=dumpLocation, projectName=projectName)

    # rsync files from host server to local directory
    fetchRsyncCommand = "rsync -x --progress --remove-source-files --exclude='*.blend' -e 'ssh -T -o Compression=no -x' '{hostServerLogin}:{tempFilePath}{projectName}/results/*' '{dumpLocation}/';".format(hostServerLogin=bpy.props.hostServerLogin, tempFilePath=scn.tempFilePath, projectName=projectName, dumpLocation=dumpLocation)

    # run the above processes
    process = subprocess.Popen(archiveRsyncCommand + fetchRsyncCommand, stdout=subprocess.PIPE, shell=True)
    return process

def buildFrameRangesString(frameRanges):
    """ builds frame range list of lists/ints from user-entered frameRanges string """

    frameRangeList = frameRanges.replace(" ", "").split(",")
    newFrameRangeList = []
    invalidDict = {"valid":False, "string":None}
    for string in frameRangeList:
        try:
            newInt = int(string)
            newFrameRangeList.append(newInt)
        except:
            if "-" in string:
                newString = string.split("-")
                if len(newString) > 2:
                    return invalidDict
                try:
                    newInt1 = int(newString[0])
                    newInt2 = int(newString[1])
                    if newInt1 <= newInt2:
                        newFrameRangeList.append([newInt1, newInt2])
                    else:
                        return invalidDict
                except:
                    return invalidDict
            else:
                return invalidDict
    return {"valid":True, "string":str(newFrameRangeList).replace(" ", "")}

def copyProjectFile(projectName):
    """ copies project file from local machine to host server """

    scn = bpy.context.scene
    bpy.ops.file.pack_all()
    saveToPath = "{tempLocalDir}{projectName}.blend".format(tempLocalDir=scn.tempLocalDir, projectName=projectName)
    bpy.ops.wm.save_as_mainfile(filepath=saveToPath, copy=True)

    # copies blender project file to host server
    rsyncCommand = "rsync --copy-links --progress --rsync-path='mkdir -p {tempFilePath}{projectName}/toRemote/ && rsync' -qazx --include={projectName}.blend --exclude='*' -e 'ssh -T -o Compression=no -x' '{tempLocalDir}' '{hostServerLogin}:{tempFilePath}{projectName}/toRemote/'".format(tempFilePath=scn.tempFilePath, projectName=projectName, tempLocalDir=scn.tempLocalDir, hostServerLogin=bpy.props.hostServerLogin)
    process = subprocess.Popen(rsyncCommand, shell=True)
    return process

def copyFiles():
    """ copies necessary files to host server """
    scn = bpy.context.scene

    # write out the servers file for remote servers
    writeServersFile(bpy.props.servers, scn.serverGroups)

    # rsync setup files to host server ('servers.txt', 'blender_p.py', 'blender_task' module)
    rsyncCommand = "rsync -qax -e 'ssh -T -o Compression=no -x' --rsync-path='mkdir -p {tempFilePath} && rsync' '{to_host_server}/' '{username}:{tempFilePath}'".format(tempFilePath=scn.tempFilePath, to_host_server=os.path.join(getLibraryPath(), "to_host_server"), username=bpy.props.hostServerLogin)
    process = subprocess.Popen(rsyncCommand, stdout=subprocess.PIPE, shell=True)
    return process

def renderFrames(frameRange, projectName, averageFrames=False):
    """ calls 'blender_task' on host server """

    scn = bpy.context.scene
    extraFlags = ""

    # defines the name of the output files generated by 'blender_task'
    if scn.nameOutputFiles != "":
        extraFlags += " -O {nameOutputFiles}".format(nameOutputFiles=scn.nameOutputFiles)

    # if rendering one frame, set '-a' flag to alert blender_task that we want an averaged result
    if averageFrames:
        extraFlags += " -a"

    # defines the project path on the host server if specified
    if scn.tempFilePath == "":
        scn.tempFilePath = "/tmp/"

    # runs blender command to render given range from the remote server
    renderCommand = "ssh -T -x {hostServerLogin} 'python {tempFilePath}blender_task -v -p -n {projectName} -l {frameRange} --hosts_file {tempFilePath}servers.txt -R {tempFilePath} --connection_timeout {t} --max_server_load {maxServerLoad}{extraFlags}'".format(hostServerLogin=bpy.props.hostServerLogin, tempFilePath=scn.tempFilePath, projectName=projectName, frameRange=frameRange.replace(" ", ""), t=str(scn.timeout), maxServerLoad=str(scn.maxServerLoad), extraFlags=extraFlags)
    process = subprocess.Popen(renderCommand, stderr=subprocess.PIPE, shell=True)
    print("Process sent to remote servers!")
    return process

def setRenderStatus(key, status):
    bpy.context.scene.renderStatus[key] = status
    for a in bpy.context.screen.areas:
        a.tag_redraw()

def getRenderStatus(key):
    return bpy.context.scene.renderStatus[key]

def appendViewable(typeOfRender):
    if typeOfRender not in bpy.context.scene.renderType:
        bpy.context.scene.renderType.append(typeOfRender)

def removeViewable(typeOfRender):
    try:
        bpy.context.scene.renderType.remove(typeOfRender)
    except:
        return

def expandFrames(frame_range):
    """ Helper function takes frame range string and returns list with frame ranges expanded """

    frames = []
    for i in frame_range:
        if type(i) == list:
            frames += range(i[0], i[1]+1)
        elif type(i) == int:
            frames.append(i)
        else:
            sys.stderr.write("Unknown type in frames list")

    return list(set(frames))

def listMissingFiles(filename, frameRange):
    """ lists all missing files from local 'render-dump' directory """

    dumpFolder=os.path.join(bpy.path.abspath("//"), "render-dump")

    try:
        allFiles = os.listdir(dumpFolder)
    except:
        sys.stderr.write("Error listing directory {dumpFolder}/. The folder may not exist.".format(dumpFolder=dumpFolder))
        return ""
    imList = []
    for f in allFiles:
        if f[-11:-4] != "average" and "seed" not in f and f[:len(filename)] == filename:
            imList.append(int(f[len(filename)+1:len(filename)+5]))
    compList = expandFrames(json.loads(frameRange))

    # compare lists to determine which frames are missing from imlist
    missingF = [i for i in compList if i not in imList]

    # return the list of missing frames as string, omitting the open and close brackets
    return str(missingF)[1:-1]

def handleError(classObject, errorSource):
    # if error message available, print in Info window and define errorMessage string
    if classObject.process.stderr != None:
        errorMessage = "Error message available in terminal/Info window."
        for line in classObject.process.stderr.readlines():
            classObject.report({"WARNING"}, str(line, "utf-8").replace("\n", ""))
    else:
        errorMessage = "No error message to print."

    classObject.report({"ERROR"}, "{errorSource} gave return code {returnCode}. {errorMessage}".format(errorSource=errorSource,returnCode=str(classObject.process.returncode), errorMessage=errorMessage))

def handleBTError(classObject):
    if classObject.process.stderr:
        classObject.stderr = classObject.process.stderr.readlines()
        print("\nERRORS:")
        for line in classObject.stderr:
            line = line.decode("ASCII").replace("\\n", "")[:-1]
            errorMessage = "blender_task error: '{line}'".format(line=line)
            classObject.report({"ERROR"}, errorMessage)
            print(errorMessage)
            sys.stderr.write(line)
        errorMsg = classObject.stderr[-1].decode("ASCII")
        try:
            classObject.numFailedFrames = int(errorMsg[18:-5])
        except:
            sys.stderr.write("Couldn't read last line of process output as integer")

def setFrameRangesDict(classObject):
    scn = bpy.context.scene

    if scn.frameRanges == "":
        classObject.frameRangesDict = {"string":"[[{frameStart},{frameEnd}]]".format(frameStart=str(scn.frame_start), frameEnd=str(scn.frame_end))}
    else:
        classObject.frameRangesDict = buildFrameRangesString(scn.frameRanges)
        if not classObject.frameRangesDict["valid"]:
            classObject.report({"ERROR"}, "ERROR: Invalid frame ranges given.")
            return False
    return True

def getRenderDumpFolder():
    return os.path.join(bpy.path.abspath("//"), "render-dump")
