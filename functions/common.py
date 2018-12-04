# Copyright (C) 2018 Christopher Gearhart
# chris@bblanimation.com
# http://bblanimation.com/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# System imports
import random
import sys
import time
import os
import itertools
import operator
import traceback
import subprocess
from math import *

# Blender imports
import bpy
props = bpy.props


# https://github.com/CGCookie/retopoflow
def bversion():
    bversion = '%03d.%03d.%03d' % (bpy.app.version[0], bpy.app.version[1], bpy.app.version[2])
    return bversion


def getActiveContextInfo():
    scn = bpy.context.scene
    cm = scn.cmlist[scn.cmlist_index]
    n = cm.source_name
    return scn, cm, n


def stopWatch(text, value, precision=2):
    """From seconds to Days;Hours:Minutes;Seconds"""

    valueD = (((value/365)/24)/60)
    Days = int(valueD)

    valueH = (valueD-Days)*365
    Hours = int(valueH)

    valueM = (valueH - Hours)*24
    Minutes = int(valueM)

    valueS = (valueM - Minutes)*60
    Seconds = round(valueS, precision)

    outputString = str(text) + ": " + str(Days) + ";" + str(Hours) + ":" + str(Minutes) + ";" + str(Seconds)
    print(outputString)


def groupExists(groupName):
    """ check if group exists in blender's memory """

    groupExists = False
    for group in bpy.data.groups:
        if group.name == groupName:
            groupExists = True
    return groupExists


def getItemByID(collection, id):
    success = False
    for item in collection:
        if item.id == id:
            success = True
            break
    return item if success else None


def str_to_bool(s):
    if s == 'True':
        return True
    elif s == 'False':
        return False
    else:
        raise ValueError  # evil ValueError that doesn't tell you what the wrong value was


# def get_settings():
#     if not hasattr(get_settings, 'settings'):
#         addons = bpy.context.user_preferences.addons
#         folderpath = os.path.dirname(os.path.abspath(__file__))
#         while folderpath:
#             folderpath,foldername = os.path.split(folderpath)
#             if foldername in {'functions','addons'}: continue
#             if foldername in addons: break
#         else:
#             assert False, 'Could not find non-"lib" folder'
#         if not addons[foldername].preferences: return None
#         get_settings.settings = addons[foldername].preferences
#     return get_settings.settings


# USE EXAMPLE: idfun=(lambda x: x.lower()) so that it ignores case
# https://www.peterbe.com/plog/uniqifiers-benchmark
def uniquify(seq, idfun=None):
    # order preserving
    if idfun is None:
        def idfun(x):
            return x
    seen = {}
    result = []
    for item in seq:
        marker = idfun(item)
        # in old Python versions:
        # if seen.has_key(marker)
        # but in new ones:
        if marker in seen:
            continue
        seen[marker] = 1
        result.append(item)
    return result


def uniquify1(seq):
    # Not order preserving
    keys = {}
    for e in seq:
        keys[e] = 1
    return keys.keys()


def tag_redraw_areas(areaTypes=["ALL"]):
    areaTypes = confirmList(areaTypes)
    for area in bpy.context.screen.areas:
        for areaType in areaTypes:
            if areaType == "ALL" or area.type == areaType:
                area.tag_redraw()


def disableRelationshipLines():
    # disable relationship lines
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].show_relationship_lines = False


def drawBMesh(BMesh, name="drawnBMesh"):
    """ create mesh and object from bmesh """
    # note: neither are linked to the scene, yet, so they won't show in the 3d view
    m = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, m)

    scn = bpy.context.scene   # grab a reference to the scene
    scn.objects.link(obj)     # link new object to scene
    scn.objects.active = obj  # make new object active
    obj.select = True         # make new object selected (does not deselect other objects)
    BMesh.to_mesh(m)          # push bmesh data into m
    return obj


def copyAnimationData(source, target):
    if source.animation_data is None:
        return

    ad = source.animation_data

    properties = [p.identifier for p in ad.bl_rna.properties if not p.is_readonly]

    if target.animation_data is None:
        target.animation_data_create()
    ad2 = target.animation_data

    for prop in properties:
        setattr(ad2, prop, getattr(ad, prop))


class Suppressor(object):
    def __enter__(self):
        self.stdout = sys.stdout
        sys.stdout = self
    def __exit__(self, type, value, traceback):
        sys.stdout = self.stdout
        if type is not None:
            # Uncomment next line to do normal exception handling
            # raise
            pass
    def write(self, x):
        pass


