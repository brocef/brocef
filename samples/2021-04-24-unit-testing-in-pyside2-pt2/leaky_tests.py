from unittest import TestCase

from PySide2.QtCore import QCoreApplication, QTimer, QThread


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
