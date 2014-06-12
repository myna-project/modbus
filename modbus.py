#-------------------------------------------------------------------------------
# Copyright (c) 2014 Proxima Centauri srl <info@proxima-centauri.it>.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# Contributors:
#     Proxima Centauri srl <info@proxima-centauri.it> - modbus gateway
#-------------------------------------------------------------------------------
#!/usr/bin/python
# -*- coding: utf-8 -*-

import atexit
import calendar
import capng
import grp
import lockfile
import logging
import logging.config
import logging.handlers
import ownet
import os
import pickle
import pifacecommon
import rrdtool
import signal
import socket
import struct
import sys
import time
import twisted.internet.error
import Queue

en = None
pf = None

#---------------------------------------------------------------------------#
# read configuration
#---------------------------------------------------------------------------#

cfgfile = '/etc/myna/myna.conf'
cfglogfile = '/etc/myna/logging.conf'

if not os.path.isfile(cfgfile):
    print "Cannot open main configuration file %s" % cfgfile
    sys.exit(1)

if not os.path.isfile(cfglogfile):
    print "Cannot open logging configuration file %s" % cfglogfile
    sys.exit(1)

#---------------------------------------------------------------------------#
# configure the service logging
#---------------------------------------------------------------------------#

logging.config.fileConfig(cfglogfile)
logger = logging.getLogger(__name__)

from daemon import runner
from pifacedigitalio import PiFaceDigital
from pymodbus.constants import Endian
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.payload import BinaryPayloadBuilder
from pymodbus.server.async import StartTcpServer
from twisted.internet.task import LoopingCall
from mynaconfig import MynaConfig
from enocean import *

#---------------------------------------------------------------------------#
# initialize default parameters, read configuration file
#---------------------------------------------------------------------------#
class ModbusConfig(MynaConfig):

    def __init__(self, cfgfile):
	self.pidfile = '/run/modbus/modbus.pid'	# PID file
	self.uid = 0				# Unix UID (default: root)
	self.gid = 0				# Unix GID (default: root)
	self.sgroups = True			# Unix supplementary groups

	self.mbaddr = '0.0.0.0'			# Modbus listen address
	self.mbport = 502			# Modbus listen port
	self.mbregs = 255			# Modbus registers available
	self.mbstore = '/run/modbus/mbstore'	# Modbus data store to allow daemon restart without loosing states
	self.endian = Endian.Big		# Modbus words endianity

	self.pifaces = 1			# Number of PiFace boards (max 8 I/O ports per PiFace)

	self.owserver = 'localhost'		# Ownet server
	self.owport = 4304			# Ownet port
	self.owpath = '/'			# Ownet path
	self.owfail = 0				# Ownet sensor empty/fail value
	self.owstore = '/run/modbus/owstore'	# Ownet data store to allow daemon restart without loosing states
	self.owtime = 60			# Ownet polling time and holding registers update (in seconds)
	self.owhold = 120			# Ownet holding of last values before failing (in seconds)

	self.enport = None			# EnOcean adapter serial port
	self.enfail = 0				# EnOcean  sensor empty/fail value
	self.enstore = '/run/modbus/enstore'	# EnOcean  data store to allow daemon restart without loosing states
	self.entime = 60			# EnOcean  polling time and holding registers update (in seconds)
	self.enhold = 120			# EnOcean  holding of last values before failing (in seconds)

	self.mbident = ModbusDeviceIdentification()
	self.mbident.VendorName = 'Pymodbus'
	self.mbident.ProductCode = 'PM'
	self.mbident.VendorUrl = 'http://github.com/bashwork/pymodbus/'
	self.mbident.ProductName = 'Pymodbus Server'
	self.mbident.ModelName = 'Pymodbus Server'
	self.mbident.MajorMinorRevision = '1.0'

	self.rrdenable = False			# RRD history sensors data saving
	self.rrdpath = '/tmp'			# RRD default path

	self.devices = {}

	MynaConfig.__init__(self, cfgfile)

	# read configuration file and validate parameters
	MynaConfig.read(self)

    def read(self):
	MynaConfig.read(self)
	config = self.getDaemonConfig('daemon')
	try:
	    if 'Daemon' in config:
		self.mbaddr = config['Daemon']['listenaddress']
		self.mbport = int(config['Daemon']['listenport'])
		self.uid = int(config['Daemon']['uid'])
		self.gid = int(config['Daemon']['gid'])
		self.sgroups = config['Daemon']['supplementarygroups']
		self.pidfile = config['Daemon']['pidfile']
	    if 'Modbus' in config:
		self.mbregs = int(config['Modbus']['registers'])
		self.mbstore = config['Modbus']['datastore']
		endianity = {'BIG': Endian.Big, 'LITTLE': Endian.Little}
		if 'endianity' in config['Modbus'] and config['Modbus']['endianity'].upper() in endianity:
		    self.endian = endianity[config['Modbus']['endianity'].upper()]
	    if 'PiFace' in config:
		self.pifaces = int(config['PiFace']['boards'])
	    if 'Ownet' in config:
		self.owserver = config['Ownet']['server']
		self.owport = int(config['Ownet']['port'])
		self.owpath = config['Ownet']['path']
		self.owfail = int(config['Ownet']['failvalue'])
		self.owstore = config['Ownet']['datastore']
		self.owtime = int(config['Ownet']['pollingtime'])
		self.owhold = int(config['Ownet']['holdingtime'])
	    if 'EnOcean' in config:
		self.enport = config['EnOcean']['port']
		self.enfail = int(config['EnOcean']['failvalue'])
		self.enstore = config['EnOcean']['datastore']
		self.entime = int(config['EnOcean']['pollingtime'])
		self.enhold = int(config['EnOcean']['holdingtime'])
	    if 'Identity' in config:
		self.mbident.VendorName = config['Identity']['vendorname']
		self.mbident.ProductCode = config['Identity']['productcode']
		self.mbident.VendorUrl = config['Identity']['vendorurl']
		self.mbident.ProductName = config['Identity']['productname']
		self.mbident.ModelName = config['Identity']['modelname']
		self.mbident.MajorMinorRevision = config['Identity']['majorminorrevision']
	    if 'RRD' in config:
		self.rrdenable = config['RRD']['enable']
		self.rrdpath = config['RRD']['path']
	except KeyError, e:
	    print 'Missing configuration key: %s' % e
	    os._exit(1)

