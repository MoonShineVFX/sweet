
import os
import sys
import signal as py_signal
from contextlib import contextmanager
from ._vendor.Qt5 import QtCore, QtWidgets
from . import control, view, widgets, resources


def launch(app_name="sweet-gui"):
    """GUI entry point

    :param app_name: Application name. Used to compose the location of current
        user specific settings file. Default is "sweet-gui".
    :type app_name: str or None
    :return: QApplication exit code
    :rtype: int
    """
    ses = Session(app_name=app_name)
    ses.view.show()
    return ses.app.exec_()


class Session(object):

    def __init__(self, app_name="sweet-gui"):
        # allow user interrupt with Ctrl+C
        py_signal.signal(py_signal.SIGINT, py_signal.SIG_DFL)

        if sys.platform == "darwin":
            os.environ["QT_MAC_WANTS_LAYER"] = "1"  # MacOS BigSur

        app = QtWidgets.QApplication.instance()  # noqa
        app = app or QtWidgets.QApplication([])

        storage = QtCore.QSettings(QtCore.QSettings.IniFormat,
                                   QtCore.QSettings.UserScope,
                                   app_name, "preferences")
        print("Preference file: %s" % storage.fileName())

        state = State(storage=storage)
        ctrl = control.Controller(state=state)
        view_ = view.MainWindow(state=state)

        resources.load_themes()
        qss = resources.load_theme(name=state.retrieve("theme"))
        view_.setStyleSheet(qss)

        self._app = app
        self._ctrl = ctrl
        self._view = view_

        self._build_connections()

    @property
    def app(self):
        return self._app

    @property
    def ctrl(self):
        return self._ctrl

    @property
    def view(self):
        return self._view

    def _build_connections(self):
        stack = self.view.find(widgets.ContextStack)
        stack.added.connect(self.ctrl.on_stack_added)
        self.ctrl.context_added.connect(stack.on_context_added)


class State(object):
    """Store/re-store Application status in/between sessions"""

    def __init__(self, storage):
        """
        :param storage: An QtCore.QSettings instance for save/load settings
            between sessions.
        :type storage: QtCore.QSettings
        """
        self._storage = storage

    def _f(self, value):
        # Account for poor serialisation format
        true = ["2", "1", "true", True, 1, 2]
        false = ["0", "false", False, 0]

        if value in true:
            value = True

        if value in false:
            value = False

        if value and str(value).isnumeric():
            value = float(value)

        return value

    @contextmanager
    def group(self, key):
        self._storage.beginGroup(key)
        try:
            yield
        finally:
            self._storage.endGroup()

    def is_writeable(self):
        return self._storage.isWritable()

    def store(self, key, value):
        self._storage.setValue(key, value)

    def retrieve(self, key, default=None):
        value = self._storage.value(key)
        if value is None:
            value = default
        return self._f(value)

    def preserve_layout(self, widget, group):
        # type: (QtWidgets.QWidget, str) -> None
        if not self.is_writeable():
            # todo: prompt warning
            return

        self._storage.beginGroup(group)

        self.store("geometry", widget.saveGeometry())
        if hasattr(widget, "saveState"):
            self.store("state", widget.saveState())
        if hasattr(widget, "directory"):  # QtWidgets.QFileDialog
            self.store("directory", widget.directory())

        self._storage.endGroup()

    def restore_layout(self, widget, group):
        # type: (QtWidgets.QWidget, str) -> None
        self._storage.beginGroup(group)

        keys = self._storage.allKeys()

        if "geometry" in keys:
            widget.restoreGeometry(self.retrieve("geometry"))
        if "state" in keys and hasattr(widget, "restoreState"):
            widget.restoreState(self.retrieve("state"))
        if "directory" in keys and hasattr(widget, "setDirectory"):
            widget.setDirectory(self.retrieve("directory"))

        self._storage.endGroup()