def applyModifiers(obj, only=None, exclude=None, curFrame=None):
    hasArmature = False
    select(obj, active=obj)
    # apply modifiers
    for mod in obj.modifiers:
        # only = ["SUBSURF", "ARMATURE", "SOLIDIFY", "MIRROR", "ARRAY", "BEVEL", "BOOLEAN", "SKIN", "OCEAN", "FLUID_SIMULATION"]
        if (only is None or mod.type in only) and (exclude is None or mod.type not in exclude) and mod.show_viewport:
            if curFrame and mod.type in ["CLOTH", "SOFT_BODY", "ARMATURE"]:
                pass
            try:
                with Suppressor():
                    bpy.ops.object.modifier_apply(apply_as='DATA', modifier=mod.name)
            except:
                mod.show_viewport = False
            if mod.type == "ARMATURE" and not hasArmature and mod.show_viewport:
                hasArmature = True
    return hasArmature


# code from https://stackoverflow.com/questions/1518522/python-most-common-element-in-a-list
def most_common(L):
    # get an iterable of (item, iterable) pairs
    SL = sorted((x, i) for i, x in enumerate(L))
    # print 'SL:', SL
    groups = itertools.groupby(SL, key=operator.itemgetter(0))

    # auxiliary function to get "quality" for an item
    def _auxfun(g):
        item, iterable = g
        count = 0
        min_index = len(L)
        for _, where in iterable:
            count += 1
            min_index = min(min_index, where)
        # print 'item %r, count %r, minind %r' % (item, count, min_index)
        return count, -min_index

    # pick the highest-count/earliest item
    return max(groups, key=_auxfun)[0]


def confirmList(objList):
    """ if single object passed, convert to list """
    if type(objList) != list:
        objList = [objList]
    return objList


def insertKeyframes(objList, keyframeType, frame, interpolationMode='Default', idx=-1):
    """ insert key frames for given objects to given frames """
    objList = confirmList(objList)
    for obj in objList:
        obj.keyframe_insert(data_path=keyframeType, frame=frame)
        if interpolationMode == "Default":
            continue
        fcurves = []
        for i in range(3):  # increase if inserting keyframes for something that takes up more than three fcurves
            fc = obj.animation_data.action.fcurves.find(keyframeType, index=i)
            if fc is not None:
                fcurves.append(fc)
        for fcurve in fcurves:
            # for kf in fcurve.keyframe_points:
            kf = fcurve.keyframe_points[idx]
            kf.interpolation = interpolationMode


def setActiveScn(scn):
    for screen in bpy.data.screens:
        screen.scene = scn


def getLayersList(layerList):
    layerList = confirmList(layerList)
    newLayersList = []
    for i in range(20):
        newLayersList.append(i in layerList)
    return newLayersList


def setLayers(layers, scn=None):
    """ set active layers of scn w/o 'dag ZERO' error """
    assert len(layers) == 20
    if scn is None:
        scn = bpy.context.scene
    # set active scene (prevents dag ZERO errors)
    setActiveScn(scn)
    # set active layers of scn
    scn.layers = layers


def deselectAll():
    bpy.ops.object.select_all(action='DESELECT')


def selectAll():
    bpy.ops.object.select_all(action='SELECT')


def hide(objList):
    objList = confirmList(objList)
    for obj in objList:
        obj.hide = True


def unhide(objList):
    objList = confirmList(objList)
    for obj in objList:
        obj.hide = False


def select(objList=[], active=None, deselect=False, only=True, scene=None):
    """ selects objs in list and deselects the rest """
    if objList is None and active is None:
        deselectAll()
    objList = confirmList(objList)
    try:
        if not deselect:
            # deselect all if selection is exclusive
            if only and len(objList) > 0:
                deselectAll()
            # select objects in list
            for obj in objList:
                obj.select = True
        elif deselect:
            # deselect objects in list
            for obj in objList:
                obj.select = False

        # set active object
        if active:
            try:
                if scene is None:
                    scene = bpy.context.scene
                scene.objects.active = active
            except:
                print("argument passed to 'active' parameter not valid (" + str(active) + ")")
    except:
        return False
    return True


def delete(objList):
    objList = confirmList(objList)
    objs = bpy.data.objects
    for obj in objList:
        if obj is None:
            continue
        objs.remove(obj, True)


def checkEqual1(iterator):
    iterator = iter(iterator)
    try:
        first = next(iterator)
    except StopIteration:
        return True
    return all(first == rest for rest in iterator)


def checkEqual2(iterator):
   return len(set(iterator)) <= 1


def checkEqual3(lst):
   return lst[1:] == lst[:-1]
# The difference between the 3 versions are that:
#
# In checkEqual2 the content must be hashable.
# checkEqual1 and checkEqual2 can use any iterators, but checkEqual3 must take a sequence input, typically concrete containers like a list or tuple.
# checkEqual1 stops as soon as a difference is found.
# Since checkEqual1 contains more Python code, it is less efficient when many of the items are equal in the beginning.
# Since checkEqual2 and checkEqual3 always perform O(N) copying operations, they will take longer if most of your input will return False.
# checkEqual2 and checkEqual3 can't be easily changed to adopt to compare a is b instead of a == b.


