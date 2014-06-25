# Gateway Description

On a Raspberry Pi (but it fits on other embedded platforms, eg. Beaglebone) was developed a python Modbus server based on the library pymodbus. 
The code is stable, even though with limited features (gateway piface/onewire/enocean thru modbus) and with some TODOs.

The server is a Modbus TCP gateway. It's possibile to read owserver datas so One Wire sensors readings (independently from the way they 
are connected to the Raspberry board), read digital inputs and outputs from one or more PiFace board thru the library pifacedigitalio,
read the values received from EnOcean sensors thru an USB EnOcean transceiver. The configuration of sensors and sensor-modbus register
couples is totally configurable using specific sections of the Myna configuration file.

NB: It's expected (actually not tested) the usage of multiple PiFace boards (eg. using a PiRack). 
The configuration parameter is Boards in the section PiFace. The default is 0 (absence of a PiFace).

The daemon reads the configuration file (default path /etc/myna/myna.conf) that is formatted ad ini file, read using the library python-configparser.

The coil state is saved on a file so restored at the daemon restart. If this file is on a tmpfs the states are holded at the daemon 
restart but the system reboot in case of power failure or unexpeceted reboot.

## Operation
When the daemon starts and, if all checkings ends well, the logging is initializated, privileges are dropped, PiFace initialiazated, 
and it will be start a thead to receive One Wire datas from owserver and a thread to receive datas from EnOcean sensors. 
Finally, it will be start the Modbus TCP server.

Possibile sensor reading errors are managed by a default configurable value or, for sporadic missed readings and for a configurable 
time interval (HoldingTime), with the last valid reading. Holing and polling times of One Wire and EnOcean are independently configurable.

The Modbus TCP server will call some callback functions, one for every class of registers (digital inputs, holding registers and coils,
while discrete inputs are not implemented at the time) to initialize default register values and, in the expected cases (eg. coils) 
states are saved (or previous states are restored).

## Installation
To install the Modbus gateway it is requred Python (2.6 or later, it has beed developed and tested with 2.7, it will not work with 3.x) and some libraries.

Libraries to be installed (example with Debian/Ubuntu):

    apt-get install python
    apt-get install python-cap-ng python-lockfile python-configparser python-jsonpickle python-pifacedigitalio python-pymodbus python-daemon python-twisted python-serial python-rrdtool
    
pymodbus and python-configparser libraries required have to be downloaded from the jessie (in case of Debian/Raspbian distros) and manually installed. They are not available or too old in wheezy version. About ownet it is discouraged the use of python-ownet because it includes several bugs. Together with the daemon there are included two libraries in the respective diretory ownet and enocean: the first one is a bug fixed versione of python-ownet, the second one is an implementation of the EnOcean EC3 protocol based on the library of Alex Raimondi (https://github.com/kleckse/enocean).

Moreover it's required to create a system user with suitable permissions (the daemon could run as root but it's discouraged for security reasons):

    groupadd -g 502 -r modbus
    useradd -u 502 -g modbus -G spi,gpio -d /nonexistent -s /bin/false -r modbus

There is an init script to start the daemon at the syste boot (/etc/init.d/modbus). In a Debian like environment the daemon can be stated or stopped or 
restarted with service modbus start/stop/restart.

## Data history

