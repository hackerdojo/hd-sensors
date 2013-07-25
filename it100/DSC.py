#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# DSC Alarm Plugin
# Developed by Travis Cook
# www.frightideas.com
#
# Updated for Hacker Dojo by Austin Hendrix

import os
import sys
import time
import re
from datetime import datetime
import serial

kSocketPort = 1514
kSocketBufferSize = 1024
kSocketTimeout = 1

kZoneStateOpen = 'open'
kZoneStateClosed = 'closed'
kZoneStateTripped = 'tripped'
kAlarmStateDisarmed = u'disarmed'
kAlarmStateExitDelay = u'exitDelay'
kAlarmStateFailedToArm = u'FailedToArm'
kAlarmStateArmed = u'armed'
kAlarmStateEntryDelay = u'entryDelay'
kAlarmStateTripped = u'tripped'

kLedIndexList = ['None','Ready','Armed','Memory','Bypass','Trouble','Program','Fire','Backlight','AC']
kLedStateList = ['off','on','flashing']
kArmedModeList = ['Away','Stay','Away, No Delay','Stay, No Delay']
kPanicTypeList = ['None','Fire','Ambulance','Panic']
kMonthList = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']

kCmdNormal = 0
kCmdThermoSet = 1
kPingInterval = 301
kHoldRetryTimeMinutes = 3

kMinimumIndigoVersion = '5.0.4'

kUseSayThisVariable = True