config = ModbusConfig(cfgfile)

#---------------------------------------------------------------------------#
# BinaryPayloadBuilder class extension to costruct list of integers words
#---------------------------------------------------------------------------#
class PayloadBuilder(BinaryPayloadBuilder):
    # values to integers instead of strings - handle a supposed bug in pymodbus
    def values(self):
        return list(struct.unpack(self._endian + str(len(self._payload[0]) >> 1) + 'H', self._payload[0]))

#---------------------------------------------------------------------------#
# IR data block callback (called for IR get)
#---------------------------------------------------------------------------#
class IRCallbackDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address, values):
        super(IRCallbackDataBlock, self).__init__(address, values)

    def getValues(self, address, count):
	if config.pifaces:
	    for i in range(address - 1, count):
		value = pf.input_pins[i].value
		super(IRCallbackDataBlock, self).setValues(i + 1, [value])
	return super(IRCallbackDataBlock, self).getValues(address, count)

#---------------------------------------------------------------------------#
# coils data block callback (called for CO get or set)
#---------------------------------------------------------------------------#
class COCallbackDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address, values):
	# coil status persistency (load)
	if os.path.isfile(config.mbstore):
	    mbfile = open(config.mbstore,'rb')
	    values = pickle.load(mbfile)
	    mbfile.close()
	    if config.pifaces:
		for i in range(0, config.pifaces * 8):
		    pf.output_pins[i].value = values[i + 1]
        super(COCallbackDataBlock, self).__init__(address, values)

    def setValues(self, address, values):
	if config.pifaces:
	    for i in range(len(values)):
		if ((address + i) > (config.pifaces * 8)):
		    break
		pf.output_pins[address + i - 1].value = values[i]
	super(COCallbackDataBlock, self).setValues(address, values)

	# coil status persistency (save)
        mbfile = open(config.mbstore,'wb')
	pickle.dump(self.values, mbfile)
        mbfile.close()

    def getValues(self, address, count):
	if config.pifaces:
	    for i in range(address - 1, count):
		value = pf.output_pins[i].value
		super(COCallbackDataBlock, self).setValues(i + 1, [value])
	return super(COCallbackDataBlock, self).getValues(address, count)

#---------------------------------------------------------------------------#
# holding registers data block callback (called for HR get)
#---------------------------------------------------------------------------#
class HRCallbackDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address, values):
        super(HRCallbackDataBlock, self).__init__(address, values)

    def getValues(self, address, count):
        return super(HRCallbackDataBlock, self).getValues(address, count)

