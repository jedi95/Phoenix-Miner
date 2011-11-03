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

from time import time
from Queue import Queue, Empty
from twisted.internet import reactor, defer

from KernelInterface import CoreInterface

class QueueReader(object):
    """A QueueReader is a very efficient WorkQueue reader that keeps the next
    nonce range available at all times. The benefit is that threaded mining
    kernels waste no time getting the next range, since this class will have it
    completely requested and preprocessed for the next iteration.

    The QueueReader is iterable, so a dedicated mining thread needs only to do
    for ... in self.qr:
    """

    SAMPLES = 3

    def __init__(self, core, preprocessor=None, workSizeCallback=None):
        if not isinstance(core, CoreInterface):
            # Older kernels used to pass the KernelInterface, and not a
            # CoreInterface. This is deprecated. We'll go ahead and take care
            # of that, though...
            core = core.addCore()
        self.core = core
        self.interface = core.getKernelInterface()
        self.preprocessor = preprocessor
        self.workSizeCallback = workSizeCallback

        if self.preprocessor is not None:
            if not callable(self.preprocessor):
                raise TypeError('the given preprocessor must be callable')
        if self.workSizeCallback is not None:
            if not callable(self.workSizeCallback):
                raise TypeError('the given workSizeCallback must be callable')

        # This shuttles work to the dedicated thread.
        self.dataQueue = Queue()

        # Used in averaging the last execution times.
        self.executionTimeSamples = []
        self.averageExecutionTime = None

        # This gets changed by _updateWorkSize.
        self.executionSize = None

        # Statistics accessed by the dedicated thread.
        self.currentData = None
        self.startedAt = None

    def start(self):
        """Called by the kernel when it's actually starting."""
        self._updateWorkSize(None, None)
        self._requestMore()
        # We need to know when the current NonceRange in the dataQueue is old.
        self.interface.addStaleCallback(self._staleCallback)

    def stop(self):
        """Called by the kernel when it's told to stop. This also brings down
        the loop running in the mining thread.
        """
        # Tell the other thread to exit cleanly.
        while not self.dataQueue.empty():
            try:
                self.dataQueue.get(False)
            except Empty:
                pass
        self.dataQueue.put(StopIteration())

    def _ranExecution(self, dt, nr):
        """An internal function called after an execution completes, with the
        time it took. Used to keep track of the time so kernels can use it to
        tune their execution times.
        """

        if dt > 0:
            self.core.updateRate(int(nr.size/dt/1000))

        self.executionTimeSamples.append(dt)
        self.executionTimeSamples = self.executionTimeSamples[-self.SAMPLES:]

        if len(self.executionTimeSamples) == self.SAMPLES:
            averageExecutionTime = (sum(self.executionTimeSamples) /
                                    len(self.executionTimeSamples))

            self._updateWorkSize(averageExecutionTime, nr.size)

    def _updateWorkSize(self, time, size):
        """An internal function that tunes the executionSize to that specified
        by the workSizeCallback; which is in turn passed the average of the
        last execution times.
        """
        if self.workSizeCallback:
            self.executionSize = self.workSizeCallback(time, size)

    def _requestMore(self):
        """This is used to start the process of making a new item available in
        the dataQueue, so the dedicated thread doesn't have to block.
        """

        # This should only run if there's no ready-to-go work in the queue.
        if not self.dataQueue.empty():
            return

        if self.executionSize is None:
            d = self.interface.fetchRange()
        else:
            d = self.interface.fetchRange(self.executionSize)

        def preprocess(nr):
            # If preprocessing is not necessary, just tuplize right away.
            if not self.preprocessor:
                return (nr, nr)

            d2 = defer.maybeDeferred(self.preprocessor, nr)

            # Tuplize the preprocessed result.
            def callback(x):
                return (x, nr)
            d2.addCallback(callback)
            return d2
        d.addCallback(preprocess)

        d.addCallback(self.dataQueue.put_nowait)

    def _staleCallback(self):
        """Called when the WorkQueue gets new work, rendering whatever is in
        dataQueue old.
        """

        #only clear queue and request more if no work present, since that
        #meas a request for more work is already in progress
        if not self.dataQueue.empty():
            # Out with the old...
            while not self.dataQueue.empty():
                try:
                    self.dataQueue.get(False)
                except Empty: continue
            # ...in with the new.
            self._requestMore()

    def __iter__(self):
        return self
    def next(self):
        """Since QueueReader is iterable, this is the function that runs the
        for-loop and dispatches work to the thread.

        This should be the only thread that executes outside of the Twisted
        main thread.
        """

        # If we just completed a range, we should tell the main thread.
        now = time()
        if self.currentData:
            dt = now - self.startedAt
            # self.currentData[1] is the un-preprocessed NonceRange.
            reactor.callFromThread(self._ranExecution, dt, self.currentData[1])
        self.startedAt = now

        # Block for more data from the main thread. In 99% of cases, though,
        # there should already be something here.
        # Note that this comes back with either a tuple, or a StopIteration()
        self.currentData = self.dataQueue.get(True)

        # Does the main thread want us to shut down, or pass some more data?
        if isinstance(self.currentData, StopIteration):
            raise self.currentData

        # We just took the only item in the queue. It needs to be restocked.
        reactor.callFromThread(self._requestMore)

        # currentData is actually a tuple, with item 0 intended for the kernel.
        return self.currentData[0]