#!/usr/bin/env python3

""" Wemo Node Server for ISY Polyglot """

import sys
import socket
import logging
import polyinterface
from time import sleep
from datetime import datetime

LOGGER = polyinterface.LOGGER
LOGGER.info('Wemo node server running on Python version {}'.format(sys.version_info))

import pywemo


class Control(polyinterface.Controller):
    """ Polyglot Controller for Wemo Node Server """
    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'Wemo Node Server'
        self.address = 'wemons'
        self.primary = self.address
        self.subscription_registry = pywemo.SubscriptionRegistry()
        LOGGER.info('Wemo Controler Initialized')

    def start(self):
        LOGGER.info('Starting ' + self.name)
        self.discover()
        self.subscription_registry.start()

    def stop(self):
        LOGGER.info('Wemo NodeServer is stopping')
        self.subscription_registry.stop()

    def shortPoll(self):
        for node in self.nodes.values():
            node.updateInfo()

    def updateInfo(self):
        pass

    def query(self, command=None):
        for node in self.nodes:
            self.nodes[node].reportDrivers()

    def discover(self, command=None):
        devices = pywemo.discover_devices()
        for wemodev in devices:
            LOGGER.info('Wemo Device {} of type {} found, checking for compatibility...'.format(wemodev.name, wemodev.device_type));
            if wemodev.device_type in ['LightSwitch', 'Switch']:
                LOGGER.info('Adding {} {} to ISY.'.format(wemodev.device_type, wemodev.name))
                address = wemodev.mac.lower()
                self.addNode(WemoSwitch(self, self.address, address, wemodev.name, wemodev, self.subscription_registry))
            elif wemodev.device_type == 'Dimmer':
                LOGGER.info('Adding {} {} to ISY.'.format(wemodev.device_type, wemodev.name))
                address = wemodev.mac.lower()
                self.addNode(WemoDimmer(self, self.address, address, wemodev.name, wemodev, self.subscription_registry))
            elif wemodev.device_type == 'Insight':
                LOGGER.info('Adding {} {} to ISY.'.format(wemodev.device_type, wemodev.name))
                address = wemodev.mac.lower()
                self.addNode(WemoInsight(self, self.address, address, wemodev.name, wemodev, self.subscription_registry))
            else:
                LOGGER.warning('WARNING Device type {} is not currently supported.'.format(wemodev.name, wemodev.device_type));

    id = 'WEMO_CTRL'
    commands = {'DISCOVER': discover}
    drivers = [{'driver': 'ST', 'value': 1, 'uom': 2}]



class WemoSwitch(polyinterface.Node):
    """ Polyglot for Wemo Switch """
    def __init__(self, controller, primary, address, name, wemodev, subregistry=None):
        super().__init__(controller, primary, address, name)
        self.device = wemodev
        if subregistry is not None:
            self.sreg = subregistry
            subregistry.register(self.device)
            subregistry.on(wemodev, None, self._onchange)
        self.on_state = False

    def _onchange(self, wemodev, type, value):
        """ Callback for notification from the switch that the switch status changed """
        if type == 'BinaryState':
            if value == '1':
                if not self.on_state:
                    self.on_state = True
                    self.reportCmd('DON')
                    self.setDriver('ST', 100)
            else:
                if self.on_state:
                    self.on_state = False
                    self.reportCmd('DOF')
                    self.setDriver('ST', 0)


    def _getstate(self):
        """ Query the switch's current state """
        try:
            rval = self.device.basicevent.GetBinaryState()
        except Exception as ex:
            LOGGER.error('Call to get status failed with exception: {}'.format(ex))
            rval = None
        return rval

    def updateInfo(self):
        """ Get current switch status.  If it is doesn't match our
            status value then assume someone changed it remotely """
        wemost = self._getstate()
        if wemost is not None:
            newst = wemost['BinaryState'] != '0'
        else:
            newst = self.on_state
        if newst != self.on_state:
            self.on_state = newst
            if self.on_state:
                self.reportCmd('DON')
            else:
                self.reportCmd('DOF')
        self.setDriver('ST', 100 if self.on_state else 0)

    def don(self, command=None):
        """ ISY Request the device be turned on """
        try:
            self.device.on()
            LOGGER.info('don {} turned on'.format(self.device.name))
        except Exception as ex:
            LOGGER.error('Call to turn switch on failed with exception: {}'.format(ex))
            return False
        self.on_state = True
        self.setDriver('ST', 100)
        return True

    def dof(self, command=None):
        """ ISY Request the device be turned off """
        try:
            self.device.off()
            LOGGER.info('dof {} turned off'.format(self.device.name))
        except Exception as ex:
            LOGGER.error('Call to turn switch off failed with exception: {}'.format(ex))
            return False
        self.on_state = False
        self.setDriver('ST', 0)
        return True

    def query(self, command=None):
        """ ISY Requested that we query the remote device """
        LOGGER.info('query of {} requested'.format(self.device.name))
        wemost = self._getstate()
        if wemost is not None:
            self.on_state = wemost['BinaryState'] != '0'
        self.setDriver('ST', 100 if self.on_state else 0)
        self.reportDrivers()
        return True

    drivers = [ {'driver': 'ST', 'value': 0, 'uom': 78} ]

    commands = {
                   'DON': don, 
                   'DOF': dof, 
                   'DFON': don, 
                   'DFOF': dof, 
                   'QUERY': query
               }

    id = 'WEMO_SWITCH'


