#/usr/bin/python

import subprocess
import sys
import os, numpy, PIL
from PIL import Image

print "running 'sendToRenderFarm.py'..."

# Enter testing mode for default values
testing   = False
verbose   = False
recursive = False




# DEFAULTS
defaultBasePath       = "/Users/cgear13/Documents/filmmaking/files_for_render_farm/"
# create ssh redirect here so I can use this code remotely
defaultHostServer     = "cgearhar@asahel.cse.taylor.edu"
defaultServerFilePath = "/tmp/cgearhar/"
dumpLocationBase      = defaultBasePath + "renderedFrames/"

# GLOBAL VARIABLES
hostServer     = ""
projectName    = ""
projectPath    = ""
serverFilePath = ""
frameStart     = ""
frameEnd       = ""















# SETUP FUNCTIONS

def handleArgs():
    global testing
    global verbose
    global recursive

    args = ""
    for i in range(1, len(sys.argv)):
        curArg = sys.argv[-1]
        if (curArg[:1] != "-" or ("t" not in curArg and "v" not in curArg and "r" not in curArg)):
            print "'" + curArg + "' not allowed as an argument."
            print ""
            print "Accepted arguments:"
            print ">  -v  => run in verbose mode. In verbose mode, rsync files are called with -v, and blender_task.py (written by nwhite, stored on asahel) is called with -v."
            print ">  -t  => run in testing mode. In testing mode, nearly all inputs have non-destructive, non-taxing default values set for carriage return, and '_testFile.blend' is opened automatically."
            print ">  -r  => run in recursive mode. In recursive mode, getNewProjectFile searches through ~/filmmaking/, so that all respective '*.blend' files are available"
            print ""
            sys.exit()
        args += sys.argv.pop()

    if "t" in args:
        testing = True
    if "v" in args:
        verbose = True
    if "r" in args:
        recursive = True




def setProjectFileOnOpen():
    global serverFilePath

    if testing:
        projectName = "_testFile.blend"
        serverFilePath = defaultServerFilePath + projectName[:-6] + "/"
        print ""
        return projectName

    else:
        return ""




def setServer():
    # set server to default server
    print "hostServer = "  + defaultHostServer + "\n"
    return defaultHostServer















# HELPERS

def getFrameStart():
    global frameStart
    while True:
        frameStart = raw_input("frame start => ")
        if testing and frameStart == "":
            frameStart = 1
        elif frameStart == "m":
            runMainMenu()
            sys.exit()
        try:
            frameStart = int(frameStart)
            break;
        except ValueError:
            print "Whoops! That was no valid number. Try again..."
    return frameStart




def getFrameEnd():
    global frameEnd
    while True:
        frameEnd = raw_input("frame end => ")
        if testing and frameEnd == "":
            frameEnd = 25
        elif frameEnd == "m":
            runMainMenu()
            sys.exit()
        try:
            frameEnd = int(frameEnd)
            break;
        except ValueError:
            print "Whoops! That was no valid number. Try again..."
    return frameEnd




def getSampleSize():
    while True:
        samplesIn = raw_input("Render Samples => ")
        if samplesIn == "":
            if testing:
                samplesIn = 50
            else:
                samplesIn = 100
        elif samplesIn == "m":
            runMainMenu()
            sys.exit()
        try:
            samplesIn = int(samplesIn)
            break;
        except ValueError:
            print "Whoops! That was no valid number. Try again..."
    return samplesIn




def formatter(start, end):
    return '{}-{}'.format(start, end)




def re_range(lst):
    n = len(lst)
    result = []
    scan = 0
    while n - scan > 2:
        step = lst[scan + 1] - lst[scan]
        if (lst[scan + 2] - lst[scan + 1] != step or step > 1):
            result.append(str(lst[scan]))
            scan += 1
            continue

        for j in range(scan+2, n-1):
            if lst[j+1] - lst[j] != step:
                result.append(formatter(lst[scan], lst[j]))
                scan = j+1
                break
        else:
            result.append(formatter(lst[scan], lst[-1]))
            return ','.join(result)

    if n - scan == 1:
        result.append(str(lst[scan]))
    elif n - scan == 2:
        result.append(','.join(map(str, lst[scan:])))

    return ','.join(result)