#---------------------------------------------------------------------------#
# RRD creation/modification/update
#---------------------------------------------------------------------------#

def rrdupdate(owdata):
    if config.rrdenable:
	stime = int(time.mktime(time.localtime()))
	path = config.rrdpath
	step = 300
	hb = 3600
	xff = 0.5
	HOUR = 3600
	YEAR = 31536000
	steps1 = 1
	rows1 = YEAR // step
	for sensor in owdata:
	    (value, timestamp) = owdata[sensor]
	    if value == config.owfail:
		continue
	    rrdfile = '%s/%s.rrd' % (path, sensor.upper())
	    if not os.path.isfile(rrdfile):
		try:
		    rrdtool.create(rrdfile, '--step', '%d' % step,
			'DS:data:GAUGE:%d:U:U' % hb,
			'RRA:AVERAGE:%d:%d:%d' % (xff, steps1, rows1))
		except rrdtool.error, e:
		    logger.warning(e)
	        logger.debug("RRD %s created" % sensor)
	    info = rrdtool.info(rrdfile)
	    if ((stime - info['last_update']) > step):
	        try:
		    rrdtool.update(rrdfile,'%s:%s' % (timestamp, value))
		except rrdtool.error, e:
		    logger.warning(e)
	        logger.debug("RRD %s updated" % sensor)

#---------------------------------------------------------------------------#
# ownet polling callback for reading sensors and updating holding registers
#---------------------------------------------------------------------------#
def OwCallback(a):

    context = a

    # polling timestamp
    utime = int(time.mktime(time.gmtime()))
    stime = int(time.mktime(time.localtime()))

    # slave 0x00 register 0x03 (HR)
    register = 0x03
    slave_id = 0x00

    builder = PayloadBuilder(endian=config.endian)

    owdata = {}

    # owdata persistency (load)
    if os.path.isfile(config.owstore):
	try:
	    owfile = open(config.owstore,'rb')
	    owdata = pickle.load(owfile)
	    owfile.close()
	except OSError:
	    logger.warning("Cannot open %s for reading." % config.owstore) 

    # init ownet configuration
    ownet.init('%s:%d' % (config.owserver, config.owport))

    # try to open ownet server
    try:
	ow = ownet.Sensor(config.owpath)
        owread = True
    except (socket.gaierror, socket.error):
        logger.warning("Cannot connect owserver %s:%d." % (config.owserver, config.owport)) 
        owread = False

    # if connected, read known sensors and update owdata
    if owread:
        try:
            for sensor in ow.sensors():
		if (hasattr(sensor, 'id') & hasattr(sensor, 'temperature')):
		    owdata[sensor.id] = [ sensor.temperature, stime ]
		if (hasattr(sensor, 'id') & hasattr(sensor, 'humidity')):
		    owdata[sensor.id] = [ sensor.humidity, stime ]
	except (socket.gaierror, socket.error, OverflowError):
	    pass

    # deinit ownet
    ownet.finish()

    # update RRDs
    if owread:
	rrdupdate(owdata)

    # owdata validation
    if '' in owdata: del owdata['']
    for sensor in owdata:
	last = owdata[sensor][1]
	if ((stime - last) > config.owhold) or owdata[sensor][0] == '':
	    owdata[sensor][0] = config.owfail
	    logger.warning("Cannot read 1 wire sensor %s from owserver %s:%d." % (sensor, config.owserver, config.owport))
	if not owread:
	    logger.warning("Cannot read 1 wire sensor %s from owserver %s:%d." % (sensor, config.owserver, config.owport))

    # owdata persistency (save)
    if owread:
	try:
	    owfile = open(config.owstore,'wb')
	    pickle.dump(owdata, owfile)
	    owfile.close()
	except OSError:
	    logger.warning("Cannot open %s for writing." % config.owstore) 

    # reset holding registers with owfail value
    devices = config.getDevices(bus = 'onewire', types = ['Temperature', 'Humidity'])
    for sensor in devices:
	try:
	    id = sensor.keys()[0]
	    device = config.getDevice(id)
	    mbaddr = int(device.values()[0]['register'])
	    builder.reset()
	    builder.add_32bit_float(config.owfail)
	    context[slave_id].setValues(register, mbaddr, builder.values())
	except AttributeError:
	    pass

    # update holding registers with owdata
    for address in owdata:
	try:
	    device = config.getDevice(address = address)
	    mbaddr = int(device.values()[0]['register'])
	    data = owdata[address][0]
	    builder.reset()
	    builder.add_32bit_float(data)
	    context[slave_id].setValues(register, mbaddr, builder.values())
	except AttributeError:
	    pass

