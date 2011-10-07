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

import os
from struct import pack, unpack
from hashlib import sha256
from twisted.internet import defer, reactor

# I'm using this as a sentinel value to indicate that an option has no default;
# it must be specified.
REQUIRED = object()

class KernelOption(object):
    """This works like a property, and is used in defining easy option tables
    for kernels.
    """
    
    def __init__(self, name, type, help=None, default=REQUIRED,
        advanced=False, **kwargs):
        self.localValues = {}
        self.name = name
        self.type = type
        self.help = help
        self.default = default
        self.advanced = advanced
    
    def __get__(self, instance, owner):
        if instance in self.localValues:
            return self.localValues[instance]
        else:
            return instance.interface._getOption(
                self.name, self.type, self.default)
    
    def __set__(self, instance, value):
        self.localValues[instance] = value

class CoreInterface(object):
    """An internal class provided for kernels to use when reporting info for
    one core.
    
    Only KernelInterface should create this.
    """
    
    def __init__(self, kernelInterface):
        self.kernelInterface = kernelInterface
        self.averageSamples = []
        self.kernelInterface.miner._addCore(self)
    
    def updateRate(self, rate):
        """Called by a kernel core to report its current rate."""
        
        numSamples = self.kernelInterface.miner.options.getAvgSamples()
        
        self.averageSamples.append(rate)
        self.averageSamples = self.averageSamples[-numSamples:]
        
        self.kernelInterface.miner.updateAverage()
    
    def getRate(self):
        """Retrieve the average rate for this core."""
        
        if not self.averageSamples:
            return 0
        
        return sum(self.averageSamples)/len(self.averageSamples)
    
    def getKernelInterface(self):
        return self.kernelInterface
        
class KernelInterface(object):
    """This is an object passed to kernels as an API back to the Phoenix
    framework.
    """
    
    def __init__(self, miner):
        self.miner = miner
        self._core = None
        
    def _getOption(self, name, type, default):
        """KernelOption uses this to read the actual value of the option."""
        if not name in self.miner.options.kernelOptions:
            if default == REQUIRED:
                self.fatal('Required option %s not provided!' % name)
            else:
                return default
        
        givenOption = self.miner.options.kernelOptions[name]
        if type == bool:
            # The following are considered true
            return givenOption is None or \
                givenOption.lower() in ('t', 'true', 'on', '1', 'y', 'yes')
        
        try:
            return type(givenOption)
        except (TypeError, ValueError):
            self.fatal('Option %s expects a value of type %s!' % (name, type))
    
    def getRevision(self):
        """Return the Phoenix core revision, so that kernels can require a
        minimum revision before operating (such as if they rely on a certain
        feature added in a certain revision)
        """
        
        return self.miner.REVISION
    
    def setWorkFactor(self, workFactor):
        """Deprecated. Kernels are now responsible for requesting optimal size
        work"""
    
    def setMeta(self, var, value):
        """Set metadata for this kernel."""
        
        self.miner.connection.setMeta(var, value)
    
    def fetchRange(self, size=None):
        """Fetch a range from the WorkQueue, optionally specifying a size
        (in nonces) to include in the range.
        """
        
        if size is None:
            return self.miner.queue.fetchRange()
        else:
            return self.miner.queue.fetchRange(size)
    
    def addStaleCallback(self, callback):
        """Register a new function to be called, with no arguments, whenever
        a new block comes out that would render all previous work stale,
        requiring a kernel to switch immediately.
        """
        
        # This should be implemented in a better way in the future...
        if callback not in self.miner.queue.staleCallbacks:
            self.miner.queue.staleCallbacks.append(callback)
    
    def removeStaleCallback(self, callback):
        """Undo an addStaleCallback."""
        
        # Likewise.
        if callback in self.miner.queue.staleCallbacks:
            self.miner.queue.staleCallbacks.remove(callback)
    
    def addCore(self):
        """Return a CoreInterface for a new core."""
        return CoreInterface(self)
    
    def checkTarget(self, hash, target):
        """Utility function that the kernel can use to see if a nonce meets a
        target before sending it back to the core.
        
        Since the target is checked before submission anyway, this is mostly
        intended to be used in hardware sanity-checks.
        """
        
        # This for loop compares the bytes of the target and hash in reverse
        # order, because both are 256-bit little endian.
        for t,h in zip(target[::-1], hash[::-1]):
            if ord(t) > ord(h):
                return True
            elif ord(t) < ord(h):
                return False
        return True
 
    def calculateHash(self, nr, nonce):
        """Given a NonceRange and a nonce, calculate the SHA-256 hash of the
        solution. The resulting hash is returned as a string, which may be
        compared with the target as a 256-bit little endian unsigned integer.
        """
        # Sometimes kernels send weird nonces down the pipe. We can assume they
        # accidentally set bits outside of the 32-bit space. If the resulting
        # nonce is invalid, it will be caught anyway...
        nonce &= 0xFFFFFFFF
    
        staticDataUnpacked = unpack('<' + 'I'*19, nr.unit.data[:76])
        staticData = pack('>' + 'I'*19, *staticDataUnpacked)
        hashInput = pack('>76sI', staticData, nonce)
        return sha256(sha256(hashInput).digest()).digest()
    
    def foundNonce(self, nr, nonce):
        """Called by kernels when they may have found a nonce."""
        
        # Sometimes kernels send weird nonces down the pipe. We can assume they
        # accidentally set bits outside of the 32-bit space. If the resulting
        # nonce is invalid, it will be caught anyway...
        nonce &= 0xFFFFFFFF
        
        # Check if the block has changed while this NonceRange was being
        # processed by the kernel. If so, don't send it to the server.
        if self.miner.queue.isRangeStale(nr):
            return False
        
        # Check if the hash meets the full difficulty before sending.
        hash = self.calculateHash(nr, nonce)
 
        if self.checkTarget(hash, nr.unit.target):
            formattedResult = pack('<76sI', nr.unit.data[:76], nonce)
            d = self.miner.connection.sendResult(formattedResult)
            def callback(accepted):
                self.miner.logger.reportFound(hash, accepted)
            d.addCallback(callback)
            return True
        else:
            self.miner.logger.reportDebug("Result didn't meet full "
                   "difficulty, not sending")
            return False
    
    def debug(self, msg):
        """Log information as debug so that it can be viewed only when -v is
        enabled.
        """
        self.miner.logger.reportDebug(msg)
    
    def log(self, msg, withTimestamp=True, withIdentifier=True):
        """Log some general kernel information to the console."""
        self.miner.logger.log(msg, True, not withTimestamp)
    
    def error(self, msg=None):
        """The kernel has an issue that requires user attention."""
        if msg is not None:
            self.miner.logger.log('Kernel error: ' + msg)
    
    def fatal(self, msg=None):
        """The kernel has an issue that is preventing it from continuing to
        operate.
        """
        if msg is not None:
            self.miner.logger.log('FATAL kernel error: ' + msg, False)
        if reactor.running:
            reactor.stop()
        os._exit(0)
    