def verifyFramesPresent(dumpLocation, boundsSpecified):

    # save list of render files to renderFilesList via the file 'renderFilesList.txt'
    subprocess.call("cd " + dumpLocation + ";ls | grep -v '.txt' > renderFilesList.txt", shell=True)
    f = open(dumpLocation + "renderFilesList.txt", "r")
    renderFilesList = f.read().splitlines()
    f.close() # close the file
    subprocess.call("cd " + dumpLocation + "; rm renderFilesList.txt", shell=True) # delete file we just created (no longer needed)
    if len(renderFilesList) == 0:
        print "no files present."
        return

    # NEEDS OPTIMIZATION, and eventually logic improvement. Checks if any files have seeds; if so, don't check if files present
    seeded = False
    for curFile in renderFilesList:
        if "_seed-" in curFile:
            seeded = True

    # trim the render file strings in renderFilesList to integers (e.g. 'demo_0001.png' becomes 1)
    for idx,string in enumerate(renderFilesList):
        try:
            renderFilesList[idx] = int(string.split('.')[0][-4:])
        except:
            print "Whoops! There was a problem verifying the frames; it seems a frame was present that didn't conform to to the '*####.*' pattern, where # is any valid number 0-9."
            return

    # init skippedImages
    skippedFrames = []

    # append all frames excluded from renderFilesList to skippedFrames
    if not boundsSpecified:
        # append to skippedFrames any number excluded from list in its own bounds
        currentFrame = renderFilesList[0]
        for renderFrame in renderFilesList:
            while renderFrame != currentFrame:
                skippedFrames.append(currentFrame)
                currentFrame += 1
            currentFrame += 1
    elif seeded:
        print "TEMP ALERT: There are seeded frames in the dumpLocation. Please rewrite this secion of code in VerifyFramesPresent() to account for such files"
        print "frames not verified"
        return
    else:
        # if frame starts line up, this for loop is skipped
        for i in range(frameStart,renderFilesList[0]):
            skippedFrames.append(i)

        # append to skippedFrames any number excluded from list in its own bounds
        currentFrame = renderFilesList[0]
        for renderFrame in renderFilesList:
            while renderFrame != currentFrame:
                skippedFrames.append(currentFrame)
                currentFrame += 1
            currentFrame += 1

        # if frame ends line up, this for loop is skipped
        for i in range(renderFilesList[-1] + 1,frameEnd):
            skippedFrames.append(i)
    skippedFrameRanges = re_range(skippedFrames).split(",")
    if len(skippedFrames) == 0:
        print "all render files seem to be present!"
    else:
        print "Missing frames: [",
        for frames in skippedFrameRanges:
            print str(frames) + ",",
        print "\b\b ]"




def chooseProjectFile(filesList):
    global projectName

    if len(filesList) == 1:
        userChoice = raw_input("Press ENTER to use project file '" + filesList[0] + "' => ")
        while ( userChoice != '' and userChoice != "m" ):
            userChoice = raw_input("Whoops! Press ENTER to confirm ('m' for main menu) => ")
        if userChoice == "m":
            runMainMenu()
            sys.exit()
        else:
            return 0

    elif len(filesList) > 1:
        # print out list of files in defaultBasePath to screen
        if recursive:
            print "files in '~/filmmaking/*'"
        else:
            print "files in '~/filmmaking/files_for_render_farm/'"
        for i,item in enumerate(filesList):
            print str(i+1) + ":  " + item

        # prompt user to choose a file
        print ""

        while True:
            userChoice = raw_input("USE FILE => ")
            if ( testing and userChoice == "" ):
                userChoice = 1
            try:
                userChoice = int(userChoice)
                break;
            except ValueError:
                print "Whoops! That was no valid number. Try again..."
        while(userChoice > len(filesList) or userChoice == 0):
            print "Whoops! Index out of bounds. Try again..."
            while True:
                userChoice = raw_input("USE FILE (default=1) => ")
                if ( testing and userChoice == "" ):
                    userChoice = 1
                try:
                    userChoice = int(userChoice)
                    break;
                except ValueError:
                    print "Whoops! That was no valid number. Try again..."

        return userChoice-1
















