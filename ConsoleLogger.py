# Copyright (C) 2011 by jedi95 <jedi95@gmail.com> and 
#                       CFSworks <CFSworks@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys
from time import time
from datetime import datetime

def formatNumber(n):
    """Format a positive integer in a more readable fashion."""
    if n < 0:
        raise ValueError('can only format positive integers')
    prefixes = 'KMGTP'
    whole = str(int(n))
    decimal = ''
    i = 0
    while len(whole) > 3:
        if i + 1 < len(prefixes):
            decimal = '.%s' % whole[-3:-1]
            whole = whole[:-3]
            i += 1
        else:
            break
    return '%s%s %s' % (whole, decimal, prefixes[i])
        
class ConsoleLogger(object):
    """This class will handle printing messages to the console."""
    
    TIME_FORMAT = '[%d/%m/%Y %H:%M:%S]'
    
    UPDATE_TIME = 1.0
    
    def __init__(self, miner, verbose=False): 
        self.verbose = verbose
        self.miner = miner
        self.lastUpdate = time() - 1
        self.rate = 0
        self.accepted = 0
        self.invalid = 0
        self.lineLength = 0
        self.connectionType = None
    
    def reportRate(self, rate, update=True):
        """Used to tell the logger the current Khash/sec."""
        self.rate = rate
        if update:
            self.updateStatus()
    
    def reportType(self, type):
        self.connectionType = type
    
    def reportBlock(self, block):
        self.log('Currently on block: ' + str(block))
        
    def reportFound(self, hash, accepted):
        if accepted:
            self.accepted += 1
        else:
            self.invalid += 1
        
        hexHash = hash[::-1]
        hexHash = hexHash[:8].encode('hex')
        if self.verbose:
            self.log('Result %s... %s' % (hexHash,
                'accepted' if accepted else 'rejected'))
        else:
            self.log('Result: %s %s' % (hexHash[8:],
                'accepted' if accepted else 'rejected'))
            
    def reportMsg(self, message):
        self.log(('MSG: ' + message), True, True)
    
    def reportConnected(self, connected):
        if connected:
            self.log('Connected to server')
        else:
            self.log('Disconnected from server')
    
    def reportConnectionFailed(self):
        self.log('Failed to connect, retrying...')
    
    def reportDebug(self, message):
        if self.verbose:
            self.log(message)
        
    def updateStatus(self, force=False):
        #only update if last update was more than a second ago
        dt = time() - self.lastUpdate
        if force or dt > self.UPDATE_TIME:
            rate = self.rate if (not self.miner.idle) else 0
            type = " [" + str(self.connectionType) + "]" if self.connectionType is not None else ''
            status = (
                "[" + formatNumber(rate) + "hash/sec] "
                "[" + str(self.accepted) + " Accepted] "
                "[" + str(self.invalid) + " Rejected]" + type)
            self.say(status)
            self.lastUpdate = time()
        
    def say(self, message, newLine=False, hideTimestamp=False):
        #add new line if requested
        if newLine:
            message += '\n'
            if hideTimestamp:
                timestamp = ''
            else:
                timestamp = datetime.now().strftime(self.TIME_FORMAT) + ' '
                
            message = timestamp + message
        
        #erase the previous line
        if self.lineLength > 0:
            sys.stdout.write('\b \b' * self.lineLength)
            sys.stdout.write(' ' * self.lineLength)
            sys.stdout.write('\b \b' * self.lineLength)

        #print the line
        sys.stdout.write(message)
        sys.stdout.flush()
        
        #cache the current line length
        if newLine:
            self.lineLength = 0
        else:
            self.lineLength = len(message)

    def log(self, message, update=True, hideTimestamp=False):
        self.say(message, True, hideTimestamp)
        if update:
            self.updateStatus(True)
        