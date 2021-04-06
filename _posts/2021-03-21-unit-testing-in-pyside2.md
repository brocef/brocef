---
title:  "Unit Testing in PySide2"
toc: true
toc_sticky: true
classes: extra-wide
show_comments: true
---

For my first post, I will be discussing something that I've had to deal with for quite some time now: writing Python unit tests for a GUI written in Qt.

# Article Datasheet

| Name | Version |
| ------ | ------ |
| Python | 3.6.8 |
| PySide2 | 5.14.1 |
| nose | 1.3.7|

# Introduction
Let's say you had an application written in Python, but you need a graphical interface. One that is portable, easy to deploy, and well documented. It would not be too surprising if you ended up opting for Qt, as they operate a very well established, documented, and extensible C++ GUI framework which–since 2016–also had an officially supported set of Python bindings ([PySide2](https://wiki.qt.io/Qt_for_Python)). However, if you did opt for Qt, then you'll likely run into a few issues when trying to unittest your UI controllers, especially if you often take a multi-threaded or signal-based approach to development.

Consider the following example.

```python
class Worker(QThread):
    resultReady = Signal(int)

    def run(self):
        # Pretend that this sleep is the worker doing something that takes a while
        for _ in range(0, 20):
            self.thread().msleep(100)
            self.resultReady.emit(random.randint(1, 100))


class Controller(QObject):
    startWorkers = Signal()

    def __init__(self):
        super().__init__()
        self.worker = Worker()
        self.startWorkers.connect(self.worker.start)
        self.worker.resultReady.connect(self.on_worker_result)

    def start(self):
        self.startWorkers.emit()

    @Slot(int)
    def on_worker_result(self, result: int):
        print("Received result from worker:", result)
```

If you wanted to write a unit test for `Controller`, you'd quickly find that you have a decision to make: do you want to patch the `Worker` class or not? By patching `Worker`, you'd avoid any issues arising from the fact that you are spinning up a new C++ thread. However, patching `Worker` will also prevent you from testing proper signal/slot integration with `Controller`.

# Unit Test Attempt and Failure

Consider the following naïve approach to writing a unit test:

```python

from unittest import TestCase
from unittest.mock import patch

class TestIntegratedController(TestCase):
    def test_controller_and_worker_bad(self):
        controller = Controller()
        with patch.object(controller, "on_worker_result") as on_result:
            controller.start()
            self.assertTrue(controller.worker.isRunning())
            self.assertTrue(controller.worker.wait())
            self.assertEqual(20, len(on_result.mock_calls))
```

Running this test will fail since `on_result.mock_calls` will be an empty list, indicating that all emissions of `worker.resultReady` were not delivered. This is, in fact, exactly what happened. One may wonder if signals aren't being processed due to the lack of an active event loop, but we can also conclude that _some_ signals are working as expected.

The call to `controller.start()` simply emits the `startWorkers` signal which has one connected slot: `worker.start`. Considering that the first assertion, `self.assertTrue(controller.worker.isRunning())`, didn't fail we know that the `startWorkers` signal was processed. What's going on?

The answer is actually quite simple: queued signals are not processed in the absence of a running event loop.

# Qt Signals, and You

