---
title:  "Unit Testing in PySide2: Object Lifecycle and State Leakage"
toc: true
toc_sticky: true
classes: extra-wide
show_comments: true
---

As promised at the conclusion of my previous post, I will continue to document my experiences writing Qt applications in Python using PySide2 and the lessons I've learned along the way. In this article, I will explore two important topics: object lifecycle and state leakage between tests.

# Article Datasheet

| Name | Version |
| ------ | ------ |
| Python | 3.9.6 |
| PySide2 | 5.15.2 |
| nose | 1.3.7|

# Introduction
Assume you have a set of Python unit tests for your various Qt objects and controllers. The objects do a variety of event-driven tasks, and in doing so use some of the following:
- `PySide2.QtCore.Signal`, with both direct and queued connections
- `PySide2.QtCore.QThread`
- `PySide2.QtCore.QTimer`
- `PySide2.QtCore.QMutex`

The above are indispensible to the implementation of a user interface, and are employed liberally in most Qt applications. However, their versitility also does come with some additional considerations–especially when it comes to unit tests. Fundamentally speaking, the exectuion of a unit test ought not affect subsequent tests. This is typically accomplished by ensuring that resources required for tests are created in `TestCase.setUp()` and released in `TestCase.tearDown()` and `TestCase.doCleanups()`. Using this approach, one quickly runs into a serious problem: the inability to destroy a `QCoreApplication` instance.

# The Cat and the Bag
If you have called `QCoreApplication()` or, more likely, `QApplication()`, then the proverbial cat is out of the bag. A `QCoreApplication` instance, once created, can never be destroyed. This is a problem for many reasons, mainly that it violates the fundamental axiom of a proper unit test: consistent execution of the test regardless of what other unit tests may have proceeded it. 

If you think I am referring to the various attributes of the class instance itself, you are mistaken (but also correct, since changes to those will persist between tests). Rather, I believe the greater concern is something more-or-less unseen, yet painfully apparent. Consider the following example.

```python
class LeakyTests(TestCase):
    def setUp(self):
        self.qapp = QCoreApplication.instance() or QCoreApplication()

    def test_fail_if_timeout(self):
        self._fail_if_timeout()
        self.assertEqual(-1, self.qapp.exec_())

    def test_one(self):
        def do_task():
            # This would be the main test logic, running in the qapp's event loop
            self.assertIsNotNone(self.qapp)

            # Pretend that the test takes about 3 seconds of non-blocking work to complete
            QTimer.singleShot(3000, self.qapp.quit)

        QTimer.singleShot(0, do_task)
        self._fail_if_timeout()
        self.assertEqual(0, self.qapp.exec_())

    def test_two(self):
        def do_task():
            self.assertIsNotNone(self.qapp)

            # This test also takes about 3 seconds as well before succeeding
            QTimer.singleShot(3000, self.qapp.quit)

        QTimer.singleShot(0, do_task)
        self._fail_if_timeout()
        self.assertEqual(0, self.qapp.exec_())

    def _fail_if_timeout(self):
        QTimer.singleShot(5000, lambda: self.qapp.exit(-1))
```

When the tests in the above class are executed `test_one` will pass, but `test_two` will fail. This may seem strange given that the two tests are identical and that their behavior is relatively simple: queue up a function to run once the app starts (the test function: `do_task()`) and then wait three seconds before exiting the event loop successfully (as `QCoreApplication.exec_()` will return 0 when `QCoreApplication.quit()` is called).

Examining the assertion failure in `test_two`, we see that `exec_()` return -1, not the expected value of 0. Given the design of this test class, we can conclude that a timer created in `_fail_if_timeout()` is responsible for this erroneous failure. Note that I said "*a* timer" not "*the* timer" from `_fail_if_timeout()` caused the failure for one simple reason: even though just one of these timeout QTimers is created per test does not mean that only one of those timers is running during each test.

Let's sketch out a timeline of timers and other events that occur during the execution of this test class (depends on test collection order, so let's presume that they are executed in the order they are declared rather than alphabetically). Also, assume that each instruction is instantaneous:
1. 00:00 - `LeakyTests.test_fail_if_timeout()` begins
2. 00:00 - The test creates a failure timer, T0, and begins the QApp's event loop
3. 00:05 - T0 is triggered, causing the QApp to terminate its event loop and the test passes
4. 00:05 - `LeakyTests.test_one()` begins
5. 00:05 - The test creates a timer, T1, to run `do_task()` with no delay and it also creates a failure timer, T2, to terminate the QApp's event loop in the event that the test does not terminate in a timely fashion
6. 00:05 - The `do_task()` function is executed as scheduled by T1 and it creates a timer T3 to exit the QApp with an exit code of `0` after a 3 second delay.
7. 00:08 - T3 triggers, calling `QApplication.quit()`, terminating the event loop and passing the assertion at the end of `test_one()`
8. 00:08 - The next test, `test_two()` begins and schedules the same two timers as `test_one()`: one timer with no delay to run the task function (T4), and another with a 5 second delay to exit the QApp with a non-zero exit code to ensure the test halts at some point (T5)
9. 00:08 - T4 triggers, spawning T6 to quit the QApp as a success
10. 00:10 - Remember T2? Yeah, it's back and it's here to ruin your otherwise successful test. T2 triggers, exiting the event loop with a non-zero exit code, failing `test_two()` despite the fact that we are one second from T6 scheduled execution which would have successfully ended `test_two()`