class WemoDimmer(polyinterface.Node):
    BRIGHT_MAX = 100
    LEVEL_INCREMENT = 5

    """ Polyglot for Wemo Dimmer """
    def __init__(self, controller, primary, address, name, wemodev, subregistry=None):
        super().__init__(controller, primary, address, name)
        self.device = wemodev
        if subregistry is not None:
            self.sreg = subregistry
            subregistry.register(self.device)
            subregistry.on(wemodev, None, self._onchange)
        self.on_level = self.BRIGHT_MAX
        self.on_state = False

    def _getstate(self):
        """ Query the device's current state """
        try:
            rval = self.device.basicevent.GetBinaryState()
        except Exception as ex:
            LOGGER.error('Call to get status failed with exception: {}'.format(ex))
            rval = None
        return rval

    def _onchange(self, wemodev, type, value):
        """ Callback for notification from the device that the device status changed """
        if type == 'Brightness':
            self.on_level = int(value)
        elif type == 'BinaryState':
            if value == '1':
                if not self.on_state:
                    self.on_state = True
                    self.reportCmd('DON')
                    self.setDriver('ST', 100 if self.on_state else 0)
            else:
                if self.on_state:
                    self.on_state = False
                    self.reportCmd('DOF')
                    self.setDriver('ST', 0)
        self.setDriver('GV0', self.on_level)

    def updateInfo(self):
        """ Get current device status.  If it is doesn't match our
            status value then assume someone changed it remotely """
        wemost = self._getstate()
        if wemost is not None:
            onst = wemost['BinaryState'] != '0'
            self.on_level = int(wemost['brightness'])

            if onst != self.on_state:
                self.on_state = onst
                if onst:
                    self.reportCmd('DON')
                else:
                    self.reportCmd('DOF')

        self.setDriver('ST', 100 if self.on_state else 0)
        self.setDriver('GV0', self.on_level)
        
    def don(self, command=None):
        """ ISY Request the device be turned on """
        cmd = command.get('cmd')
        val = command.get('value')

        if cmd == 'DFON':
            level = self.BRIGHT_MAX
        else:
            if val:
                level = int(val)
            else:
                level = self.on_level

        if level > self.BRIGHT_MAX:
            level = self.BRIGHT_MAX
            
        try:
            self.device.set_brightness(level)
        except Exception as ex:
            LOGGER.error('Bulb {} failed to turn on {}'.format(self.name, ex))
            return

        self.on_level = level
        self.on_state = True
        self.setDriver('ST', 100 if self.on_state else 0)
        self.setDriver('GV0', self.on_level)
        return True

    def dof(self, command=None):
        """ ISY Request the device be turned off """
        try:
            self.device.off()
            LOGGER.info('dof {} turned off'.format(self.device.name))
        except Exception as ex:
            LOGGER.error('Call to turn switch off failed with exception: {}'.format(ex))
            return False
        self.on_state = False
        self.setDriver('ST', 0)
        return True

    def brt_dim(self, command=None):
        cmd = command.get('cmd')
        value = self.on_level
        if self.on_state:
            if cmd == "BRT":
                increment = self.LEVEL_INCREMENT
            elif cmd == "DIM":
                increment = 0 - self.LEVEL_INCREMENT
            else:
                return False
            value += increment
            value = max(value, 0)
            value = min(value, self.BRIGHT_MAX)
        if value > 0:
            self.don({'cmd' : 'DON', 'value' : value})
        else:
            self.dof({'cmd' : 'DON', 'value' : value})
        return True

    def query(self, command=None):
        """ ISY Requested that we query the remote device """
        LOGGER.info('query of {} requested'.format(self.device.name))
        wemost = self._getstate()
        if wemost is not None:
            onst = wemost['BinaryState'] != '0'
            self.on_level = int(wemost['brightness'])
            self.setDriver('ST', 100 if self.on_state else 0)
            self.setDriver('GV0', self.on_level)
            self.reportDrivers()
        return True

    drivers = [ 
                {'driver': 'ST',   'value': 0, 'uom': 78},
                {'driver': 'GV0',  'value': BRIGHT_MAX, 'uom': 51},
              ]

    commands = {
                 'DON': don, 
                 'DOF': dof, 
                 'DFON': don, 
                 'DFOF': dof, 
                 'BRT': brt_dim, 
                 'DIM': brt_dim,
                 'QUERY': query,
               }

    id = 'WEMO_DIMMER'
    
    """ DIMMER DEVELOPMENT NOTES:
            Fader:  
                faderState -> Switch
                faderTime -> Number or Dimmer, setpoint in UI
                faderStart -> DateTime
                nightMode -> Switch
                startTime -> DateTime
                endTime -> DateTime
                nightModeBrightness -> Dimmer
    """