Looking at the documentation for [QObject.connect()](https://doc.qt.io/qt-5/qobject.html#connect), you'll see that the default connection type is [Qt::AutoConnection](https://doc.qt.io/qt-5/qt.html#ConnectionType-enum). This type of signal connection is great for most use cases, but can lead to some confusing behavior. The description is as follows:

> If the receiver lives in the thread that emits the signal, Qt::DirectConnection is used. Otherwise, Qt::QueuedConnection is used. The connection type is determined when the signal is emitted.

Alright, so it's basically a convenient way to either use a `Qt::DirectConnection` or `Qt::QueuedConnection` depending on whether or not the receiver is in the same thread that is emitting the signal. A direct connection is pretty straight-forward: it immediately invokes the connected slot. A queued connection, however, is a bit more interesting.

> The slot is invoked when control returns to the event loop of the receiver's thread. The slot is executed in the receiver's thread.

And there you have it. Since `worker.resultReady` is emitted from inside a new thread and the connection to `on_worker_result` was made in the main thread, the only way that the signal will be processed is if "control returns to the event loop of the receiver's thread".

# A Fork in the Road

So now you have 2 options:
1. Force the connection to be direct
2. Run an event loop

Let's examine each options.

## A Direct Approach

If the connection is `Qt::DirectConnection`, then callbacks will be invoked directly regardless of what thread they live in.

If we change

```python
self.worker.resultReady.connect(self.on_worker_result)
```

to

```python
self.worker.resultReady.connect(self.on_worker_result, type=Qt.DirectConnection)
```

then we'll see that the test passes. Great! Easy fix, right?

Not so fast.

In this case, the change is safe in that the only thing that `Controller.on_worker_result()` does is call `print()`, but imagine that the function instead does something that is a bit more complex, like resize a window to fit new contents. Let's beef up the `Controller` class to now render results as they come in.

```python
class VisualController(Controller):
    def __init__(self):
        super().__init__()
        self.results = QStringListModel(["Worker Results:"])
        self.listview = QListView()
        self.listview.setModel(self.results)

    def start(self):
        super().start()
        self.listview.show()

    @Slot(int)
    def on_worker_result(self, result: int):
        super().on_worker_result(result)
        row_count = self.results.rowCount()
        assert self.results.insertRows(row_count, 1)
        new_row_idx = self.results.index(row_count, 0)
        self.results.setData(new_row_idx, str(result))
        self._resize_to_fit_contents()

    def _resize_to_fit_contents(self):
        QApplication.processEvents()
        view_geo = self.listview.geometry()
        view_geo.setHeight(max(view_geo.height(), self.listview.contentsSize().height()))
        self.listview.setGeometry(view_geo)
```

For reference, here's the main block:

```python
if __name__ == "__main__":
    from PySide2.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    controller = VisualController()
    controller.start()
    app.exec_()
```

Running this file will work for the first ten results or so, but as soon as it comes time to resize the window the application crashes. I am running this on macOS v10.15.7 (Catalina), and this is the traceback:

```
2021-04-06 12:18:52.172 python[3447:4844238] WARNING: NSWindow drag regions should only be invalidated on the Main Thread! This will throw an exception in the future. Called from (
        0   AppKit                              0x00007fff33133629 -[NSWindow(NSWindow_Theme) _postWindowNeedsToResetDragMarginsUnlessPostingDisabled] + 371
        1   AppKit                              0x00007fff3314563a -[NSView setFrameOrigin:] + 1141
        2   AppKit                              0x00007fff331451ae -[_NSThemeWidget setFrameOrigin:ignoreRentry:] + 66
        3   AppKit                              0x00007fff33144088 -[NSThemeFrame _updateButtonPositions] + 197
        4   AppKit                              0x00007fff331428a1 -[NSThemeFrame _tileTitlebarAndRedisplay:] + 69
        5   AppKit                              0x00007fff33160ec5 -[NSThemeFrame setFrameSize:] + 631
```

As you can see, the call to `NSThemeFrame.setFrameSize` is causing the issue. This ought not come as a surprise, as all GUI operations should happen in the main thread and we've designed the application to trigger `VisualController._resize_to_fit_contents()` to happen in the worker's thread.

Changing the `resultReady` signal connection back to `Qt::AutoConnection` resolves the issue as `VisualController._resize_to_fit_contents()` now occurs in the main thread.

We won't be continuing to use `VisualController` anymore, however feel free to keep it around to play around with. It's purpose is to simply demonstrate that the direct connection approach is often flawed, and should only be used with the utmost caution.

## Going Loopy

The `VisualController` example worked quite well and results were processed as expected, but only due to the fact that there was a running event loop (`Qapplication.exec_()`). We're reaching the grand-finale of this article: how to write a Python unit test that spins up an event loop to properly test this async worker model.

You might be thinking, "if we spin up an event loop, won't that block the exection of the test causing it to never terminate?" The short answer is yes, unless we do something about that!

Consider the following unit test:

```python
class TestIntegratedController(TestCase):
    def test_controller_and_worker_good(self):
        app = QCoreApplication(sys.argv)
        controller = Controller()
        controller.worker.finished.connect(QCoreApplication.quit)
        with patch.object(controller, "on_worker_result") as on_result:
            controller.start()
            app.exec_()
            self.assertEqual(20, len(on_result.mock_calls))
```

Running the test passes, just as we hoped. However, the test is not as safe nor comprehensive as it could be. There are a few possibilities that can derail the test and, in some cases, causing the test to never finish.

### Event-Loop Testing Considerations
I'm sure the Qt-veterans out there can think of a slew of possible issues with little more than a single glance at the above test. Here are those that I was able to identify (some of which aren't exactly likely for this particular test, but certainly are if we consider this to be a generalized approach):
- There is nothing to ensure that `exec_()` returns in the event that the worker thread fails to terminate
- We do not check the value of `exec_()`
- The controller, and consequently its worker, start before the event loop begins potentially causing issues and violates a typical invariant of Qt applications–that the main event loop is always running when components are in use
- If the worker finishes before the event loop begins, the test will never finish (imagine a sleep between `controller.start()` and `app.exec_()`)
- If this test is one of many that requires a `QCoreApplication` (or a subclass, like `QApplication`) then the constructor for `app` will fail
- The worker thread starts before the event loop has begun, which may not be desired in some cases