# PRINCIPAL FUNCTIONS

def setProjectFile():
    global serverFilePath

    # save list of files in defaultBasePath to 'filesList.txt' and readlines into variable filesList
    subprocess.call("cd " + defaultBasePath + ";ls *.blend | grep -v '_testFile.blend' > filesList.txt", shell=True)
    f = open(defaultBasePath + "filesList.txt", "r")
    filesList = f.read().splitlines()
    # close 'filesList.txt' and delete it
    f.close()
    subprocess.call("cd " + defaultBasePath + "; rm filesList.txt", shell=True)
    if ( len(filesList) == 0 ):
        print "    please create dynamic link to your project file with the following command:"
        print "        =>  ln -s path/to/project.blend ~/filmmaking/files_for_render_farm/\n"
        print "run 'render' again once you've done this.\n"
        sys.exit()
    chosenIndex = chooseProjectFile(filesList)

    # set user choice to projectName
    projectName    = filesList[chosenIndex]
    if " " in projectName:
        if verbose:
            print "changing ' ' characters to '_' in source file"
        subprocess.call("cd " + defaultBasePath + ";mv " + projectName.replace(" ", "\ ") + " " + projectName.replace(" ", "_"), shell=True)
        projectName = projectName.replace(" ", "_")
    serverFilePath = defaultServerFilePath + projectName[:-6] + "/"

    print "using file '" + projectName + "'\n"
    return projectName




def averageFrames():
    print "running averageFrames()... (currently only supports '.png' and '.tga')"
    allfiles=os.listdir(dumpLocationBase + projectName[:-6] + "/")
    imlist=[filename for filename in allfiles if  (filename[-4:] in [".tga",".TGA"] and filename[-5] != "e" and filename[:-10] == projectName[:-6] + "_seed-")]
    for i in range(len(imlist)):
        imlist[i] = dumpLocationBase + projectName[:-6] + "/" + imlist[i]

    if len(imlist) == 0:
        print "There were no image files to average..."
        return;

    # Assuming all images are the same size, get dimensions of first image
    print "Averaging the following images:"
    for image in imlist:
        print image
    w,h=Image.open(imlist[0]).size
    N=len(imlist)

    # Create a numpy array of floats to store the average (assume RGB images)
    arr=numpy.zeros((h,w,3),numpy.float)

    # Build up average pixel intensities, casting each image as an array of floats
    for im in imlist:
        # load image
        imarr=numpy.array(Image.open(im),dtype=numpy.float)
        try:
            arr=arr+imarr/N
        except:
            print "It seems your image may have an alpha value. This is not currently supported by this script; please either add support for alpha channels to the averageFrames() function, or try another image."

    # Round values in array and cast as 8-bit integer
    arr=numpy.array(numpy.round(arr),dtype=numpy.uint8)

    # Print details
    print "Averaged successfully!"

    # Generate, save and preview final image
    out=Image.fromarray(arr,mode="RGB")
    print "saving averaged image..."
    out.save(dumpLocationBase + projectName[:-6] + "/" + projectName[:-6] + "_average.tga")