The daemon has a simple data history feature. Datas are stored in a RRD database, with fixed parameters (step of 300 seconds, heartbeat of 3600 seconds,
datasource name data and type GAUGE, one only RRA of type  AVERAGE with xff of 0.5 and 105120 data rows (number of seconds of an year  / step that is 
one year of datas sampled every 5 minutes).

## Logging
 The logging confguration is separated from main Myna configuration, and it's independently managed by Python logging.config.fileConfig().

Main loggers are pymodbus and main. The first one is used by pymodbus library, the second one is used by the daemon. It can have indipendent and different handlers and logging levels.

For more information refer to Python manual:

https://docs.python.org/2/library/logging.config.html

##Configuration file format

The section directly involved for the modbus daemon configuration are:

* daemon: these defines the parameters of the daemon, One Wire and EnOcean configurations, data logging, etc.
* device: these defines the devices and the modbus registers associations

Due to an extension to the class ConfigParser, MynaConfig(), it's possibile to manage subsections (eg. device.mydevice1, device.mydevice2, ...) and subkeys (eg. climatic.x, climatic.y, climatic.z).

### Deamon

# Subsections:

**daemon.Daemon:** it contains the daemon configuration. uid and gid defines the unix user (numeri uid) and the unix group (numeric gid)
witch privileges woul be dropped (the defaults are 0 and 0, so root will be used; this is discouraged for security reasons). listenport 
defines the TCP listen port (default: 502). supplementarygroups (boolean) defines the usage of supplementary groups (required to use PiFaces boards). 
listenaddress defines the listen IP address (default: 0.0.0.0 so the daemon will listen on all configured IP address of all network interfaces).
pidfile defines the path and filename of the pid file.

**daemon.Modbus:** defines the configuration of Modbus registers. registers defines the numbers of registers publishes by the daemon 
(no matter if used or not), endianity (Big or Little) defines the endianity (bytes orders of the words). datastore defines the file
where registers states will be stored and then restored at the daemon restart.

**daemon.PiFace:** defines the usage and the number of PiFace boards (parameter boards).

**daemon.Ownet**:defines the configuration of the One Wire handling thread. Datas are read thru the middleware owserver. 
Parameters are server that is the IP address or hostname of the owserver, port that is TCP port of the server, path that 
is the owfs root (it could be useful in case of a One Wire hub or to read the uncached way of owserver; for normal usage is '/'). 
pollingtime and holdingtime are, respectively, the sampling interval and the time interval during witch the last reading will be 
kept as valid value in case of miss readings. failvalue defines a fake value to use in case of miss readings and holdingtime exceding. 
datastore definies the path and filename that will store sensors readings and timestamps.

**daemon.EnOcean**: defines  the configuration of the EnOcean handling thread. Parameters are port that is the serial port with the 
transceiver, pollingtime and holdingtime,  are, respectively, the sampling interval and the time interval during witch the last reading will be 
kept as valid value in case of miss readings. failvalue defines a fake value to use in case of miss readings and holdingtime exceding. datastore 
definies the path and filename that will store sensors readings and timestamps.

**daemon.RRD**: contains the data logging configuration. The parameter enable (boolean) enable or disable the logging; the parameter 
path definines the path used to save RRD databases.

**daemon.Identity**: defines Modbus brand/model/version.

# Device

Each device contains a subsection, an id (better if coincide with the subsection), a register that defines the association with the modbus register, a bus (piface, onewire, enocean are supported at this time), an address that is the One Wire or EnOcean sensor address, a type that defines the measure type (Temperature or Humidity are supported at this time). In case of bus = enocean it's mandatory to specify also the parameter eep. The presence of extra parameter is tolerated.

The configuration file coul be carry other sections intended to other Myna components as web gui, alerting and web admin. These sections are trasparent to the modbus daemon.

# Holding register structure
Registers are used in couples, as float32 (IEEE 754) and their association are configurable with the parameter register in the sections device. 
The parameter register specifices the first registers of the couple of registers.

|REGISTER|      USAGE     |
|--------|----------------|
|1       |PiFace 1 input 1|
|2       |PiFace 1 input 2|
|3       |PiFace 1 input 3|
|4       |PiFace 1 input 4|
|5       |PiFace 1 input 5|
|6       |PiFace 1 input 6|
|7       |PiFace 1 input 7|
|8       |PiFace 1 input 8|
|9       |PiFace 2 input 1|

# Coils structure

|REGISTER|       USAGE     |
|--------|-----------------|
|1       |PiFace 1 output 1|
|2       |PiFace 1 output 2|
|3       |PiFace 1 output 3|
|4       |PiFace 1 output 4|
|5       |PiFace 1 output 5|
|6       |PiFace 1 output 6|
|7       |PiFace 1 output 7|
|8       |PiFace 1 output 8|
|9       |PiFace 2 output 1|

# Example of Myna configuration file

    [daemon.Daemon]
    uid = 502
    listenport = 502
    supplementarygroups = True
    gid = 502
    listenaddress = 0.0.0.0
    pidfile = /run/modbus/modbus.pid

    [daemon.Modbus]
    registers = 255
    datastore = /run/modbus/mbstore
    endianity = Big

    [daemon.PiFace]
    boards = 1

    [daemon.Ownet]
    server = localhost
    port = 4304
    path = /
    failvalue = 9999
    datastore = /run/modbus/owstore
    pollingtime = 60
    holdingtime = 300

    [daemon.Identity]
    vendorname = Pymodbus
    productcode = PM
    vendorurl = http://github.com/bashwork/pymodbus/
    productname = Pymodbus Server
    modelname = Pymodbus Server
    majorminorrevision = 1.0

    [daemon.RRD]
    enable = True
    path = /var/log/modbus

    [device.HVAC_MEETING_VLV]
    name =
    coil = 2
    type = OnOff
    id = HVAC_MEETING_VLV
    bus = piface

    [device.HVAC_MEETING_T]
    external = False
    address = 19A3EB030000
    register = 1
    type = Temperature
    id = HVAC_MEETING_T
    bus = onewire

    [device.HVAC_STM330_T]
    name = STM330
    bus = enocean
    register = 3
    eep = A5-02-05
    external = False
    address = 0181120A
    type = Temperature
    id = HVAC_STM330_T