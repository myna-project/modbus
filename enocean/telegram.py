#-------------------------------------------------------------------------------
# Copyright (c) 2014 Proxima Centauri srl <info@proxima-centauri.it>.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# Contributors:
#     Proxima Centauri srl <info@proxima-centauri.it> - class and thread based
#-------------------------------------------------------------------------------
#!/usr/bin/python
# -*- coding: utf-8 -*-

# Possibile EEPs for STM 330 sensors
# A5-02-05 Temperature 0 - 40 C
# A5-04-01 Temperature and Humidity 0 - 40 C, 0 - 100 %
# A5-10-03 Temperature, Set Point Control 0 - 255, 0 - 40 C
# A5-10-05 Temperature, Occupancy and Set Point Control 0 - 255, 0 - 40 C
# A5-10-10 Temperature, Humidity, Set Point and Occupancy Control 0 - 255, 0 - 100 %, 0 - 40 C
# A5-10-12 Temperature, Humidity and Set Point 0 - 255, 0 - 100 %, 0 - 40 C

class ESP3Telegram(object):
    def __init__(self, eep, data):
	self.data = data
	self.choice = self.data[0]
	self.rorg = None
	self.func = None
	self.type = None
	if eep:
	    (rorg, func, type) = eep.split('-')
	    self.rorg = int(rorg, 16)
	    self.func = int(func, 16)
	    self.type = int(type, 16)

    def tmp(self):
	ranges = {0x01: [-40.0, 0.0, 6.375],
		  0x02: [-30.0, 10.0, 6.375],
		  0x03: [-20.0, 20.0, 6.375],
		  0x04: [-10.0, 30.0, 6.375],
		  0x05: [0.0, 40.0, 6.375],
		  0x06: [10.0, 50.0, 6.375],
		  0x07: [20.0, 60.0, 6.375],
		  0x08: [30.0, 70.0, 6.375],
		  0x09: [40.0, 80.0, 6.375],
		  0x0a: [50.0, 90.0, 6.375],
		  0x0b: [60.0, 100.0, 6.375],
		  0x10: [-60.0, 20.0, 3.1875],
		  0x11: [-50.0, 30.0, 3.1875],
		  0x12: [-40.0, 40.0, 3.1875],
		  0x13: [-30, 50.0, 3.1875],
		  0x14: [-20.0, 60.0, 3.1875],
		  0x15: [-10.0, 70.0, 3.1875],
		  0x16: [0.0, 80.0, 3.1875],
		  0x17: [10.0, 90.0, 3.1875],
		  0x18: [20.0, 100.0, 3.1875],
		  0x19: [30.0, 110.0, 3.1875],
		  0x1a: [40.0, 120.0, 3.1875],
		  0x1b: [50.0, 130.0, 3.1875],
		  0x20: [-10.0, 41.2, 20.0],
		  0x30: [-40.0, 62.3, 10.0]}
	if self.func in (0x02,):
	    (scaleMin, scaleMax, div) = ranges[self.type]
	    tmp = scaleMax - ((self.data[2] << 8) | self.data[3]) / div
	elif self.func in (0x04, 0x10):
	    div = 6.25
	    tmp = self.data[3] / div
	else:
	    return None
	return tmp

    def hum(self):
	if self.func in (0x04, 0x10):
	    div = 2.5
	    hum = self.data[2] / div
	else:
	    return None
	return hum

    def sp(self):
	if self.func in (0x10,):
	    sp = self.data[1]
	else:
	    return None
	return sp

    def isTeachIn(self):
	return bool(not self.data[4] & 0x80)

    def sender(self):
        return str(self.data[len(self.data)-5:len(self.data)-1]).encode('hex')