# QObject Lifecycle
The issue here and the solution is relatively straight-forward: some objects created in one test were not destroyed after the test ended. In particular, the timer created in `_fail_if_timeout()` from `test_one()` was responsible for exiting the event loop running in `test_two()`.

There are many approaches one could take to remediate the issue. Some of those include:
- Stopping all timers at the end of each test via [QTimer.stop()](https://doc.qt.io/qt-5/qtimer.html#stop)
- Disconnecting connected slots from the timer's `triggered` signal
- Destroying the timer via `deleteLater()`
- Destroying the timer by assigning it a parent and destroying the parent

I have found the last option to be the best, in that we can leverage object lifecycle more easily and "brainlessly" by leveraging Qt's parent-child object relationships. Taking a look at the [documentation for QObject](https://doc.qt.io/qt-5/qobject.html#QObject) (from which QTimer is derived), we can see that "destructor of a parent object destroys all child objects". Let's give it a shot and tweak our test suite to take advantage of this.

```python
class LessLeakyTests(TestCase):
    def setUp(self):
        self.qapp = QCoreApplication.instance() or QCoreApplication()
        self.test_qobj = QObject()
        self.addCleanup(self.release_qt_resources)

    def release_qt_resources(self):
        self.test_qobj.deleteLater()
        self.qapp.sendPostedEvents(event_type=QEvent.DeferredDelete)
        self.qapp.processEvents()

    def _single_shot(self, timeout_ms: int, func: Callable[[], Any]):
        timer = QTimer(parent=self.test_qobj)
        timer.setSingleShot(True)
        timer.setInterval(timeout_ms)
        timer.timeout.connect(func)
        timer.start()

    def test_one(self):
        def do_task():
            # This would be the main test logic, running in the qapp's event loop
            # Pretend that the test takes about 3 seconds and at the end of which quit() is called to signify a successful test
            self._single_shot(3000, self.qapp.quit)

        self._single_shot(0, do_task)
        self._fail_if_timeout()
        self.assertEqual(0, self.qapp.exec_())

    def test_two(self):
        def do_task():
            # This test takes about 3 seconds as well before succeeding
            self._single_shot(3000, self.qapp.quit)

        self._single_shot(0, do_task)
        self._fail_if_timeout()
        self.assertEqual(0, self.qapp.exec_())

    def _fail_if_timeout(self):
        self._single_shot(5000, lambda: self.qapp.exit(-1))
```

In `setUp()` you will now see that we create a `QObject` which is used as a parent to all timers created in `_single_shot()`. Additionally, there is now a cleanup function `release_qt_resources()` which does three important things:
1. It first schedules the object for deletion (note: it does _not_ actually delete the object, see (docs)[https://doc.qt.io/qt-5/qobject.html#deleteLater] for more info)
2. It processes all posted events of type `QEvent.DeferredDelete`, which basically processes all scheduled object deletions
3. It pumps the main event loop once

The first step is necessary for obvious reasons, in that we want to delete the parent so that those timers are destroyed before the next test begins. The next two lines are a bit strange until you realize that this cleanup function is only executed after the test finishes and therefore we know that there is no running event loop. You could, in theory, run the event loop again and terminate it after some delay, however it's more trouble than its worth.


## Why is this necessary
As described earlier, a `QCoreApplication` instance or any of its subclasses is not destroyed during the entire lifecycle of the process. Additionally, there are some objects–like `QTimer` or any widgets/windows–which will continue to exist even when there are no obvious references to it in Python if they have a null parent.

On the other hand, other objects–like a `QObject` or `QThread`–will be destroyed and garbage collected when there are no more strong Python references as Qt does not maintain any internal references to those objects. That being said, you are not safe if you are creating QThreads instead of QTimers and ignoring their lifecycles, as you will run into the converse issue: the Python object will be destroyed before the underlying C++ object is and you will likely see the process trigger a segmentation fault.

In any case, managing the lifecycle of both the Python object and its corresponding C++ object is essential to a well-functioning application or test suite.

# Lessons Learned
In summary, make no assumptions about what happens in your application if you do not pay object lifecycle any attention. Rather, every single `QObject` should be inspected and its lifecycle carefully considered.

For a test suite, I recommend creating a `QObject` instance to use as a parent for any objects creataed in tests so that all your ephemeral test resources can be easily cleaned up and released prior to the next test.

Additionally, pumping the event loop between tests can also help prevent any queued signals or events from executing at the start of the next test. This is a topic that I have spent a great deal of time learning about myself, so I anticipate I will be writing more about it soon.
