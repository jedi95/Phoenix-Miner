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

from minerutil.Midstate import calculateMidstate
from twisted.internet import defer
from collections import deque

"""A WorkUnit is a single unit containing 2^32 nonces. A single getWork
request returns a WorkUnit.
"""
class WorkUnit(object):
    data = None
    target = None
    midstate = None
    nonces = None
    base = None
    identifier = None

"""A NonceRange is a range of nonces from a WorkUnit, to be dispatched in a
single execution of a mining kernel. The size of the NonceRange can be
adjusted to tune the performance of the kernel.

This class doesn't actually do anything, it's just a well-defined container
that kernels can pull information out of.
"""
class NonceRange(object):

    def __init__(self, unit, base, size):
        self.unit = unit # The WorkUnit this NonceRange comes from.
        self.base = base # The base nonce.
        self.size = size # How many nonces this NonceRange says to test.


class WorkQueue(object):
    """A WorkQueue contains WorkUnits and dispatches NonceRanges when requested
    by the miner. WorkQueues dispatch deffereds when they runs out of nonces.
    """

    def __init__(self, miner, options):

        self.miner = miner
        self.queueSize = options.getQueueSize()
        self.logger = options.makeLogger(self, miner)

        self.queue = deque('', self.queueSize)
        self.deferredQueue = deque()
        self.currentUnit = None
        self.block = ''
        self.lastBlock = None

        # This is set externally. Not the best practice, but it can be changed
        # in the future.
        self.staleCallbacks = []

    # Called by foundNonce to check if a NonceRange is stale before submitting
    def isRangeStale(self, nr):
        return (nr.unit.identifier != self.block)

    def storeWork(self, aw):

        #check if this work matches the previous block
        if self.lastBlock is not None and (aw.identifier == self.lastBlock):
            self.logger.reportDebug('Server gave work from the previous '
                                    'block, ignoring.')
            #if the queue is too short request more work
            if (len(self.queue)) < (self.queueSize):
                self.miner.connection.requestWork()
            return

        #create a WorkUnit
        work = WorkUnit()
        work.data = aw.data
        work.target = aw.target
        work.midstate = calculateMidstate(work.data[:64])
        work.nonces = 2 ** aw.mask
        work.base = 0
        work.identifier = aw.identifier

        #check if there is a new block, if so reset queue
        newBlock = (aw.identifier != self.block)
        if newBlock:
            self.queue.clear()
            self.currentUnit = None
            self.lastBlock = self.block
            self.block = aw.identifier
            self.logger.reportDebug("New block (WorkQueue)")

        #clear the idle flag since we just added work to queue
        self.miner.reportIdle(False)

        #add new WorkUnit to queue
        if work.data and work.target and work.midstate and work.nonces:
            self.queue.append(work)

        #if the queue is too short request more work
        if (len(self.queue)) < (self.queueSize):
            self.miner.connection.requestWork()

        #if there is a new block notify kernels that their work is now stale
        if newBlock:
            for callback in self.staleCallbacks:
                callback()

        #check if there are deferred NonceRange requests pending
        #since requests to fetch a NonceRange can add additional deferreds to
        #the queue, cache the size beforehand to avoid infinite loops.
        for i in range(len(self.deferredQueue)):
            df, size = self.deferredQueue.popleft()
            d = self.fetchRange(size)
            d.chainDeferred(df)

    #gets the next WorkUnit from queue
    def getNext(self):

        #check if the queue will fall below desired size
        if (len(self.queue) - 1) < (self.queueSize):
            self.miner.connection.requestWork()

        #return next WorkUnit
        return self.queue.popleft()

    def getRangeFromUnit(self, size):

        #get remaining nonces
        noncesLeft = self.currentUnit.nonces - self.currentUnit.base

        #if there are enough nonces to fill the full reqest
        if noncesLeft >= size:
            nr = NonceRange(self.currentUnit, self.currentUnit.base, size)

            #check if this uses up the rest of the WorkUnit
            if size >= noncesLeft:
                self.currentUnit = None
            else:
                self.currentUnit.base += size

        #otherwise send whatever is left
        else:
            nr = NonceRange(
                self.currentUnit, self.currentUnit.base, noncesLeft)
            self.currentUnit = None

        #return the range
        return nr

    def fetchRange(self, size=0x10000):

        #make sure size is not too large
        size = min(size, 0x100000000)

        #make sure size is not too small
        size = max(size, 256)

        #check if the current unit exists
        if self.currentUnit is not None:

            #get a nonce range
            nr = self.getRangeFromUnit(size)

            #return the range
            return defer.succeed(nr)

        #if there is no current unit
        else:
            #if there is another unit in queue
            if len(self.queue) >= 1:

                #get the next unit from queue
                self.currentUnit = self.getNext()

                #get a nonce range
                nr = self.getRangeFromUnit(size)

                #return the range
                return defer.succeed(nr)

            #if the queue is empty
            else:

                #request more work
                self.miner.connection.requestWork()

                #report that the miner is idle
                self.miner.reportIdle(True)

                #set up and return deferred
                df = defer.Deferred()
                self.deferredQueue.append((df, size))
                return df