def setProjectFileRecursive():
    global serverFilePath
    global projectPath

    # save list of files in '~/filmmaking/' to 'defaultBasePath/filesPathsList.txt' and readlines into variable filesList
    subprocess.call("cd ~/filmmaking; find . -type f \( -name '*.blend' ! -name '_testFile.blend' \)  > " + defaultBasePath + "filesPathsList.txt", shell=True)
    f = open(defaultBasePath + "filesPathsList.txt", "r")
    filesPathsList = f.read().splitlines()
    filesList = []
    pathsList = []
    # close 'filesPathsList.txt' and delete it
    f.close()
    subprocess.call("cd " + defaultBasePath + "; rm filesPathsList.txt", shell=True)
    if ( len(filesPathsList) == 0 ):
        print "    please create dynamic link to your project file with the following command:"
        print "        =>  ln -s path/to/project.blend ~/filmmaking/files_for_render_farm/\n"
        print "run 'render' again once you've done this.\n"
        sys.exit()

    for i in range(len(filesPathsList)):
        filesPathsList[i] = "~/filmmaking/" + filesPathsList[i][2:]
        tempSplitPath = filesPathsList[i].split("/")
        filesList.append(tempSplitPath.pop())
        pathsList.append("")
        for item in tempSplitPath:
            pathsList[i] = pathsList[i] + item + "/"

    #change global variable for projectPath
    chosenIndex = chooseProjectFile(filesList)
    # set user choice to projectName

    projectName    = filesList[chosenIndex]
    projectPath    = pathsList[chosenIndex].replace(" ", "\ ")
    if " " in projectName:
        if verbose:
            print "changing ' ' characters to '_' in source file"
        subprocess.call("cd " + projectPath + ";mv " + projectName.replace(" ", "\ ") + " " + projectName.replace(" ", "_"), shell=True)
        projectName = projectName.replace(" ", "_")

    subprocess.call("cd " + defaultBasePath + "; ln -s " + projectPath + projectName  + " ./" + projectName,shell=True)
    serverFilePath = defaultServerFilePath + projectName[:-6] + "/"

    print "using file '" + projectName + "'\n"
    return projectName




def sendToHostServer():
    userChoice = "b"
    getFrameStart()
    getFrameEnd()
    #sampleSize = getSampleSize()
    numFrames = frameEnd - frameStart + 1
    userChoice = raw_input("Press ENTER to render " + str(numFrames) + " frames of '" + projectName[:-6] + "'? => ") # at " + str(sampleSize) + " samples => ")
    while ( userChoice != 'm' and userChoice != '' ):
        userChoice = raw_input("Whoops! Press ENTER to confirm ('m' for main menu) => ")
    if userChoice == 'm':
        return False
    print ""

    print "verifying remote directory..."
    subprocess.call("ssh " + hostServer + " 'mkdir -p " + serverFilePath + ";'", shell=True)

    # set up project folder in remote server
    print "copying blender project files..."

    subprocess.call("rsync -a --copy-links '" + defaultBasePath + projectName + "' '" + hostServer + ":" + serverFilePath + projectName + "'", shell=True)
    print "rsync -v -a --copy-links '" + defaultBasePath + projectName + "' '" + hostServer + ":" + serverFilePath + projectName + "'"
    print ""

    # run blender command to render given range from the remote server
    print "opening connection to " + hostServer + "..."
    subprocess.call("ssh " + hostServer + " 'blender_task.py -n " + projectName[:-6] + " -s " + str(frameStart) + " -e " + str(frameEnd) + "'", shell=True)

    return True