def changeContext(context, areaType):
    """ Changes current context and returns previous area type """
    lastAreaType = context.area.type
    context.area.type = areaType
    return lastAreaType


def getLibraryPath():
    """ returns full path to module directory """
    functionsPath = os.path.dirname(os.path.abspath(__file__))
    libraryPath = functionsPath[:-10]
    if not os.path.exists(libraryPath):
        raise NameError("Did not find addon from path {}".format(libraryPath))
    return libraryPath


# https://github.com/CGCookie/retopoflow
def showErrorMessage(message, wrap=80):
    if not message or wrap == 0:
        return
    lines = message.splitlines()
    nlines = []
    for line in lines:
        spc = len(line) - len(line.lstrip())
        while len(line) > wrap:
            i = line.rfind(' ', 0, wrap)
            if i == -1:
                nlines += [line[:wrap]]
                line = line[wrap:]
            else:
                nlines += [line[:i]]
                line = line[i+1:]
            if line:
                line = ' '*spc + line
        nlines += [line]
    lines = nlines

    def draw(self,context):
        for line in lines:
            self.layout.label(line)

    bpy.context.window_manager.popup_menu(draw, title="Error Message", icon="ERROR")
    return


def handle_exception():
    errormsg = print_exception('Render_Farm_log')
    # if max number of exceptions occur within threshold of time, abort!
    print('\n'*5)
    print('-'*100)
    print("Something went wrong. Please start an error report with us so we can fix it! (press the 'Report a Bug' button under the 'Render On Servers' dropdown menu of the Render Farm)")
    print('-'*100)
    print('\n'*5)
    showErrorMessage("Something went wrong. Please start an error report with us so we can fix it! (press the 'Report a Bug' button under the 'Render on Servers' dropdown menu of the Render Farm Addon)", wrap=240)


# http://stackoverflow.com/questions/14519177/python-exception-handling-line-number
def print_exception(txtName, showError=False):
    exc_type, exc_obj, tb = sys.exc_info()

    errormsg = 'EXCEPTION (%s): %s\n' % (exc_type, exc_obj)
    etb = traceback.extract_tb(tb)
    pfilename = None
    for i, entry in enumerate(reversed(etb)):
        filename, lineno, funcname, line = entry
        if filename != pfilename:
            pfilename = filename
            errormsg += '         %s\n' % (filename)
        errormsg += '%03d %04d:%s() %s\n' % (i, lineno, funcname, line.strip())

    print(errormsg)

    if txtName not in bpy.data.texts:
        # create a log file for error writing
        bpy.ops.text.new()
        bpy.data.texts[-1].name = txtName

    # write error to log text object
    bpy.data.texts[txtName].write(errormsg + '\n')

    if showError:
        showErrorMessage(errormsg, wrap=240)

    return errormsg


def update_progress(job_title, progress):
    length = 20  # modify this to change the length
    block = int(round(length*progress))
    msg = "\r{0}: [{1}] {2}%".format(job_title, "#"*block + "-"*(length-block), round(progress*100, 1))
    if progress >= 1:
        msg += " DONE\r\n"
    sys.stdout.write(msg)
    sys.stdout.flush()


def writeErrorToFile(errorReportPath, txtName, addonVersion):
    # write error to log text object
    if not os.path.exists(errorReportPath):
        os.makedirs(errorReportPath)
    fullFilePath = os.path.join(errorReportPath, "Render_Farm_error_report.txt")
    f = open(fullFilePath, "w")
    f.write("\nPlease copy the following form and paste it into a new issue at https://repo.cse.taylor.edu/cgearhar/RenderFarm/")
    f.write("\n\nDon't forget to include a description of your problem! The more information you provide (what you were trying to do, what action directly preceeded the error, etc.), the easier it will be for us to squash the bug.")
    f.write("\n\n### COPY EVERYTHING BELOW THIS LINE ###\n")
    f.write("\nDescription of the Problem:\n")
    f.write("\nBlender Version: " + bversion())
    f.write("\nAddon Version: " + addonVersion)
    f.write("\nPlatform Info:")
    f.write("\n   sysname = " + str(os.uname()[0]))
    f.write("\n   release = " + str(os.uname()[2]))
    f.write("\n   version = " + str(os.uname()[3]))
    f.write("\n   machine = " + str(os.uname()[4]))
    f.write("\nError:")
    try:
        f.write("\n" + bpy.data.texts[txtName].as_string())
    except KeyError:
        f.write(" No exception found")