def InsightUpdate(device, update_string):
    """ The PyWemo Insight object doesn't parse or use the string returned by
        a subscription to the device updates.  So, this function is a hack to
        add that support without modifying the actual PyWemo module.  This is
        (effectively) identical to the provided functions update_insight_params
        and parse_insight_params with the exception that this function is not 
        provided the last data point of threshold.  At some point I should/will
        do a pull request with some minor changes/fixes :-) """
    (
        state,  # 0 if off, 1 if on, 8 if on but load is off
        lastchange,
        onfor,
        ontoday,
        ontotal,
        timeperiod,
        _x,  # ???
        currentmw,
        todaymw,
        totalmw
    ) = update_string.split('|')
    device.insight_params['state'] = state
    device.insight_params['lastchange'] = datetime.fromtimestamp(int(lastchange))
    device.insight_params['onfor'] = int(onfor)
    device.insight_params['ontoday'] = int(ontoday)
    device.insight_params['ontotal'] = int(ontotal)
    device.insight_params['todaymw'] = int(float(todaymw))
    device.insight_params['totalmw'] = int(float(totalmw))
    device.insight_params['currentpower'] = int(float(currentmw))


class WemoInsight(polyinterface.Node):
    """ Polyglot for Wemo Insight """
    STATE_ON  = 1
    STATE_OFF = 0
    STATE_STBY = 8

    state_transitions = { (0,1) : 'DON',   # Physically switched on + Threshold met (Doesn't happen)
                          (0,8) : 'DON',   # Physically switched on + Threshold not met (or still measuring)
                          (8,1) : 'GV10',  # Threshold triggered high
                          (8,0) : 'DOF',   # Physically switched off
                          (1,8) : 'GV11',  # Threshold triggered low
                          (1,0) : 'DOF',   # Physically switched off
                        }

    def __init__(self, controller, primary, address, name, wemodev, subregistry=None):
        super().__init__(controller, primary, address, name)
        self.device = wemodev
        self.sreg = subregistry
        self.on_state = 0
        self.ignore_callback = False

    def start(self):
        if self.sreg is not None:
            self.sreg.register(self.device)
            self.sreg.on(self.device, None, self._onchange)
        self.updateInfo()

    def _onchange(self, wemodev, type, value):
        """ Callback for notification from the device that the status changed """
        if self.ignore_callback:
            return
        if type == 'BinaryState':
            old_on_state = self.on_state
            try:
                InsightUpdate(self.device, value)
                self._updateState()
                if old_on_state != self.on_state:
                    self.reportCmd(WemoInsight.state_transitions[(old_on_state, self.on_state)])
            except Exception as ex:
                LOGGER.error('Attempt to update state failed in _onchange exception: {}'.format(ex))
                rval = None

    def _getstate(self):
        """ Query the device's current state """
        try:
            self.device.update_insight_params()
        except Exception as ex:
            LOGGER.error('Call to get status failed with exception: {}'.format(ex))

    def _updateState(self):
        self.on_state = int(self.device.insight_params['state'])
        self.setDriver('ST', 100 if self.on_state != 0 else 0)
        self.setDriver('GV0', self.device.on_for)
        self.setDriver('GV1', int(self.device.current_power / 1000))
        self.setDriver('GV2', self.device.today_on_time)
        self.setDriver('GV3', int(self.device.today_kwh * 60 * 60))  # Convert from KWh to KWs
        self.setDriver('GV6', self.device.threshold_power / 1000)
        self.setDriver('GV7', 1 if self.on_state == 1 else 0)
        self.reportDrivers()

    def updateInfo(self):
        """ Get current device status.  If it is doesn't match our
            status value then assume someone changed it remotely """
        self._getstate()
        self._updateState()

    def onoff(self, command=None):
        """ ISY Request the device be turned on """
        cmd = command.get('cmd')
        self.ignore_callback = True
        try:
            if cmd == 'DON' or cmd == 'DFON':
                self.device.on()
            elif cmd == 'DOF' or cmd == 'DFOF':
                self.device.off()
            else:
                raise Exception('Unkown command given to onoff:  {}'.format(command))
            sleep(0.25)
            self.updateInfo()
            self.ignore_callback = False
            LOGGER.info('Device {} turned {}'.format(self.device.name, cmd))
        except Exception as ex:
            self.ignore_callback = False
            LOGGER.error('Call to onoff failed with exception: {}'.format(ex))
            return False
        return True

    def query(self, command=None):
        """ ISY Requested that we query the remote device """
        LOGGER.info('query of {} requested'.format(self.device.name))
        self.updateInfo()
        return True

    drivers = [ 
                {'driver': 'ST', 'value':  0, 'uom': 78},
                {'driver': 'GV0', 'value': 0, 'uom': 58},  # <!-- Time On -->
                {'driver': 'GV1', 'value': 0, 'uom': 73},  # <!-- Watts Currently -->
                {'driver': 'GV2', 'value': 0, 'uom': 58},  # <!-- Time On Today -->
                {'driver': 'GV3', 'value': 0, 'uom': 102},  # <!-- Watts Used Today -->
                #{'driver': 'GV4', 'value': 0, 'uom': 58},  # <!-- Total Time On -->
                #{'driver': 'GV5', 'value': 0, 'uom': 73},  # <!-- Total Watts Used -->
                {'driver': 'GV6', 'value': 0, 'uom': 73},  # <!-- Threshold in Watts -->
                {'driver': 'GV7', 'value': 0, 'uom': 2},   # <!-- Currently Above Threshold? -->
              ]

    commands = {
                 'DON': onoff, 
                 'DOF': onoff, 
                 'DFON': onoff, 
                 'DFOF': onoff, 
                 'QUERY': query,
               }
               
    id = 'WEMO_INSIGHT'
    
    
    
if __name__ == "__main__":
    try:
        LOGGER.debug("Getting Poly")
        poly = polyinterface.Interface("Wemo")
        LOGGER.debug("Starting Poly")
        poly.start()
        LOGGER.debug("Getting Control")
        wemo = Control(poly)
        LOGGER.debug("Starting Control")
        wemo.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