I'm not going to bore you with an explanation for each of those items, rather I'll just jump to my solution.

### Unit Test Attempt and Success

First, there is one (optional) change needed in the `Controller` class.

Change

```python
self.startWorkers.connect(self.worker.start)
```

to

```python
self.startWorkers.connect(self.worker.start, type=Qt.QueuedConnection)
```

By making this a queued connection, calling `Controller.start()` will only run the worker thread once the event loop begins. You don't necessarily need this, as the `resultReady` signal connection is queued and won't be processed until the event loop begins, however I think it is better to do minimize the amount of work that is done without an event loop for a test like this.

And now for the revised unit test:
```python
class TestIntegratedController(TestCase):
    def test_controller_and_worker_better(self):
        app = QCoreApplication.instance() or QCoreApplication(sys.argv)
        controller = Controller()
        controller.worker.finished.connect(QCoreApplication.quit, type=Qt.QueuedConnection)

        timeout_timer = QTimer(parent=controller)
        timeout_timer.setInterval(3000)
        timeout_timer.setSingleShot(True)
        timeout_timer.timeout.connect(lambda: QCoreApplication.exit(-1))
        timeout_timer.start()

        with patch.object(controller, "on_worker_result") as on_result:
            controller.start()
            self.assertEqual(0, app.exec_())
            self.assertEqual(20, len(on_result.mock_calls))
```

Walking through some of the changes:
- `app` is assigned to `QCoreApplication.instance() or QCoreApplication(sys.argv)` as a lazy way to say: set `app` to the `QCoreApplication` that already exists, and if one does not exist make it
- The connection to `controller.worker.finished` is now a queued connection to ensure that if the worker finishes before the event loop begins, that the call to `QCoreApplication.quit()` only occurs once the event loop begins (which is the recommended method in [the Qt docs](https://doc.qt.io/qt-5/qcoreapplication.html#quit))
- A `QTimer` is created before the main test logic begins and is set to run once (`singleShot` is `True`) with a timeout of 3000 milliseconds (the worker should take ~2000 milliseconds, so there's a ~1000 millisecond grace period for extra processing, can be increased as needed)
- The `QTimer` is set to call `QCoreApplication.exit(-1)` if it is triggered, which will cause `app.exec_()` to return even if the worker thread didn't finish (in time)
- The value of `app.exec_()`  is inspected and verified to be `0`, ensuring that the cause for test termination is a success (in this case it's from the `worker.finished` connection)

While this test is not perfect, it's a good start.

# Debrief
In [the first unit test](#unit-test-attempt-and-failure) we saw a simple, but misguided, approach to unit testing Qt components in Python. After examining the issues and possible approaches, it became clear that an ideal solution would preserve the multi-thread signalling relationship between `Controller` and `Worker`. A new version of the [same unit test](#unit-test-attempt-and-success) was crafted, yielding the desired result.

If you'd like to see the different tests in action and play around with the visual component from [A Direct Approach](#a-direct-approach), you can find the [sample Python file here](/samples/2021-03-21-unit-testing-in-pyside2/example_tests_and_visuals.py).

The final version of the unit test, while better, is still not perfect. In subsequent articles I will discuss further improvements to a Qt unit testing framework to cover issues including, but not limited to, the following:
- Garbage collection of test resources
- Enforcing proper resource management and component lifecycle
- Preventing state leakage between tests
- Testing visual components in a headless environment
- Catching and handling exceptions that occur in `QThreads` and slots to properly fail tests

**Thanks for reading!**
