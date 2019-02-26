#!/usr/bin/env python3

""" Wemo Node Server for ISY """

import sys
import socket
import logging
import polyinterface
import pywemo

LOGGER = polyinterface.LOGGER

class Control(polyinterface.Controller):
    """ Polyglot Controller for Wemo Node Server """

    def __init__(self, polyglot):
        super().__init__(polyglot)
        self.name = 'Wemo Node Server'
        self.address = 'wemons'
        self.primary = self.address
        self.subscription_registry = pywemo.SubscriptionRegistry()
        LOGGER.debug('Wemo Controler Initialized')

    def start(self):
        LOGGER.debug('Starting ' + self.name)
        self.discover()
        self.subscription_registry.start()

    def stop(self):
        LOGGER.debug('Wemo NodeServer is stopping')
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
                address = wemodev.mac
                self.addNode(WemoSwitch(self, self.address, address, wemodev.name, wemodev, self.subscription_registry))

    id = 'WEMO_CTRL'
    commands = {'DISCOVER': discover}
    drivers = [{'driver': 'ST', 'value': 1, 'uom': 2}]



class WemoSwitch(polyinterface.Node):

    def __init__(self, controller, primary, address, name, wemodev, subregistry=None):
        super().__init__(controller, primary, address, name)
        self.device = wemodev
        if subregistry is not None:
            self.sreg = subregistry
            subregistry.register(self.device)
            subregistry.on(wemodev, 'BinaryState', self.onchange)
        self.st = False

    def onchange(self, wemodev, type, value):
        if value == '1':
            self.st = True
            self.reportCmd('DON')
            self.setDriver('ST', 1)
        else:
            self.st = False
            self.reportCmd('DOF')
            self.setDriver('ST', 0)

    def don(self):
        try:
            self.device.on()
        except Exception as ex:
            LOGGER.debug('Call to turn switch on failed with exception:')
            LOGGER.debug(ex)
            return False
        self.st = True
        self.setDriver('ST', 1)
        return True

    def dof(self):
        try:
            self.device.off()
        except Exception as ex:
            LOGGER.debug('Call to turn switch off failed with exception:')
            LOGGER.debug(ex)
            return False
        self.st = False
        self.setDriver('ST', 0)
        return True

    def updateInfo(self):
        if self.st:
            self.setDriver('ST', 1)
        else:
            self.setDriver('ST', 0)

    def _getstate(self):
        try:
            tval = self.device.basicevent.GetBinaryState()
            rval = tval['BinaryState'] != '0'
        except Exception as ex:
            LOGGER.debug('Call to get status failed with exception:')
            LOGGER.debug(ex)
            rval = False
        self.st = rval
        return rval

    def query(self, command=None):
        self.ts = self._getstate()
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
        poly = polyinterface.Interface("MyWemo")
        LOGGER.debug("Starting Poly")
        poly.start()
        LOGGER.debug("Getting Control")
        wemo = Control(poly)
        LOGGER.debug("Starting Control")
        wemo.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
