#!/usr/bin/env python

import bpy, subprocess, os, json, io, fcntl, time
from bpy.types import Operator
from bpy.props import *
from ..functions import *

class refreshNumAvailableServers(Operator):
    """Attempt to connect to all servers through host server""" # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.refresh_num_available_servers"          # unique identifier for buttons and menu items to reference.
    bl_label   = "Refresh Available Servers"                    # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}                           # enable undo for the operator.

    def checkNumAvailServers(self):
        scn = bpy.context.scene
        command = "ssh -T -x " + bpy.props.hostServerLogin + " 'python " + scn.tempFilePath + "blender_task -H --hosts_file " + scn.tempFilePath + "servers.txt'"
        process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
        return process

    def updateAvailServerInfo(self):
        scn = bpy.context.scene

        line1 = self.process.stdout.readline().decode('ASCII').replace("\\n", "")
        line2 = self.process.stdout.readline().decode('ASCII').replace("\\n", "")
        available = json.loads(line1.replace("'", "\""))
        offline = json.loads(line2.replace("'", "\""))

        bpy.types.Scene.availableServers = StringProperty(name = "Available Servers")
        bpy.types.Scene.offlineServers = StringProperty(name = "Offline Servers")

        scn['availableServers'] = available
        scn['offlineServers'] = offline
        for a in bpy.context.screen.areas:
            a.tag_redraw()

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.cancel(context)
            self.report({'INFO'}, "Render process cancelled")
            print("Process cancelled")
            return {'CANCELLED'}

        if event.type == 'TIMER':
            self.process.poll()

            if self.process.returncode != 0 and self.process.returncode != None:

                # if error message available, print in Info window and define errorMessage string
                if self.process.stderr != None:
                    errorMessage = "Error message available in terminal/Info window."
                    for line in self.process.stderr.readlines():
                        self.report({'WARNING'}, str(line, 'utf-8').replace("\n",""))
                else:
                    errorMessage = "No error message to print."

                self.report({'ERROR'}, "Process " + str(self.state-1) + " gave return code " + str(self.process.returncode) + ". " + errorMessage)
                return{'FINISHED'}

            if self.process.returncode != None:
                print("Process " + str(self.state) + " finished! (return code: " + str(self.process.returncode) + ")\n")

                # check the number of available servers through the host
                if(self.state == 1):
                    print("Running 'checkNumAvailServers' function...")
                    self.process = self.checkNumAvailServers()
                    self.state += 1
                    return{'PASS_THROUGH'}

                elif(self.state == 2):
                    self.updateAvailServerInfo()
                    self.report({'INFO'}, "Refresh process completed")
                    return{'FINISHED'}
                else:
                    self.report({'ERROR'}, "ERROR: Current state not recognized.")
                    return{'FINISHED'}

        return{'PASS_THROUGH'}

    def execute(self, context):
        scn = context.scene
        writeServersFile(bpy.props.servers, scn.serverGroups)

        # verify user input for tempFilePath string
        scn.tempFilePath.replace(" ", "_")
        if scn.tempFilePath[-1] != "/":
            scn.tempFilePath = scn.tempFilePath + "/"

        # create timer for modal
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)

        # start initial process
        print("Copying project files...")
        self.process = copyFiles()
        self.state   = 1  # initializes state for modal

        self.report({'INFO'}, "Refreshing available servers...")

        return{'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.process.kill()

class sendFrame(Operator):
    """Render current frame on remote servers"""            # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.render_frame_on_servers"            # unique identifier for buttons and menu items to reference.
    bl_label   = "Render Current Frame"                     # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}                       # enable undo for the operator.


    def modal(self, context, event):
        if event.type in {'ESC'} and not(self.alreadyCalled):
            if self.state == 3:
                self.alreadyCalled = True
                self.process.kill()
                self.report({'INFO'}, "Render process cancelled. Fetching frames...")
                print("Process cancelled")
                setRenderStatus("image", "Cancelled")
            else:
                self.cancel(context)
                self.report({'INFO'}, "Render process cancelled")
                print("Process cancelled")
                setRenderStatus("image", "Cancelled")
                return {'CANCELLED'}

        if self.process.stdout and self.state == 3:
            flags = fcntl.fcntl(self.process.stdout, fcntl.F_GETFL) # get current stdout flags
            fcntl.fcntl(self.process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            try:
                print(read(self.process.stdout.fileno(), 1024))
            except:
                pass
        #     self.stdout = self.process.stdout.readlines()
        #     for line in self.stdout:
        #         line = line.decode('ASCII').replace("\\n", "")[:-1]
        #         self.finishedFrames += line.count("has been copied back from hostname")
        #         print(self.finishedFrames)

        if event.type == 'TIMER':
            self.process.poll()

            if self.process.returncode != None:
                # handle unidentified errors
                if self.process.returncode > 1:
                    if self.alreadyCalled:
                        self.report({'INFO'}, "Process cancelled - No rendered frames found.")
                    else:
                        setRenderStatus("image", "ERROR")

                        # if error message available, print in Info window and define errorMessage string
                        if self.process.stderr != None:
                            errorMessage = "Error message available in terminal/Info window."
                            for line in self.process.stderr.readlines():
                                self.report({'WARNING'}, str(line, 'utf-8').replace("\n",""))
                        else:
                            errorMessage = "No error message to print."

                        # define self.errorSource string
                        if not(self.state == 3):
                            self.errorSource = "Process " + str(self.state-1)
                        else:
                            self.errorSource = "blender_task"

                        self.report({'ERROR'}, self.errorSource + " gave return code " + str(self.process.returncode) + ". " + errorMessage)
                    return{'FINISHED'}

                # handle and report errors for 'blender_task' process
                elif self.process.returncode == 1 and self.state == 3:
                    if self.process.stderr:
                        self.stderr = self.process.stderr.readlines()
                        print("\nERRORS:")
                        for line in self.stderr:
                            line = line.decode('ASCII').replace("\\n", "")[:-1]
                            self.report({'ERROR'}, "blender_task error: '" + line + "'")
                            print("blender_task error: '" + line + "'")
                            sys.stderr.write(line)
                        errorMsg = self.stderr[-1].decode('ASCII')
                        try:
                            self.numFailedFrames = int(errorMsg[18:-5])
                        except:
                            sys.stderr.write("Couldn't read last line of process output as integer")

                print("Process " + str(self.state) + " finished! (return code: " + str(self.process.returncode) + ")\n")

                # copy files to host server
                if(self.state == 1):
                    print("Copying files to host server...")
                    self.process = copyFiles()
                    self.state += 1
                    return{'PASS_THROUGH'}

                # start render process at current frame
                elif(self.state == 2):
                    self.process = renderFrames("[" + str(self.curFrame) + "]", self.projectName, True)
                    self.state += 1
                    setRenderStatus("image", "Rendering...")
                    return{'PASS_THROUGH'}

                # get rendered frames from remote servers and archive old render files
                elif(self.state == 3):
                    print("Fetching render files...")
                    self.process = getFrames(self.projectName)
                    self.state += 1
                    if not(self.alreadyCalled):
                        setRenderStatus("image", "Finishing...")
                    return{'PASS_THROUGH'}

                elif(self.state == 4):
                    failedFramesString = ""
                    if(self.numFailedFrames > 0):
                        failedFramesString = " (failed for " + str(self.numFailedFrames) + " frames)"
                    if not(self.alreadyCalled):
                        setRenderStatus("image", "Complete!")
                        self.report({'INFO'}, "Render completed" + failedFramesString + "! View the rendered image in your UV/Image_Editor")
                    else:
                        setRenderStatus("image", "Partial completetion")
                        self.report({'INFO'}, "Render partially completed" + failedFramesString + " - View the rendered image in your UV/Image_Editor")
                    appendViewable("image")
                    return{'FINISHED'}
                else:
                    self.report({'ERROR'}, "ERROR: Current state not recognized.")
                    setRenderStatus("image", "ERROR")
                    return{'FINISHED'}

        return{'PASS_THROUGH'}

    def execute(self, context):
        self.projectName = bpy.path.display_name_from_filepath(bpy.data.filepath)
        scn = context.scene

        #for testing purposes only (saves unsaved file as 'unsaved_file.blend')
        if self.projectName == "":
            self.projectName = "unsaved_file"
            bpy.ops.wm.save_mainfile(filepath=scn.tempLocalDir + self.projectName + ".blend")

        # ensure no other image render processes are running
        if(getRenderStatus("image") in ["Rendering...", "Preparing files..."]):
            self.report({'WARNING'}, "Render in progress...")
            return{'FINISHED'}

        # ensure the job won't break the script
        jobValidityDict = jobIsValid("image", self.projectName)
        if jobValidityDict["errorType"] != None:
            self.report({jobValidityDict["errorType"]}, jobValidityDict["errorMessage"])
        else:
            self.report({'INFO'}, "Rendering current frame on " + str(len(scn['availableServers'])) + " servers.")
        if not jobValidityDict["valid"]:
            return{'FINISHED'}

        # verify user input for tempFilePath string
        scn.tempFilePath.replace(" ", "_")
        if scn.tempFilePath[-1] != "/":
            scn.tempFilePath = scn.tempFilePath + "/"

        # write out the servers file for remote servers
        writeServersFile(bpy.props.servers, scn.serverGroups)

        # create timer for modal
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)

        # start initial render process
        self.stdout = None
        self.stderr = None
        self.alreadyCalled = False
        self.numFailedFrames = 0
        self.finishedFrames = 0
        self.curFrame = context.scene.frame_current
        self.process = copyProjectFile(self.projectName)
        self.state   = 1  # initializes state for modal

        setRenderStatus("image", "Preparing files...")

        return{'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.process.kill()

class sendAnimation(Operator):
    """Render animation on remote servers"""            # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.render_animation_on_servers"    # unique identifier for buttons and menu items to reference.
    bl_label   = "Render Animation"   # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}                   # enable undo for the operator.

    def modal(self, context, event):
        scn = context.scene

        if event.type in {'ESC'} and not(self.alreadyCalled):
            if self.state == 3:
                self.alreadyCalled = True
                self.process.kill()
                self.report({'INFO'}, "Render process cancelled. Fetching frames...")
                print("Process cancelled")
                setRenderStatus("animation", "Cancelled")
            else:
                self.cancel(context)
                self.report({'INFO'}, "Render process cancelled")
                print("Process cancelled")
                setRenderStatus("animation", "Cancelled")
                return {'CANCELLED'}


        if event.type == 'TIMER':
            self.process.poll()

            if self.process.returncode != None:
                # handle unidentified errors
                if self.process.returncode > 1:
                    if self.alreadyCalled:
                        self.report({'INFO'}, "Process cancelled - No rendered frames found.")
                    else:
                        setRenderStatus("animation", "ERROR")

                        # if error message available, print in Info window and define errorMessage string
                        if self.process.stderr != None:
                            errorMessage = "Error message available in terminal/Info window."
                            for line in self.process.stderr.readlines():
                                self.report({'WARNING'}, str(line, 'utf-8').replace("\n",""))
                        else:
                            errorMessage = "No error message to print."

                        # define self.errorSource string
                        if not(self.state == 3):
                            self.errorSource = "Process " + str(self.state-1)
                        else:
                            self.errorSource = "blender_task"

                        self.report({'ERROR'}, self.errorSource + " gave return code " + str(self.process.returncode) + ". " + errorMessage)
                    return{'FINISHED'}

                # handle and report errors for 'blender_task' process
                elif self.process.returncode == 1 and self.state == 3:
                    if self.process.stderr:
                        self.stderr = self.process.stderr.readlines()
                        print("\nERRORS:")
                        for line in self.stderr:
                            line = line.decode('ASCII').replace("\\n", "")[:-1]
                            self.report({'ERROR'}, "blender_task error: '" + line + "'")
                            print("blender_task error: '" + line + "'")
                            sys.stderr.write(line)
                        errorMsg = self.stderr[-1].decode('ASCII')
                        try:
                            self.numFailedFrames = int(errorMsg[18:-5])
                        except:
                            sys.stderr.write("Couldn't read last line of process output as integer")

                print("Process " + str(self.state) + " finished! (return code: " + str(self.process.returncode) + ")\n")

                # copy files to host server
                if(self.state == 1):
                    print("Copying files to host server...")
                    self.process = copyFiles()
                    self.state += 1
                    return{'PASS_THROUGH'}

                # start render process from the defined start and end frames
                elif(self.state == 2):
                    if scn.frameRanges == "":
                        self.frameRangesDict = {"string":"[[" + str(context.scene.frame_start) + "," + str(context.scene.frame_end) + "]]"}
                    else:
                        self.frameRangesDict = buildFrameRangesString(scn.frameRanges)
                        if not self.frameRangesDict["valid"]:
                            self.report({'ERROR'}, "ERROR: Invalid frame ranges given.")
                            setRenderStatus("animation", "ERROR")
                            return{'FINISHED'}
                    self.process = renderFrames(str(expandFrames(json.loads(self.frameRangesDict["string"]))), self.projectName, False)
                    setRenderStatus("animation", "Rendering...")
                    self.state += 1
                    return{'PASS_THROUGH'}

                # get rendered frames from remote servers and archive old render files
                elif(self.state == 3):
                    print("Fetching render files...")
                    self.process = getFrames(self.projectName)
                    if not(self.alreadyCalled):
                        setRenderStatus("animation", "Finishing...")
                    self.state +=1
                    return{'PASS_THROUGH'}

                elif(self.state == 4):
                    failedFramesString = ""
                    if(self.numFailedFrames > 0):
                        failedFramesString = " (failed for " + str(self.numFailedFrames) + " frames)"
                    missingFrames = listMissingFiles(self.projectName, self.frameRangesDict["string"])
                    if len(missingFrames) > 0:
                        self.report({'WARNING'}, "Missing Files: ")
                        self.report({'WARNING'}, missingFrames)
                    if not(self.alreadyCalled):
                        self.report({'INFO'}, "Render completed" + failedFramesString + "! View the rendered animation in '//render/'")
                        setRenderStatus("animation", "Complete!")
                    else:
                        self.report({'INFO'}, "Render partially completed - View rendered frames in '//render/'")
                    appendViewable("animation")
                    return{'FINISHED'}
                else:
                    self.report({'ERROR'}, "ERROR: Current state not recognized.")
                    setRenderStatus("animation", "ERROR")
                    return{'FINISHED'}

        return{'PASS_THROUGH'}

    def execute(self, context):# ensure no other animation render processes are running
        self.projectName = bpy.path.display_name_from_filepath(bpy.data.filepath)
        scn = context.scene

        #for testing purposes only (saves unsaved file as 'unsaved_file.blend')
        if self.projectName == "":
            self.projectName = "unsaved_file"
            bpy.ops.wm.save_mainfile(filepath=scn.tempLocalDir + self.projectName + ".blend")

        if(getRenderStatus("animation") in ["Rendering...","Preparing files..."]):
            self.report({'WARNING'}, "Render in progress...")
            return{'FINISHED'}

        # ensure the job won't break the script
        jobValidityDict = jobIsValid("animation", self.projectName)
        if jobValidityDict["errorType"] != None:
            self.report({jobValidityDict["errorType"]}, jobValidityDict["errorMessage"])
        else:
            self.report({'INFO'}, "Rendering current frame on " + str(len(scn['availableServers'])) + " servers.")
        if not jobValidityDict["valid"]:
            return{'FINISHED'}

        # verify user input for tempFilePath string
        scn.tempFilePath.replace(" ", "_")
        if scn.tempFilePath[-1] != "/":
            scn.tempFilePath = scn.tempFilePath + "/"

        # write out the servers file for remote servers
        writeServersFile(bpy.props.servers, scn.serverGroups)

        # create timer for modal
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, context.window)
        wm.modal_handler_add(self)

        # start initial render process
        self.stdout = None
        self.stderr = None
        self.alreadyCalled = False
        self.numFailedFrames = 0
        self.startFrame = context.scene.frame_start
        self.endFrame   = context.scene.frame_end
        self.numFrames  = str(int(scn.frame_end) - int(scn.frame_start))
        self.process    = copyProjectFile(self.projectName)
        self.state      = 1   # initializes state for modal

        self.report({'INFO'}, "Rendering animation on " + str(len(scn['availableServers'])) + " servers.")
        setRenderStatus("animation", "Preparing files...")

        return{'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.process.kill()

class openRenderedImageInUI(Operator):
    """Open rendered image"""                                       # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.open_rendered_image"                            # unique identifier for buttons and menu items to reference.
    bl_label   = "Open Rendered Image"    # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}                                   # enable undo for the operator.

    def execute(self, context):
        self.projectName = bpy.path.display_name_from_filepath(bpy.data.filepath)
        # open rendered image
        context.area.type = 'IMAGE_EDITOR'
        averaged_image_filepath = bpy.path.abspath("//") + "render-dump/" + self.projectName + "_average.tga"
        bpy.ops.image.open(filepath=averaged_image_filepath)
        bpy.ops.image.reload()

        return{'FINISHED'}

class openRenderedAnimationInUI(Operator):
    """Open rendered animation"""                 # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.open_rendered_animation"  # unique identifier for buttons and menu items to reference.
    bl_label   = "Open Rendered Animation"        # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}             # enable undo for the operator.


    def execute(self, context):
        self.frameRangesDict = buildFrameRangesString(context.scene.frameRanges)
        self.projectName = bpy.path.display_name_from_filepath(bpy.data.filepath)
        # open rendered image
        context.area.type = 'CLIP_EDITOR'
        image_sequence_filepath = bpy.path.abspath("//") + "render-dump/"
        if context.scene.frameRanges == "":
            fs = context.scene.frame_start
        else:
            if self.frameRangesDict["valid"]:
                fr = json.loads(self.frameRangesDict["string"])[0]
                if type(fr) == list:
                    fs = fr[0]
                else:
                    fs = fr
            else:
                self.report({'ERROR'}, "ERROR: Invalid frame ranges given.")
                return{'FINISHED'}

        image_filename = self.projectName + "_%04d.tga" % (fs)
        print("Opening frame: " + image_filename)
        bpy.ops.clip.open(directory=image_sequence_filepath, files=[{"name":image_filename}])
        bpy.ops.clip.reload()

        return{'FINISHED'}

class editRemoteServersDict(Operator):
    """Edit the remote servers dictionary in a text editor"""                       # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.edit_servers_dict"                                          # unique identifier for buttons and menu items to reference.
    bl_label   = "Edit Remote Servers"                                              # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}                                               # enable undo for the operator.

    def execute(self, context):
        context.area.type = 'TEXT_EDITOR'
        try:
            libraryServersPath = os.path.join(getLibraryPath(), "servers")
            bpy.ops.text.open(filepath=os.path.join(libraryServersPath, "remoteServers.txt"))
            self.report({'INFO'}, "Opened 'remoteServers.txt'")
            bpy.props.requiredFileRead = True
        except:
            self.report({'ERROR'}, "ERROR: Could not open 'remoteServers.txt'. If the problem persists, try reinstalling the add-on.")
        return{'FINISHED'}

class restartRemoteServers(Operator):
    """Restart active remote servers group"""   # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.restart_remote_servers" # unique identifier for buttons and menu items to reference.
    bl_label   = "Restart Remote Servers"       # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}           # enable undo for the operator.

    # def restartServers(self, scn):
    #     # for security reasons, read password in from external file on local machine
    #     f = open("/Users/cgear13/loginValue.txt", "r")
    #     encodedPassword = f.readline()[:-1]
    #
    #     # decode password from 'loginValue.txt'
    #     decodedPassword = ""
    #     for i in range(len(encodedPassword)):
    #         decodedPassword += chr(ord(encodedPassword[i])-2)
    #
    #     # build and execute curl command
    #     if(scn.serverGroups == "All Servers"):
    #         serversToRestart = "all"
    #     else:
    #         serversToRestart = "lab=" + scn.serverGroups
    #     curlCommand = "curl --user cgearhar:" + decodedPassword + " -X GET -H 'Content-type: application/json' -H 'Accept: application/json' 'http://fog.cse.taylor.edu/lab-resource/restart?" + serversToRestart + "&os=linux&fork=" + str(len(bpy.props.servers[scn.serverGroups])) + "'"
    #     sshCurlCommand = "ssh " + bpy.props.hostServerLogin + ":'" + curlCommand + "'"
    #     process = subprocess.Popen(sshCurlCommand, stdout=subprocess.PIPE, shell=True)
    #     return process
    #
    # def modal(self, context, event):
    #     scn = context.scene
    #
    #     if event.type == 'TIMER':
    #         self.process.poll()
    #
    #         if self.process.returncode != None and self.process.returncode > 1:
                # if self.process.stderr != None:
                #     errorMessage = "Error message available in terminal/Info window."
                #     for line in self.process.stderr.readlines():
                #         self.report({'WARNING'}, str(line, 'utf-8').replace("\n",""))
                # else:
                #     errorMessage = "No error message to print."
                # self.report({'ERROR'}, "Process " + str(self.state-1) + " gave return code " + str(self.process.returncode) + ". " + errorMessage)
                # return{'FINISHED'}
    #         if self.process.returncode != None:
    #             self.report({'INFO'}, "Remote servers have been restarted")
    #             return{'FINISHED'}
    #
    #     return{'PASS_THROUGH'}

    def execute(self, context):
        # # create timer for modal
        # wm = context.window_manager
        # self._timer = wm.event_timer_add(0.1, context.window)
        # wm.modal_handler_add(self)
        #
        # # start initial process
        # self.process = self.restartServers(context.scene)
        # self.state   = 1
        # self.report({'INFO'}, "Restarting remote servers")
        #
        # return{'RUNNING_MODAL'}
        return{'FINISHED'}

class listFiles(Operator):
    """List the files missing from the render-dump folder"""   # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.list_files"     # unique identifier for buttons and menu items to reference.
    bl_label   = "List Files"           # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}   # enable undo for the operator.

    def execute(self, context):
        scn = context.scene
        if scn.nameOutputFiles != "":
            self.fileName = scn.nameOutputFiles
        else:
            self.fileName = bpy.path.display_name_from_filepath(bpy.data.filepath)

        if scn.frameRanges == "":
            self.frameRangesDict = {"string":"[[" + str(context.scene.frame_start) + "," + str(context.scene.frame_end) + "]]"}
        else:
            self.frameRangesDict = buildFrameRangesString(scn.frameRanges)
            if not self.frameRangesDict["valid"]:
                self.report({'ERROR'}, "ERROR: Invalid frame ranges given.")
                return{'FINISHED'}

        # list all missing files from start frame to end frame in render-dump location
        missingFrames = listMissingFiles(self.fileName, self.frameRangesDict["string"])
        self.report({'INFO'}, "Missing frames: " + missingFrames)

        return{'FINISHED'}

class setToMissingFrames(Operator):
    """Set frame range to frames missing from the render-dump folder"""   # blender will use this as a tooltip for menu items and buttons.
    bl_idname  = "scene.set_to_missing_frames"  # unique identifier for buttons and menu items to reference.
    bl_label   = "Set to Missing Frames"        # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}           # enable undo for the operator.

    def execute(self, context):
        scn = context.scene

        # set the name of the files to the project name or custom name defined in advanced settings
        if scn.nameOutputFiles != "":
            self.fileName = scn.nameOutputFiles
        else:
            self.fileName = bpy.path.display_name_from_filepath(bpy.data.filepath)

        if scn.frameRanges == "":
            self.frameRangesDict = {"string":"[[" + str(context.scene.frame_start) + "," + str(context.scene.frame_end) + "]]"}
        else:
            self.frameRangesDict = buildFrameRangesString(scn.frameRanges)
            if not self.frameRangesDict["valid"]:
                self.report({'ERROR'}, "ERROR: Invalid frame ranges given.")
                return{'FINISHED'}

        # list all missing files from start frame to end frame in render-dump location
        scn.frameRanges = listMissingFiles(self.fileName, self.frameRangesDict["string"])

        return{'FINISHED'}