def getRenderFiles():
    dumpLocation = dumpLocationBase + projectName[:-6] + "/"
    if verbose:
        print dumpLocation

    print "verifying local directory..."
    subprocess.call("mkdir -p " + dumpLocation + "backups/", shell=True)

    print "cleaning up local directory..."
    subprocess.call("find " + dumpLocation + ".. ! -name '" + projectName[:-6] + "' -empty -type d -delete", shell=True)
    subprocess.call("rsync --remove-source-files " + dumpLocation + "* " + dumpLocation + "backups/",shell=True)

    print "verifying remote directory..."
    if verbose:
        print "ssh " + hostServer + " 'mkdir -p " + serverFilePath + ";'"
    subprocess.call("ssh " + hostServer + " 'mkdir -p " + serverFilePath + ";'", shell=True)

    print "copying files from server...\n"
    subprocess.call("rsync --exclude='*.blend' '" + hostServer + ":" + serverFilePath + "*' '" + dumpLocation + "'",shell=True)

    print "verifying all render frames present",
    if ( frameStart != "" and frameEnd != "" ):
        print "(" + str(frameStart) + "-" + str(frameEnd) + ")"
        boundsSpecified = True
    else:
        print "(no start frame or end frame specified)"
        boundsSpecified = False
    verifyFramesPresent(dumpLocation, boundsSpecified)













# MAIN MENU

def runMainMenu():
    global projectName

    continueRunning = True
    while(continueRunning):
        subprocess.call("clear", shell=True)
        print "\nMAIN MENU",
        if verbose or testing or recursive:
            print " (mode:",
        if verbose:
            print "-v",
        if testing:
            print "-t",
        if recursive:
            print "-r",
        if verbose or testing or recursive:
            print "\b)",
        print ""
        print "(press 'm' to return to main menu at any time)\n"
        print "Menu options:"
        print "1.   n: newProjectFile"
        print "2.   s: sendToRenderFarm (DEFAULT)"
        print "3.   g: getRenderFiles"
        print "4.   a: averageFrames"
        print "5.   q: quit"
        if testing:
            print "6.   d: openDefaultFile"
        print ""
        if( projectName == "" ): print "no project file set."
        else:                    print "projectFile = " + projectName
        print ""
        menuSelection = raw_input("SELECT MENU OPTION => ")
        print ""
        if (menuSelection == "n" or menuSelection == "1"):
            print "running setProjectFile script...\n"
            if recursive:
                projectName = setProjectFileRecursive()
            else:
                projectName = setProjectFile()
            subprocess.call("clear", shell=True)
        elif (menuSelection == "s" or menuSelection == "" or menuSelection == "2" ):
            if projectName == "":
                projectName = setProjectFile()
            print "running sendToRenderFarm script..."
            if ( sendToHostServer() ):
                junk = raw_input("\nPress ENTER to get render files => ")
                while (junk != "" and junk != "m"):
                    junk = raw_input("\nWhoops! you entered '" + junk + "'. Press ENTER to continue => ")
                if junk == "":
                    print "\nrunning getRenderFiles script..."
                    getRenderFiles()
                    print ""
                    averageFrames()
                    junk = raw_input("\nprocess completed. Press enter for main menu...")
            subprocess.call("clear", shell=True)
        elif (menuSelection == "g" or menuSelection == "3" ):
            if projectName == "":
                projectName = setProjectFile()
            print "running getRenderFiles script..."
            getRenderFiles()
            junk = raw_input("\nprocess completed. Press enter for main menu...")
            subprocess.call("clear", shell=True)
        elif (menuSelection == "a" or menuSelection == "4" ):
            averageFrames()
            junk = raw_input("\nprocess completed. Press enter for main menu...")
            subprocess.call("clear", shell=True)
        elif (menuSelection == "q" or menuSelection == "5" ):
            continueRunning = False
        elif (testing and (menuSelection == "d" or menuSelection == "6") ):
            projectName = setProjectFileOnOpen()
        else:
            print "Whoops! Invalid input."















# MAIN

def main():
    global projectName
    global hostServer

    # if arguments were passed, handle them
    if len(sys.argv) > 1:
        handleArgs()

    # set up global variable "hostServer"
    hostServer = setServer()

    # for testing purposes for now... (in the future, it will automatically open last opened file)
    projectName = setProjectFileOnOpen()

    # open the main menu
    runMainMenu()

main()
