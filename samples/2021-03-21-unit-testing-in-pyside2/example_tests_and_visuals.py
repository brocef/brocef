import random
import sys
from unittest import TestCase
from unittest.mock import patch

from PySide2.QtCore import (QCoreApplication, QMutex, QObject, QThread, QTimer,
                            Signal, Slot, Qt, QStringListModel)
from PySide2.QtWidgets import QListView


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
        self.startWorkers.connect(self.worker.start, type=Qt.QueuedConnection)
        self.worker.resultReady.connect(self.on_worker_result)

    def start(self):
        self.startWorkers.emit()

    @Slot(int)
    def on_worker_result(self, result: int):
        print("Received result from worker:", result)


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


class TestIntegratedController(TestCase):
    def test_controller_and_worker_good(self):
        app = QCoreApplication(sys.argv)
        controller = Controller()
        controller.worker.finished.connect(QCoreApplication.quit)
        with patch.object(controller, "on_worker_result") as on_result:
            controller.start()
            app.exec_()
            self.assertEqual(20, len(on_result.mock_calls))

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


    def test_controller_and_worker_bad(self):
        controller = Controller()
        with patch.object(controller, "on_worker_result") as on_result:
            controller.start()
            self.assertTrue(controller.worker.isRunning())
            self.assertTrue(controller.worker.wait())
            self.assertEqual(20, len(on_result.mock_calls))


if __name__ == "__main__":
    from PySide2.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    controller = VisualController()
    controller.start()
    app.exec_()
