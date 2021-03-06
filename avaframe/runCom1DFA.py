"""
    Run script for running Standalone DFA
    This file is part of Avaframe.
"""

# Load modules
import os

# Local imports
from avaframe.com1DFA import com1DFA
from avaframe.in3Utils import cfgUtils
from avaframe.in3Utils import logUtils


# log file name; leave empty to use default runLog.log
logName = 'runCom1DFA'

# Load avalanche directory from general configuration file
cfgMain = cfgUtils.getGeneralConfig()
avalancheDir = cfgMain['MAIN']['avalancheDir']

# Start logging
log = logUtils.initiateLogger(avalancheDir, logName)
log.info('MAIN SCRIPT')
log.info('Current avalanche: %s', avalancheDir)

# Load input parameters from configuration file
cfg = cfgUtils.getModuleConfig(com1DFA)

# Run Standalone DFA
com1DFA.runSamos(cfg, avalancheDir)