#---------------------------------------------------------------------------#
# EnOcean polling callback for reading sensors and updating holding registers
#---------------------------------------------------------------------------#
def EnCallback(a):

    (context, queues) = a
    qRadio = queues[ESP3Radio.typeId]

    # polling timestamp
    utime = int(time.mktime(time.gmtime()))
    stime = int(time.mktime(time.localtime()))

    # slave 0x00 register 0x03 (HR)
    register = 0x03
    slave_id = 0x00

    builder = PayloadBuilder(endian=config.endian)

    endata = {}

    # endata persistency (load)
    if os.path.isfile(config.enstore):
	try:
	    enfile = open(config.enstore,'rb')
	    endata = pickle.load(enfile)
	    enfile.close()
	except OSError:
	    logger.warning("Cannot open %s for reading." % config.enstore) 

    while qRadio.qsize():
	qr = qRadio.get()
	t = ESP3Telegram(None, qr.data)
	try:
	    device = config.getDevice(address = t.sender())
	    eep = device.values()[0]['eep']
	    t = ESP3Telegram(eep, qr.data)
	    if t.tmp():
		endata[t.sender()] = [t.tmp(), stime]
	    if t.hum():
		endata[t.sender()] = [t.hum(), stime]
	except (AttributeError, KeyError):
	    pass

    # update RRDs
    rrdupdate(endata)

    # endata validation
    for sensor in endata:
	last = endata[sensor][1]
	if ((stime - last) > config.enhold) or endata[sensor][0] == '':
	    endata[sensor][0] = config.enfail
	    logger.warning("Cannot receive anymore EnOcean sensor %s." % sensor)

    # endata persistency (save)
    try:
        enfile = open(config.enstore,'wb')
        pickle.dump(endata, enfile)
        enfile.close()
    except OSError:
        logger.warning("Cannot open %s for writing." % config.enstore) 

    # reset holding registers with enfail value
    devices = config.getDevices(bus = 'enocean')
    for sensor in devices:
	try:
	    id = sensor.keys()[0]
	    device = config.getDevice(id)
	    mbaddr = int(device.values()[0]['register'])
	    builder.reset()
	    builder.add_32bit_float(config.owfail)
	    context[slave_id].setValues(register, mbaddr, builder.values())
	except AttributeError:
	    pass

    # update holding registers with endata
    for address in endata:
	try:
	    device = config.getDevice(address = address)
	    mbaddr = int(device.values()[0]['register'])
	    data = endata[address][0]
	    builder.reset()
	    builder.add_32bit_float(data)
	    context[slave_id].setValues(register, mbaddr, builder.values())
	except AttributeError:
	    pass

#---------------------------------------------------------------------------#
# the main app running in background
#---------------------------------------------------------------------------#
class ModbusApp():

    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/null'
        self.stderr_path = '/dev/null'
        self.pidfile_path = config.pidfile
        self.pidfile_timeout = 10

    def run(self):
	global en, pf
	# init PiFace
	if config.pifaces:
	    try:
		pf = PiFaceDigital()
		logger.debug("PiFace board/s initialized.")
	    except pifacecommon.spi.SPIInitError:
		logger.critical("Cannot initialize PiFace.")
		os._exit(1)

	# init EnOcean
	if config.enport:
	    qRadio = Queue.Queue()
	    qResponse = Queue.Queue()
	    qEvent = Queue.Queue()
	    enqueues = {}
	    enqueues = dict({ESP3Radio.typeId: qRadio, ESP3Response.typeId: qResponse, 'default': qResponse})
	    try:
		s = serial.Serial(config.enport)
		s.close()
	    except (serial.SerialException):
		logger.critical("Cannot open serial port %s." % config.enport)
		os._exit(1)
	    en = EnOcean(enqueues, config.enport)
	    en.start()
	    logger.debug("EnOcean initialized.")


	mbregs = config.mbregs
	store = ModbusSlaveContext(
	    di = ModbusSequentialDataBlock(0, [0]*mbregs),
	    co = COCallbackDataBlock(0, [0]*mbregs),
	    hr = HRCallbackDataBlock(0, [0]*mbregs),
	    ir = IRCallbackDataBlock(0, [0]*mbregs))
	context = ModbusServerContext(slaves=store, single=True)

	owloop = LoopingCall(f=OwCallback, a=context)
	enloop = LoopingCall(f=EnCallback, a=(context, enqueues))

	# start one wire polling thread
	owloop.start(config.owtime, now=True)
	logger.info("Started One Wire polling. Polling rate %d seconds, holding time %d seconds." % (config.owtime, config.owhold))

	# start enocean polling thread
	enloop.start(config.entime, now=True)
	logger.info("Started EnOcean polling. Polling rate %d seconds, holding time %d seconds." % (config.entime, config.enhold))

	# start TCP Modbus server
	try:
	    StartTcpServer(context, identity=config.mbident, address=(config.mbaddr, config.mbport))
	except twisted.internet.error.CannotListenError:
	    logger.critical("Cannot listen on %s:%d. Socket already in use." % (config.mbaddr, config.mbport))
	    os._exit(1)

	os._exit(0)

