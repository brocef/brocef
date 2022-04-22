from unittest import TestCase
from typing import Callable, Any

from PySide2.QtCore import QCoreApplication, QTimer, QObject, QEvent


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

