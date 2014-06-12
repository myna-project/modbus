#-------------------------------------------------------------------------------
# Copyright (c) 2014 Proxima Centauri srl <info@proxima-centauri.it>.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# Contributors:
#     Proxima Centauri srl <info@proxima-centauri.it> - class and thread based
#     Alex Raimondi (https://github.com/kleckse) - initial implementation
#-------------------------------------------------------------------------------
#!/usr/bin/python
# -*- coding: utf-8 -*-

import serial
import checksum
import datetime
import struct
import threading
from telegram import *

class ESP3BasePacket(object):
    
    def __init__(self, pktType, data, optData = bytearray(0)):
        self.pktType = pktType
        self.data = data
        self.optData = optData 
        self.timeStamp = datetime.datetime.now()
        self.initFromData()
        
    def initFromData(self):
        pass
        
    @classmethod
    def fromData(cls,  data, optData = bytearray(0)):
        return cls(cls.typeId,  data,  optData)
        
    # serialize packet header and compute checksum
    def  _header(self):
        # Create header form data length and packet type
        header = bytearray(struct.pack('>HBB', 
                                        len(self.data),  
                                        len(self.optData),  
                                        self.pktType))
        # compute checksum
        crc = checksum.crc8(0xff)
        crc.update(header)
        header.append(crc.sum)   
        # sync byte (not included in checksum)
        header.insert(0,  0x55)
        return header

    # serialize entier packet
    def serialize(self):
        # serialize header
        pkt = self._header()
        
        # compute checksum over data
        crc = checksum.crc8(0xff)
        crc.update(self.data)
        crc.update(self.optData)
        
        # append data and opt. data (if any)
        if len(self.data) > 0:
            pkt = pkt + self.data
        if len(self.optData) > 0:
            pkt = pkt + self.optData
        
        # finaly add data checksum
        pkt.append(crc.sum)
        return pkt
        
    @classmethod
    def factory(cls,  pktType,  data,  optData):
        if pktType == ESP3Radio.typeId: 
            return ESP3Radio.fromData(data, optData)
        if pktType == ESP3Response.typeId:
            return ESP3Response.fromData(data,  optData)
        # add all other packet type
        else:
            # fall back for unknown packets
            return ESP3BasePacket(pktType,  data,  optData)
  

class ESP3Radio(ESP3BasePacket):
    
    typeId = 0x01

    def initFromData(self):
        self.choice = self.data[0]        
        (self.senderId,  self.status)= struct.unpack('>IB',  str(self.data[len(self.data)-5:len(self.data)]))
        (self.subTelNum,  self.destId,  self.dBm,  self.SecurityLevel) = struct.unpack('>BIBB',  str(self.optData))
        self.repeatCount = self.status & 0x0F
        # T21 and NU flags as tuple
        self.flags = ((self.status >> 5) & 0x01, (self.status >> 4) & 0x01)

    def toEvents(self):
        # act upon choice
        if self.choice == 0xf6:
            if self.flags == (1, 1):
                # one or more buttons pressed
                btn = self.data[1]
                events = (ButtonEvent.buttonPressed(self.timeStamp, self.senderId, (btn >> 5) & 0x7), )
                if btn & 0x01:
                    # 2nd button pressed
                    events += (ButtonEvent.buttonPressed(self.timeStamp, self.senderId, (btn >> 1) & 0x7), )
                # return event tuple
                return events
            elif self.flags == (1, 0):
                # buttons released (one or more)
                return ButtonEvent.buttonReleased(self.timeStamp, self.senderId),

        # fallback return empty tuple
        return ()

class ESP3Response(ESP3BasePacket):

    typeId = 0x02

class ESP3CommonCommand(ESP3BasePacket):

    typeId = 0x05

    @classmethod
    def withCommand(cls,  cmd,  cmdData = bytearray(0),  optData = bytearray(0)):
        data = bytearray(struct.pack('B',  cmd)) + cmdData
        return cls.fromData(data,  optData)

class States:
  Idle, Sync, Data, OptData, Chk = range(5)

class EnOcean(threading.Thread):
    def __init__(self, queues, port, baudrate=57600):
	super(EnOcean, self).__init__()
	self._queues = queues
        self._stop = threading.Event()
	self.setDaemon(True)
	self._baudrate = baudrate
	self._port = port

    def stop(self):
        self._stop.set()
        self._disconnect()

    def run(self):
	self._connect()
        while not self._stop.isSet():
	    pkt = self.read()
	    if pkt:
		try:
		    # try to get queue for packet
		    self._queues[pkt.typeId].put(pkt)
		except KeyError:
		    # put on default queue (which must exist!)
		    self._queues['default'].put(pkt)

    def _connect(self):
	self._sp = serial.Serial(self._port,  self._baudrate, timeout = 1)
	self._rxState = States.Idle

    def _disconnect(self):
	self._sp.close()

    def write(self, pkt):
	spkt = str(pkt.serialize())
	self._sp.write(spkt)

    def read(self):
        # initialize some local variables
	pcktType = 0
	PcktData = None
	OptData = None
	optLength = 0

	# number of bytes to receive as next
	n = 1
	self._rxState = States.Idle

	while not self._stop.isSet():
	    data = self._sp.read(n)

    	    if len(data) == n:
        	# received enough bytes
        	data = bytearray(data)

        	if self._rxState == States.Idle:
            	    if data[0] == 0x55:
            	        self._rxState = States.Sync
            	        # next we want to receive 4 header bytes + 1 crc
            	        n = 5

        	elif self._rxState == States.Sync:
            	    crc = checksum.crc8(0xff)
            	    crc.update(data)
            	    if crc.valid():
            	        # extract header
            	        dataLength = (data[0] << 8) + data[1]
            	        optLength = data[2]
            	        pcktType = data[3]
            	        # proceed to next rxState
            	        self._rxState = States.Data
            	        n = dataLength
            	    else:
            	        # Go back to idle (could be improved)
            	        self._rxState = States.Idle
            	        n = 1

        	elif self._rxState == States.Data:
            	    PcktData = data
            	    # proceed to next rxState
            	    self._rxState = States.OptData
            	    n = optLength

        	elif self._rxState == States.OptData:
            	    OptData = data
            	    # proceed to next rxState
            	    self._rxState = States.Chk
            	    n = 1

        	elif self._rxState == States.Chk:
            	    # verify data
            	    crc = checksum.crc8(0xff)
            	    crc.update(PcktData)
            	    crc.update(OptData)
            	    crc.update(data)
            	    if crc.valid():
            	        return ESP3BasePacket.factory(pcktType, PcktData, OptData)

            	    # packet completed => back to idle
            	    self._rxState = States.Idle
            	    n = 1

        	else:
            	    # timeout => back to idle
            	    self._rxState = States.Idle
            	    n = 1
