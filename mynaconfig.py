#-------------------------------------------------------------------------------
# Copyright (c) 2014 Proxima Centauri srl <info@proxima-centauri.it>.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# Contributors:
#     Proxima Centauri srl <info@proxima-centauri.it> - Myna configuration handler
#-------------------------------------------------------------------------------
#!/usr/bin/python
# -*- coding: utf-8 -*-
from ConfigParser import ConfigParser, SafeConfigParser, ParsingError, NoSectionError
import json, os

class MynaConfig():

    def __init__(self, cfgfile):
	self.__cfgfile = cfgfile
        self.__devices = {}
        self.__logics = {}
        self.__rooms = {}
        self.__daemon = {}
        self.__alert = {}
        self.__plant = {}
	self.read()

    def __get(self, section):
        return dict(map(lambda y: tuple(map(lambda x: map(str.strip, x.split(',')) if ',' in x else x, y)), self.__parser.items(section)))

    def __set(self, section, secDict):
	self.__parser.remove_section(section)
	self.__parser.add_section(section)
        map(lambda (k, v): self.__parser.set(section, k, v if not isinstance(v, list) else ','.join(v)), sorted(secDict.iteritems()))

    def __get_multi(self, sections, secType):
	secDict = {}
        map(lambda z: secDict.update({z.replace('%s.' % secType, ''): dict(map(lambda y: tuple(map(lambda x: map(str.strip, x.split(',')) if ',' in x else x, y)), self.__parser.items(z)))}), sections)
	return secDict

    def __set_multi(self, sections, secType, secDict):
	map(lambda x: self.__parser.remove_section(x), sections)
        sections = map(lambda x: '%s.%s' % (secType, x), secDict.keys())
	map(lambda x: self.__parser.add_section(x), sorted(sections))
	map(lambda x: map(lambda (k, v): self.__parser.set(x, k, v if not isinstance(v, list) else ','.join(v)), sorted(secDict[x.replace('%s.' % secType, '')].iteritems())), sections)
        return sections

    def read(self):
        try:
            self.__parser = SafeConfigParser()
            self.__parser.read(self.__cfgfile)
        except ParsingError, e:
            print e
            sys.exit(1)
	sections = self.__parser.sections()
        try:
	    self.__deviceSections = filter(lambda x:'device.' in x, sections)
	    self.__roomSections = filter(lambda x:'room.' in x, sections)
	    self.__logicSections = filter(lambda x:'logic.' in x, sections)
	    self.__daemonSections = filter(lambda x:'daemon.' in x, sections)
	    self.__devices = self.__get_multi(self.__deviceSections, 'device')
	    self.__rooms = self.__get_multi(self.__roomSections, 'room')
	    self.__logics = self.__get_multi(self.__logicSections, 'logic')
	    self.__daemon = self.__get_multi(self.__daemonSections, 'daemon')
	    self.__alert = self.__get('alert')
	    self.__plant = self.__get('plant')
	except NoSectionError:
	    pass

    def write(self):
        try:
	    os.rename(self.__cfgfile, '%s.bak' % self.__cfgfile)
            with open(self.__cfgfile, 'w') as fp:
		self.__parser.write(fp)
		fp.close()
        except OSError, e:
            print e
            sys.exit(1)

    def getDevices(self, bus=None, types=None):
	devices = self.__devices
	if bus:
	    if isinstance(bus, str) or isinstance(bus, unicode):
		bus = [bus]
	    devices = filter(None, map(lambda (k, v): {k: v} if 'bus' in v and v['bus'] in bus else None, devices.iteritems()))[0]
	if types:
	    if isinstance(types, str) or isinstance(types, unicode):
		types = [types]
	    devices = filter(None, map(lambda (k, v): {k: v} if 'type' in v and v['type'] in types else None, devices.iteritems()))
	return devices

    def getDevice(self, id=None, address=None):
	device = None
	if address:
	    device = filter(None, map(lambda (k, v): {k: v} if 'address' in v.keys() and address.upper() in map(str.upper, v.values()) else None, self.__devices.iteritems()))
	    device = device[0] if device else None
	elif id:
	    device = {id: self.__devices[id]} if id in self.__devices else None
	return device

    def getRooms(self):
	return self.__rooms

    def getRoom(self, id=None, device=None):
	room = None
	if device:
	    room = filter(None, map(lambda (k, v): {k: v} if filter(lambda x: k if device in x else None, v.values()) else None, self.__rooms.iteritems()))
	    room = room[0] if room else None
	elif id:
	    room = {id: self.__rooms[id]} if id in self.__rooms else None
	return room

    def getLogics(self):
	return self.__logics

    def getLogic(self, id=None, room=None):
	logic = None
	if room:
	    logic = filter(None, map(lambda (k, v): {k: v} if filter(lambda x: k if room in x else None, v.values()) else None, self.__logics.iteritems()))
	    logic = logic[0] if logic else None
	elif id:
	    logic = {id: self.__logics[id]} if id in self.__logics else None
	return logic

    def setDevices(self, devices):
	self.__devices = devices
	self.__deviceSections = self.__set_multi(self.__deviceSections, 'device', devices)

    def setRooms(self, rooms):
	self.__rooms = rooms
	self.__roomSections = self.__set_multi(self.__roomSections, 'room', rooms)

    def setLogics(self, logics):
	self.__logics = logics
	self.__logicSections = self.__set_multi(self.__logicSections, 'logic', logics)

    def getDaemonConfig(self, subSection = None):
	if subSection and subSection in self.__daemon:
	    return self.__daemon[subSection]
	return self.__daemon

    def getAlertConfig(self):
	return self.__alert

    def setAlertConfig(self, alert):
	self.__alert = alert
	self.__set('alert', alert)

    def getPlantConfig(self):
	return self.__plant

    def setPlantConfig(self, plant):
	self.__plant = plant
	self.__set('plant', plant)

