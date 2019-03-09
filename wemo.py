#!/usr/bin/env python3

""" Wemo Node Server for ISY """

import sys
import socket
import logging
import polyinterface

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
            if wemodev.device_type == 'LightSwitch':
                LOGGER.info('Wemo LighSwitch {} found. Adding to ISY if necessary.'.format(wemodev.name))
                address = wemodev.mac.lower()
                self.addNode(WemoSwitch(self, self.address, address, wemodev.name, wemodev, self.subscription_registry))

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
            subregistry.on(wemodev, 'BinaryState', self._onchange)
        self.st = False

    def _onchange(self, wemodev, type, value):
        """ Callback for notification from the switch that the switch status changed """
        if value == '1':
            if not self.st:
                self.st = True
                self.reportCmd('DON')
                self.setDriver('ST', 1)
        else:
            if self.st:
                self.st = False
                self.reportCmd('DOF')
                self.setDriver('ST', 0)

    def _getstate(self):
        """ Query the switch's current state """
        try:
            tval = self.device.basicevent.GetBinaryState()
            rval = tval['BinaryState'] != '0'
            LOGGER.debug('_getstate for {} returned {}'.format(self.device.name, tval))
        except Exception as ex:
            LOGGER.error('Call to get status failed with exception:')
            LOGGER.error(ex)
            rval = False
        return rval

    def updateInfo(self):
        """ Get current switch status.  If it is doesn't match our
            status value then assume someone changed it remotely """
        oldst = self.st
        self.st = self._getstate()
        if self.st != oldst:
            if self.st:
                self.reportCmd('DON')
            else:
                self.reportCmd('DOF')
        newv = 1 if self.st else 0
        self.setDriver('ST', newv)

    def don(self, command=None):
        """ ISY Request the device be turned on """
        try:
            self.device.on()
            LOGGER.debug('don {} turned on'.format(self.device.name))
        except Exception as ex:
            LOGGER.debug('Call to turn switch on failed with exception:')
            LOGGER.debug(ex)
            return False
        self.st = True
        self.setDriver('ST', 1)
        return True

    def dof(self, command=None):
        """ ISY Request the device be turned off """
        try:
            self.device.off()
            LOGGER.debug('dof {} turned off'.format(self.device.name))
        except Exception as ex:
            LOGGER.debug('Call to turn switch off failed with exception:')
            LOGGER.debug(ex)
            return False
        self.st = False
        self.setDriver('ST', 0)
        return True

    def query(self, command=None):
        """ ISY Requested that we query the remote device """
        LOGGER.debug('query of {} requested'.format(self.device.name))
        self.st = self._getstate()
        self.updateInfo()
        self.reportDrivers()
        return True

    drivers = [ {'driver': 'ST', 'value': 0, 'uom': 2} ]

    commands = {
                   'DON': don, 
                   'DOF': dof, 
                   'QUERY': query
               }

    id = 'WEMO_SWITCH'


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