#---------------------------------------------------------------------------#
# create pid and lockfile directory if it doesn't exists
#---------------------------------------------------------------------------#

pidpath = os.path.dirname(config.pidfile)
if not os.path.exists(pidpath):
    try:
	os.mkdir(pidpath)
	os.chown(pidpath, config.uid, config.gid)
    except OSError:
	logger.critical("Path %s doesn't exists or insufficient permissions." % pidpath)
	os._exit(1)

#---------------------------------------------------------------------------#
# drop root privileges retaining capability CAP_NET_BIND_SERVICE
#---------------------------------------------------------------------------#

def getsgroups(gid):
    grnam = grp.getgrgid(gid).gr_name
    sgroups = []
    groups = grp.getgrall()
    for group in groups:
        if grnam in group.gr_mem:
	    sgroups.append(grp.getgrnam(group.gr_name).gr_gid)
    return sgroups

try:
    capng.capng_clear(capng.CAPNG_SELECT_BOTH)
    capng.capng_update(capng.CAPNG_ADD, capng.CAPNG_EFFECTIVE|capng.CAPNG_PERMITTED, capng.CAP_NET_BIND_SERVICE)
    if config.sgroups:
	sgroups = getsgroups(config.gid)
	if sgroups:
	    os.setgroups(sgroups)
	capng.capng_change_id(config.uid, config.gid, capng.CAPNG_CLEAR_BOUNDING)
    else:
	capng.capng_change_id(config.uid, config.gid, capng.CAPNG_CLEAR_BOUNDING|capng.CAPNG_DROP_SUPP_GRP)
    logger.debug("Changed uid/gid to %d:%d." % (config.uid, config.gid))
except OSError:
    logger.critical("Cannot change uid/gid to %d:%d. Nonexistent uid/gid or insufficient privileges." % (config.uid, config.gid))
    os._exit(1)

#---------------------------------------------------------------------------#
# signal handler
#---------------------------------------------------------------------------#

def sighup(signum, frame):
    logger.info("SIGHUP received, reloading configuration")
    config.read()

signal.signal(signal.SIGHUP, sighup)

#---------------------------------------------------------------------------#
# exit handler
#---------------------------------------------------------------------------#

@atexit.register
def terminate(signum=None, frame=None):
    if pf and hasattr(pf, 'fd'):
	pf.deinit_board()
    if en:
	en.stop()
    logger.info("Exiting.")

signal.signal(signal.SIGTERM, terminate)
signal.signal(signal.SIGINT, terminate)

#---------------------------------------------------------------------------#
# init and demonize ModbusApp (preserving logging)
#---------------------------------------------------------------------------#

app = ModbusApp()

daemon_runner = runner.DaemonRunner(app)
fileno = []
for (key, value) in logging.Logger.manager.loggerDict.iteritems():
    if hasattr(value, 'handlers'): 
	for handler in value.handlers:
    	    if hasattr(handler, 'stream') and hasattr(handler.stream, 'fileno'):
    		fileno.append(handler.stream.fileno())
    	    if hasattr(handler, 'socket') and hasattr(handler.socket, 'fileno'):
    		fileno.append(handler.socket.fileno())
daemon_runner.daemon_context.files_preserve = list(set(fileno))
daemon_runner.parse_args()
try:
    daemon_runner.do_action()
except lockfile.LockTimeout:
    logger.warning("Already running.")
    os._exit(1)
except runner.DaemonRunnerStopFailureError:
    logger.warning("Not running.")
    os._exit(1)

