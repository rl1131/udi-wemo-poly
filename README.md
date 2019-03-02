# Polyglot v2 Node Server for Wemo Switches

[![license](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/rl1131/udi-wemo-poly/blob/master/LICENSE)

This [Polyglot v2](https://github.com/UniversalDevicesInc/polyglot-v2) node server provides an interface between the ISY home automation controller from Universal Devices Inc. and Wemo WiFi switches.

### Installation instructions

You can install this node server by manually running
```
cd ~/.polyglot/nodeservers
git clone https://github.com/rl1131/udi-wemo-poly.git udi-wemo-poly
cd udi-wemo-poly
./install.sh
```

After that is complete use the Polyglot web interface to add the node server.

### Requirements and Attribution

This node server is dependent Greg Dowling's [pywemo](https://github.com/pavoni/pywemo) Python module.