################################################################################
class DSC(object):

	def enum(self,**enums):
		return type('Enum', (), enums)

	########################################
	def __init__(self, port):

		self.States = self.enum(STARTUP=1,HOLD=2,HOLD_RETRY=3,HOLD_RETRY_LOOP=4,BOTH_INIT=5,SO_CONNECT=6,BOTH_PING=7,BOTH_POLL=8)
		self.state = self.States.STARTUP

		self.serialPort = port
		self.code = '000'

		self.shutdown = False
		self.interfaceState = 0
		self.zoneList = {}
		self.tempList = {}
		self.trippedZoneList = []
		self.keypadList = {}
		self.port = None
		self.repeatAlarmTripped = False
		self.isPortOpen = False
		self.txCmdList = []
		self.closeTheseZonesList = []
		self.currentHoldRetryTime = kHoldRetryTimeMinutes
		self.doorOrWindowOpen = False
		self.doorOrWindowOpenTimer = 0
		self.configEmailAlarms = ""

	def __del__(self):
		pass

	########################################
	# Communication Routines

	def calcChecksum(self, s):
		calcSum=0
		for c in s:
			calcSum += ord(c)
		calcSum %= 256
		return calcSum

	def closePort(self):
		if self.port == None:
			return
		if self.port.isOpen() == True:
			self.port.close()
			self.port = None

	def openPort(self):
		self.closePort()
		print(u"Initializing communication on port %s" % self.serialPort )
		try:
			self.port = serial.Serial(self.serialPort, 9600, writeTimeout=1)
		except Exception, err:
			print('Error opening serial port: %s' % (str(err)))
			return False

		if self.port.isOpen() == True:
			self.port.flushInput()
			self.port.timeout = 1
			return True

		return False

	def readPort(self):
		if self.port.isOpen() == False:
			self.state = self.States.BOTH_INIT
			return ""

		data = ""
		try:
			data = self.port.readline()
		except Exception, err:
			print('Connection RX Error: %s' % (str(err)))
			# Return with '-' signaling calling subs to abort so we can re-init.
			data = '-'
		except:
			print('Connection RX Problem, plugin quitting')
			exit()

		return data


	def writePort(self, data):
		self.port.write(data)


	def sendPacketOnly(self, data):
		pkt = "%s%02X\r\n" % (data, self.calcChecksum(data))
		print(u"TX: %s" % pkt)
		try:
			self.writePort(pkt)
		except Exception, err:
			print('Connection TX Error: %s' % (str(err)))
			exit()
		except:
			print('Connection TX Problem, plugin quitting')
			exit()


	def sendPacket(self, tx, waitFor='500', rxTimeout=3, txRetries=3):
		retries = txRetries
		txCmd = tx[:3]

		while txRetries > 0:
			self.sendPacketOnly(tx)
			ourTimeout = time.time() + rxTimeout
			txRetries -= 1
			while time.time() < ourTimeout:
				if self.shutdown == True:
					return ''
				(rxCmd,rxData) = self.readPacket()

				# If rxCmd == - then the socket closed, return for re-init
				if rxCmd == '-':
					return '-'

				if rxCmd == '502':
					print('Received system error after sending command, aborting.')
					return ''

				# If rxCmd is not 0 length then we received a response
				if len(rxCmd) > 0:
					if waitFor == '500':
						if (rxCmd == '500') and (rxData == txCmd):
							return rxData
					elif (rxCmd == waitFor):
						return rxData
			if txCmd != '000':
				print('Timed out after waiting for response to command %s for %u seconds, retrying.' % (tx,rxTimeout))
		print('Resent command %s %u times with no success, aborting.' % (tx,retries))
		return ''


	def readPacket(self):

		data = self.readPort()
		if len(data) == 0:
			return ('','')
		elif data == '-':
			# socket has closed, return with signal to re-initialize
			return ('-','')

		data = data.strip()

		m = re.search(r'^(...)(.*)(..)$', data)
		if not m:
			return ('','')

		# Put this try in to try to catch exceptions when non-ascii characters
		# were received, not sure why they are being received.
		try:
			print(u"RX: %s" % data)
			(cmd,dat,sum) = ( m.group(1), m.group(2), int(m.group(3),16) )
		except:
			print(u'IT-100/2DS Error: Received a response with invalid characters')
			return ('','')

		if sum != self.calcChecksum("".join([cmd,dat])):
			print("Checksum did not match on a received packet.")
			return ('','')

		# Parse responses based on cmd value
		#
		if cmd == '500':
  			print(u"ACK for cmd %s." % dat)
  			self.cmdAck = dat

		elif cmd == '501':
			print(u'IT-100/2DS Error: Received a command with a bad checksum')

		elif cmd == '502':
			errText = u'Unknown'

			if dat == '020':
				errText = u'API Command Syntax Error'
			elif dat == '022':
				errText = u'API Command Not Supported'
			elif dat == '023':
				errText = u'API System Not Armed (sent in response to a disarm command)'
			elif dat == '024':
				errText = u'API System Not Ready to Arm (not secure, in delay, or already armed)'
				self.triggerEvent(u'eventFailToArm')
			elif dat == '025':
				errText = u'API Command Invalid Length'
			elif dat == '026':
				errText = u'API User Code not Required'
			elif dat == '027':
				errText = u'API Invalid Characters in Command'

			print(u"IT-100/2DS Error (%s): %s" % (dat,errText))

		elif cmd == '505':
			if dat == '3':
				print(u'Received login request')

  		elif cmd == '510':
  			leds = int(dat,16)

  			if leds & 1 > 0:
  				self.updateKeypad(0, u'LEDReady', 'on')
  			else:
  				self.updateKeypad(0, u'LEDReady', 'off')

  			if leds & 2 > 0:
  				self.updateKeypad(0, u'LEDArmed', 'on')
  			else:
  				self.updateKeypad(0, u'LEDArmed', 'off')

  			if leds & 16 > 0:
  				self.updateKeypad(0, u'LEDTrouble', 'on')
  			else:
  				self.updateKeypad(0, u'LEDTrouble', 'off')

  		elif cmd == '550':

  			print("Got unexpected command 550")

   		elif cmd == '561' or cmd == '562':
			m = re.search(r'^(.)(...)$', dat)
			if m:
				(sensor,temp) = ( int(m.group(1)), int(m.group(2)) )
				if cmd == '562':
					self.updateSensorTemp(sensor, 'outside', temp)
				else:
					self.updateSensorTemp(sensor, 'inside', temp)
  		elif cmd == '563':
  			m = re.search(r'^(.)(...)(...)$', dat)
			if m:
				(sensor,cool,heat) = ( int(m.group(1)), int(m.group(2)), int(m.group(3)) )
				self.updateSensorTemp(sensor, 'cool', cool)
				self.updateSensorTemp(sensor, 'heat', heat)
  		elif cmd == '601':
			m = re.search(r'^(.)(...)$', dat)
			if m:
				(partition,zone) = ( int(m.group(1)), int(m.group(2)) )
  				self.updateZoneState(zone,kZoneStateTripped)
  				if zone not in self.trippedZoneList:
					self.trippedZoneList.append(zone)

   		elif cmd == '602':
			m = re.search(r'^(.)(...)$', dat)
			if m:
				(partition,zone) = ( int(m.group(1)), int(m.group(2)) )
				print(u"Zone %d Restored. (Partition %d)" % (zone,partition) )
   		elif cmd == '609':
   			zone = int(dat)
  			print(u"Zone number %d Open." % zone)
  			self.updateZoneState(zone,kZoneStateOpen)
  			if self.repeatAlarmTripped == True:
  				if zone in self.closeTheseZonesList:
  					self.closeTheseZonesList.remove(zone)

  		elif cmd == '610':
  			zone = int(dat)
  			print(u"Zone number %d Closed." % zone)
  			# Update the zone to closed ONLY if the alarm is not tripped
  			# We want the tripped states to be preserved so someone looking
  			# at their control page will see all the zones that have been
  			# opened since the break in.
  			if self.repeatAlarmTripped == False:
  				self.updateZoneState(zone,kZoneStateClosed)
  			else:
  				self.closeTheseZonesList.append(zone)

  		elif cmd == '620':
			print(u"Duress Alarm Detected")
  		elif cmd == '621':
			print(u"Fire Key Alarm Detected")
  		elif cmd == '623':
			print(u"Auxiliary Key Alarm Detected")
  		elif cmd == '625':
			print(u"Panic Key Alarm Detected")
  		elif cmd == '631':
			print(u"Auxiliary Input Alarm Detected")
  		elif cmd == '632':
			print(u"Auxiliary Input Alarm Restored")
  		elif cmd == '650':
			print(u"Partition %d Ready" % int(dat))
		elif cmd == '651':
			print(u"Partition %d Not Ready" % int(dat))
		elif cmd == '652':
			if len(dat) == 1:
				partition = int(dat)
				print(u"Alarm Armed. (Partition %d)" % partition )
				self.updateKeypad(partition, u'state', kAlarmStateArmed)
				#TODO: This response does not tell us armed type trigger.  Stay, Away, etc.  :(
			elif len(dat) == 2:
				m = re.search(r'^(.)(.)$', dat)
				if m:
					(partition,mode) = ( int(m.group(1)), int(m.group(2)) )
					print(u"Alarm Armed in %s mode. (Partition %d)" % (kArmedModeList[mode],partition) )
					if (mode == 0) or (mode == 2):
						armedEvent = u'armedAway'
					else:
						armedEvent = u'armedStay'
					self.triggerEvent(armedEvent)
					self.updateKeypad(partition, u'state', kAlarmStateArmed)
		elif cmd == '654':
			print(u"Alarm TRIPPED! (Partition %d)" % int(dat))
			self.updateKeypad(int(dat), u'state', kAlarmStateTripped)
			self.triggerEvent(u'eventAlarmTripped')
			self.repeatAlarmTrippedNext = time.time()
			self.repeatAlarmTripped = True
		elif cmd == '655':
			# If the alarm has been disarmed while it was tripped, update any zone states
			# that were closed during the break in.  We don't update them during the event
			# so that Indigo's zone states will represent a zone as tripped during the entire
			# event.
			if self.repeatAlarmTripped == True:
				self.repeatAlarmTripped = False
				for zone in self.closeTheseZonesList:
					self.updateZoneState(zone,kZoneStateClosed)
				self.closeTheseZonesList = []

			print(u"Alarm Disarmed. (Partition %d)" % int(dat))
			self.trippedZoneList = []
			self.updateKeypad(int(dat), u'state', kAlarmStateDisarmed)
			self.triggerEvent(u'eventAlarmDisarmed')

		elif cmd == '656':
			print(u"Exit Delay. (Partition %d)" % int(dat))
			self.updateKeypad(int(dat), u'state', kAlarmStateExitDelay)
		elif cmd == '657':
			print(u"Entry Delay. (Partition %d)" % int(dat))
			self.updateKeypad(int(dat), u'state', kAlarmStateEntryDelay)
		elif cmd == '672':
			print(u"Alarm Failed to Arm. (Partition %d)" % int(dat))
			self.triggerEvent(u'eventFailToArm')
		elif cmd == '673':
			print(u"Partition %d Busy." % int(dat))
		elif cmd == '700' or cmd == '701' or cmd == '702':
			m = re.search(r'^(.)(....)$', dat)
			if m:
				(partition,user) = ( int(m.group(1)), m.group(2) )
				print(u"Alarm armed by user %s. (Partition %d)" % (user,partition) )
		elif cmd == '750':
			m = re.search(r'^(.)(....)$', dat)
			if m:
				(partition,user) = ( int(m.group(1)), m.group(2) )
				print(u"Alarm disarmed by user %s. (Partition %d)" % (user,partition) )
		elif cmd == '840':
			print(u"Trouble Status (LED ON). (Partition %d)" % int(dat))
		elif cmd == '841':
			print(u"Trouble Status Restore (LED OFF). (Partition %d)" % int(dat))
		elif cmd == '851':
			print(u"Partition Busy Restore. (Partition %d)" % int(dat))
		elif cmd == '896':
			print(u"Keybus Fault")
		elif cmd == '897':
			print(u"Keybus Fault Restore")
		elif cmd == '901':
			#for char in dat:
			#	print(u"LCD DEBUG: %d" % ord(char))
			m = re.search(r'^...(..)(.*)$', dat)
			if m:
				lcdText = re.sub(r'[^ a-zA-Z0-9_/\:-]+', ' ', m.group(2))
				half = len(lcdText)/2
				half1 = lcdText[:half]
				half2 = lcdText[half:]
				print( u"LCD Update, Line 1:'%s' Line 2:'%s'" % (half1, half2))
				self.updateKeypad(0, u'LCDLine1', half1)
				self.updateKeypad(0, u'LCDLine2', half2)

		elif cmd == '903':
			m = re.search(r'^(.)(.)$', dat)
			if m:
				(ledName,ledState) = ( kLedIndexList[int(m.group(1))], kLedStateList[int(m.group(2))] )
				print(u"LED '%s' is '%s'." % (ledName,ledState))

				if ledState == 'flashing':
					ledState = 'on'

				if ledName == 'Ready':
					self.updateKeypad(0, u'LEDReady', ledState)
				elif ledName == 'Armed':
					self.updateKeypad(0, u'LEDArmed', ledState)
				elif ledName == 'Trouble':
					self.updateKeypad(0, u'LEDTrouble', ledState)

		elif cmd == '904':
			print(u"Beep Status")
		elif cmd == '905':
			print(u"Tone Status")
		elif cmd == '906':
			print(u"Buzzer Status")
		elif cmd == '907':
			print(u"Door Chime Status")
		elif cmd == '908':
			m = re.search(r'^(..)(..)(..)$', dat)
			if m:
				print(u"DSC Software Version %s.%s" % (m.group(1), m.group(2)) )
		else:
			print(u"Cmd:%s Dat:%s Sum:%d" % (cmd,dat,sum))

		return (cmd,dat)


	########################################
	# State Subs

	def updateSensorTemp(self, sensorNum, key, temp):
		if temp > 127:
			temp = 127 - temp
  		print(u"Temp sensor %d %s temp now %d degrees." % (sensorNum,key,temp))
		if sensorNum in self.tempList.keys():
			if key == 'inside':
				self.tempList[sensorNum].updateStateOnServer(key=u"temperatureInside", value=temp)
			elif key == 'outside':
				self.tempList[sensorNum].updateStateOnServer(key=u"temperatureOutside", value=temp)
			elif key == 'cool':
				self.tempList[sensorNum].updateStateOnServer(key=u"setPointCool", value=temp)
			elif key == 'heat':
				self.tempList[sensorNum].updateStateOnServer(key=u"setPointHeat", value=temp)

			if self.tempList[sensorNum].pluginProps['zoneLogChanges'] == 1:
				print(u"Temp sensor %d %s temp now %d degrees." % (sensorNum,key,temp))


	# Updates indigo variable instance var with new value varValue
	#
	def updateZoneState(self, zoneKey, newState):

		if zoneKey in self.zoneList.keys():
			zone = self.zoneList[zoneKey]
			zoneType = zone.pluginProps['zoneType']

			# If the new state is different from the old state
			# then lets update timers and set the new state
			if zone.states[u'state'] != newState:
				# This is a new state, update all states and timers
				zone.updateStateOnServer(key=u"LastChangedShort", value="0m")
				zone.updateStateOnServer(key=u"LastChangedTimer", value=0)

				# Check if this zone is assigned to an occupancy group so we can update it
				grp = int(zone.pluginProps['occupancyGroup'])

				if grp > 0:
					print(u"Updating group %u timer." % grp)
					self.updateKeypadTimers(grp)

			# Update zone state in Indigo Device
			zone.updateStateOnServer(key=u"state", value=newState)

			# If this is a door or window, see if we need to update our DoorOrWindowOpen variable
			if (zoneType == u'zoneTypeDoor') or (zoneType == u'zoneTypeWindow'):
				if newState == kZoneStateOpen:
					self.doorOrWindowOpen = True
					#print(u"DOOR OR WINDOW OPEN")
				else:
					# Loop through the doors and windows to see if they are all closed
					for thisZoneKey in self.zoneList.keys():
						thisZone = self.zoneList[thisZoneKey]
						thisZoneType = thisZone.pluginProps['zoneType']
						#If this is a window or door and it's open, break out of loop
						if ((thisZoneType == u'zoneTypeDoor') or (thisZoneType == u'zoneTypeWindow')) and thisZone.states[u'state'] == kZoneStateOpen:
							break
					else:
						#print(u"ALL DOORS AND WINDOWS CLOSED")
						self.doorOrWindowOpen = False
						self.doorOrWindowOpenTimer = 0
						self.updateKeypad(0, u'DoorOrWindowOpenTimer', self.doorOrWindowOpenTimer)

  			if newState == kZoneStateTripped:
				print(u"Alarm Zone '%s' TRIPPED!" % zone.name )

			if zone.pluginProps['zoneLogChanges'] == 1:
				if newState == kZoneStateOpen:
					print(u"Alarm Zone '%s' Opened." % zone.name )
				elif newState == kZoneStateClosed:
					print(u"Alarm Zone '%s' Closed." % zone.name )


	def updateKeypad(self, partition, stateName, newState):

		print(u"Updating state %s keypad on partition %u to %s." % (stateName,partition,newState))

		if partition == 0:
			for keyk in self.keypadList.keys():
				self.keypadList[keyk].updateStateOnServer(key=stateName, value=newState)
			return

		if partition in self.keypadList.keys():
			self.keypadList[partition].updateStateOnServer(key=stateName, value=newState)

	# Send 0 to increment all timers, or 1-5 to reset one of them
	#
	def updateKeypadTimers(self, action):

		# Loop through all keypads
		for key in self.keypadList.keys():
			keypad = self.keypadList[key]

			for i in range(6):
				# Build state key based on timer we are working with
				if i == 0:
					keyk = "OccupancyLastDetectedTimer"
				else:
					keyk = "".join(['OccupancyGroup',str(i),'LastDetectedTimer'])

				# If action is 0, increment all timers by 1
				# Otherwise, only reset timers 0 and "action"
				if action == 0:
					newVal = keypad.states[keyk] + 1
				else:
					newVal = 0
					if (i != 0) and (i != action):
						continue

				# Update the state in the Indigo keypad device
				keypad.updateStateOnServer(key=keyk, value=newVal)


	# TODO: this gets called on a lot of interesting events.
	#  add our own triggers here.
	def triggerEvent(self, eventId):

		return


	########################################
	# Action Subs
	# TODO: I think most of these are dead code. use or delete them

	def actionDisarm(self, action):
		print(u"Disarming alarm")
		self.txCmdList.append((kCmdNormal,tx))

	def actionArmStay(self, action):
		print(u"Arming alarm in stay mode.")
		self.txCmdList.append((kCmdNormal,'0311'))

	def actionArmAway(self, action):
		print(u"Arming alarm in away mode.")
		self.txCmdList.append((kCmdNormal,'0301'))

	def actionPanicAlarm(self, action):
		panicType = action.props[u'panicAlarmType']
		print(u"Activating Panic Alarm! (%s)" % kPanicTypeList[int(panicType)])
		self.txCmdList.append((kCmdNormal,'060' + panicType))

	def actionSendKeypress(self, action):
		print(u"Received Send Keypress Action")
		keys = action.props[u'keys']
		firstChar = True
		sendBreak = False
		for char in keys:
			if char == 'L':
				time.sleep(2)
				sendBreak = False

			if (firstChar == False):
				#self.sendPacket('070^')
				self.txCmdList.append((kCmdNormal,'070^'))

			if char != 'L':
				#self.sendPacket('070' + char)
				self.txCmdList.append((kCmdNormal,'070' + char))
				sendBreak = True

			firstChar = False
		if (sendBreak == True):
			#self.sendPacket('070^')
			self.txCmdList.append((kCmdNormal,'070^'))

	def actionResetOccupancyGroup(self, action):
		self.updateKeypadTimers(int(action.props[u'occupancyGroup']))

	def actionSyncTime(self, action):
		print(u"Setting DSC time and date to the same as the Indigo server (may take a few minutes).")
		d = datetime.now()
		#self.sendPacket(u"010%s" % d.strftime("%H%M%m%d%y"))
		self.txCmdList.append((kCmdNormal,u"010%s" % d.strftime("%H%M%m%d%y")))

	def actionAdjustThermostat(self, action):
		print(u"Device %s:" % action)
		self.txCmdList.append((kCmdThermoSet,action))

	def setThermostat(self, action):
		#find this thermostat in our list to get the number
		for sensorNum in self.tempList.keys():
			if self.tempList[sensorNum].id == action.deviceId:
				break

		print(u"SensorNum = %s" % sensorNum)

		#send 095 for thermostat in question, wait for 563 response
		#print(u'095' + str(sensorNum))
		rx = self.sendPacket(u'095' + str(sensorNum), waitFor='563')
		if len(rx) == 0:
			print('Error getting current thermostat setpoints, aborting adjustment.')
			return

		if (action.props[u'thermoAdjustmentType'] == u'+') or (action.props[u'thermoAdjustmentType'] == u'-'):
			sp = 0
		else:
			sp = int(action.props[u'thermoSetPoint'])

		# then 096TC+000 to inc cool,
		#      096Th-000 to dec heat
		#      096Th=### to set setpoint
		# wait for 563 response
		#print(u'096%u%c%c%03u' % (sensorNum, action.props[u'thermoAdjustWhich'], action.props[u'thermoAdjustmentType'],sp) )
		rx = self.sendPacket(u'096%u%c%c%03u' % (sensorNum, action.props[u'thermoAdjustWhich'], action.props[u'thermoAdjustmentType'],sp), waitFor='563')
		if len(rx) == 0:
			print('Error changing thermostat setpoints, aborting adjustment.')
			return

		# send 097T
		#send 097 for thermostat in question to save setting, wait for 563 response
		rx = self.sendPacket(u'097' + str(sensorNum), waitFor='563')
		if len(rx) == 0:
			print('Error saving thermostat setpoints, aborting adjustment.')
			return


	def getShortTime(self, minutes):

		# If time is less than an hour then show XXm
		if minutes < 60:
			return str(minutes) + 'm'
		# If it's less than one day then show XXh
		elif minutes < 1440:
			return str(int(minutes / 60)) + 'h'
		# If it's less than one hundred days then show XXd
		elif minutes < 43200:
			return str(int(minutes / 1440)) + 'd'
		# If it's anything more than one hundred days then show nothing
		else:
			return ''



	########################################
	# Concurrent Thread Start / Stop
	#
	def startComm(self):
		print(u"startComm called")
		self.minuteTracker = time.time() + 60

		# While Indigo hasn't told us to shutdown
		while self.shutdown == False:

			self.timeNow = time.time()

			if self.state == self.States.STARTUP:
				print(u"STATE: Startup")
				self.state = self.States.BOTH_INIT

			elif self.state == self.States.HOLD:
				time.sleep(1)

			elif self.state == self.States.HOLD_RETRY:
				print("Plugin will attempt to re-initialize again in %u minutes." % self.currentHoldRetryTime)
				self.nextRetryTime = self.timeNow + (kHoldRetryTimeMinutes*60)
				self.state = self.States.HOLD_RETRY_LOOP

			elif self.state == self.States.HOLD_RETRY_LOOP:
				if self.timeNow >= self.nextRetryTime:
					self.state = self.States.BOTH_INIT
				time.sleep(1)

			elif self.state == self.States.BOTH_INIT:
				if self.openPort() == True:
					self.state = self.States.BOTH_PING

				else:
					#print('Error opening port, will retry in %u minutes.' % self.currentHoldRetryTime)
					self.state = self.States.HOLD_RETRY

			elif self.state == self.States.SO_CONNECT:
				err = True

				# Read packet to clear the port of the 5053 login request
				self.readPacket()

				attemptLogin = True
				while attemptLogin == True:
					attemptLogin = False
					rx = self.sendPacket('005' + self.code, waitFor='505')
					if len(rx) == 0:
						print('Timeout waiting for 2DS to respond to login request.')
					else:
						rx = int(rx)
						if rx == 0:
							print('2DS refused login request.')
						elif rx == 1:
							err = False
							print("Connected to 2DS.")
						elif rx == 3:
							# 2DS sent login request, retry (Happens when socket is first opened)
							print(u"Received login request, retrying login...")
							attemptLogin = True
						else:
							print('Unknown response from 2DS login request.')

				# This delay is required otherwise 2DS locks up
				time.sleep(1)

				# Enable time broadcast
				if err == False:
					print("Enabling 2DS Time Broadcast")
					rx = self.sendPacket('0561')
					if len(rx) > 0:
						print(u"Time Broadcast enabled.")
					else:
						print(u'Error enabling Time Broadcast.')
						err = True

				if err == True:
					self.state = self.States.HOLD_RETRY
				else:
					self.state = self.States.BOTH_PING

			elif self.state == self.States.BOTH_PING:
				#Ping the panel to confirm we are in communication
				err = True
				print(u"Pinging the panel to test communication...")
				rx = self.sendPacket('000')
				if len(rx) > 0:
					print(u"Ping was successful.")
					err = False
				else:
					print('Error pinging panel, aborting.')

				if err == True:
					self.state = self.States.HOLD_RETRY
				else:
					#Request a full state update
					print("Requesting a full state update.")
					rx = self.sendPacket('001')
					if len(rx) == 0:
						print('Error getting state update.')
						self.state = self.States.HOLD_RETRY
					else:
						print("State update request successful, initialization complete, starting normal operation.")
						self.state = self.States.BOTH_POLL

			elif self.state == self.States.BOTH_POLL:
				if len(self.txCmdList) > 0:
					(cmdType,data) = self.txCmdList[0]
					if cmdType == kCmdNormal:
						txRsp = self.sendPacket(data)
						if txRsp == '-':
							# If we receive - socket has closed, lets re-init
							print('Tried to send data but socket seems to have closed.  Trying to re-initialize.')
							self.state = self.States.BOTH_INIT
						else:
							# send was a success, remove command from queue
							del self.txCmdList[0]

					elif cmdType == kCmdThermoSet:
						self.setThermostat(data)
				else:
					(rxRsp,rxData) = self.readPacket()
					if rxRsp == '-':
						# If we receive - socket has closed, lets re-init
						print('Tried to read data but socket seems to have closed.  Trying to re-initialize.')
						self.state = self.States.BOTH_INIT


			if self.repeatAlarmTripped == True:
				#timeNow = time.time()
				if self.timeNow >= self.repeatAlarmTrippedNext:
					self.repeatAlarmTrippedNext = self.timeNow + 12

			# If a minute has elapsed
			if self.timeNow >= self.minuteTracker:

				# Increment all zone changed timers
				self.minuteTracker += 60
				for zoneKey in self.zoneList.keys():
					zone = self.zoneList[zoneKey]
					tmr = zone.states[u"LastChangedTimer"] + 1
					zone.updateStateOnServer(key=u"LastChangedTimer", value=tmr)
					zone.updateStateOnServer(key=u"LastChangedShort", value=self.getShortTime(tmr))

				# Increment Door or Window open timer
				if self.doorOrWindowOpen == True:
					self.doorOrWindowOpenTimer += 1
					self.updateKeypad(0, u'DoorOrWindowOpenTimer', self.doorOrWindowOpenTimer)

				# Increment occupancy timers
				self.updateKeypadTimers(0)

		self.closePort()
		print(u"startComm Exit")


if __name__ == '__main__':
	dsc = DSC('/dev/ttyS0')
	dsc.startComm()
