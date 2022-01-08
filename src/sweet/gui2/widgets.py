
import re
import os
import json
from .. import util
from ._vendor.Qt5 import QtWidgets, QtGui, QtCore
from ._vendor import qoverview
from . import delegates, resources as res
from .completer import RequestCompleter, RequestTextEdit
from .models import (
    JsonModel,
    ResolvedPackagesModel,
    ToolStackModel,
    InstalledPackagesModel,
    InstalledPackagesProxyModel,
)


class TreeView(qoverview.VerticalExtendedTreeView):

    def __init__(self, *args, **kwargs):
        super(TreeView, self).__init__(*args, **kwargs)
        self.setAllColumnsShowFocus(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setStyleSheet("""
            QTreeView::item{
                padding: 5px 1px;
                border: 0px;
            }
        """)


class CurrentSuite(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(CurrentSuite, self).__init__(*args, **kwargs)
        self.setObjectName("SuiteView")

        name = QtWidgets.QLineEdit()
        description = QtWidgets.QTextEdit()
        load_path = QtWidgets.QLineEdit()

        name.setPlaceholderText("Suite name..")
        description.setPlaceholderText("Suite description.. (optional)")
        description.setMinimumHeight(5)
        load_path.setReadOnly(True)
        load_path.setMinimumHeight(5)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(name)
        layout.addWidget(description, stretch=True)
        layout.addWidget(load_path)
        layout.addStretch()

        self._min_height = self.minimumSizeHint().height()
        self._hide_on_min = [description, load_path]

    def resizeEvent(self, event):
        h = event.size().height()
        for w in self._hide_on_min:
            w.setVisible(h > self._min_height)
        return super(CurrentSuite, self).resizeEvent(event)


class SuiteSavingDialog(QtWidgets.QDialog):
    pass


class DragDropListWidget(QtWidgets.QListWidget):
    dropped = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super(DragDropListWidget, self).__init__(*args, **kwargs)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(self.InternalMove)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)

    def dropEvent(self, event):
        rte = super(DragDropListWidget, self).dropEvent(event)
        if event.isAccepted():
            self.dropped.emit()
        return rte


class ContextListWidget(QtWidgets.QWidget):
    added = QtCore.Signal(str)
    renamed = QtCore.Signal(str, str)
    dropped = QtCore.Signal(str)
    reordered = QtCore.Signal(list)
    selected = QtCore.Signal(str)

    def __init__(self, *args, **kwargs):
        super(ContextListWidget, self).__init__(*args, **kwargs)
        self.setObjectName("ContextListWidget")

        label = QtWidgets.QLabel("Context Stack")

        view = DragDropListWidget()
        view.setSortingEnabled(False)  # do not sort this !

        btn_add = QtWidgets.QPushButton("Add")
        btn_add.setObjectName("ContextAddOpBtn")

        btn_rm = QtWidgets.QPushButton("Remove")
        btn_rm.setObjectName("ContextRemoveOpBtn")

        # layout

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(btn_add)
        layout.addWidget(view, stretch=True)
        layout.addWidget(btn_rm)

        # signals

        btn_add.clicked.connect(self.add_context)
        btn_rm.clicked.connect(self.drop_context)
        view.currentTextChanged.connect(self.selected)
        view.dropped.connect(self.context_reordered)
        view.itemDoubleClicked.connect(self.rename_context)

        self._view = view

    def on_context_added(self, ctx):
        item = QtWidgets.QListWidgetItem(ctx.name)
        # item.setData(ctx, role=self._model.ItemRole)
        self._view.insertItem(0, item)
        self._view.setCurrentRow(0)

    def on_context_dropped(self, name):
        item = self._find_item(name)
        self._view.takeItem(self._view.row(item))
        self._view.removeItemWidget(item)

    def on_context_reordered(self, new_order):
        items = []
        for name in new_order:
            item = self._find_item(name)
            self._view.takeItem(self._view.row(item))
            items.append(item)
        for item in items:
            self._view.addItem(item)

    def on_context_renamed(self, name, new_name):
        item = self._find_item(name)
        item.setText(new_name)

    def on_suite_reset(self):
        self._view.clear()

    def _find_item(self, name):
        return next(iter(self._view.findItems(name, QtCore.Qt.MatchExactly)))

    def add_context(self):
        existing = self.context_names()
        widget = ContextNameEditor(existing=existing)
        dialog = YesNoDialog(widget, parent=self)
        dialog.setWindowTitle("Name New Context")

        def on_finished(result):
            if result:
                self.added.emit(widget.get_name())

        dialog.finished.connect(on_finished)
        dialog.open()

    def rename_context(self, item):
        """
        :param item:
        :type item: QtWidgets.QListWidgetItem
        :return:
        """
        old_name = item.text()
        existing = self.context_names()
        existing.remove(old_name)

        widget = ContextNameEditor(existing=existing, default=old_name)
        dialog = YesNoDialog(widget, parent=self)
        dialog.setWindowTitle("Rename Context")

        def on_finished(result):
            if result:
                new_name = widget.get_name()
                if old_name != new_name:
                    self.renamed.emit(old_name, new_name)

        dialog.finished.connect(on_finished)
        dialog.open()

    def drop_context(self):
        names = self.selected_contexts()
        for name in names:
            self.dropped.emit(name)

    def selected_contexts(self):
        return [
            item.text() for item in self._view.selectedItems()
        ]

    def context_names(self):
        return [
            self._view.item(row).text()
            for row in range(self._view.count())
        ]

    def context_reordered(self):
        new_order = self.context_names()
        self.reordered.emit(new_order)


class YesNoDialog(QtWidgets.QDialog):

    def __init__(self, widget, *args, **kwargs):
        super(YesNoDialog, self).__init__(*args, **kwargs)

        btn_accept = QtWidgets.QPushButton("Accept")
        btn_reject = QtWidgets.QPushButton("Cancel")

        btn_accept.setObjectName("AcceptButton")
        btn_reject.setObjectName("CancelButton")
        btn_accept.setDefault(True)
        btn_accept.setEnabled(False)

        layout = QtWidgets.QGridLayout(self)
        layout.addWidget(widget, 0, 0, 1, 2)
        layout.addWidget(btn_accept, 1, 0, 1, 1)
        layout.addWidget(btn_reject, 1, 1, 1, 1)

        btn_accept.clicked.connect(lambda: self.done(self.Accepted))
        btn_reject.clicked.connect(lambda: self.done(self.Rejected))
        if hasattr(widget, "validated"):
            widget.validated.connect(btn_accept.setEnabled)


class ContextNameEditor(QtWidgets.QWidget):
    validated = QtCore.Signal(bool)
    colors = {
        "ready": QtGui.QColor("#78879b"),
        "invalid": QtGui.QColor("#C84747"),
    }

    def __init__(self, existing, default="", *args, **kwargs):
        super(ContextNameEditor, self).__init__(*args, **kwargs)
        self.setMinimumWidth(300)

        validator = RegExpValidator("^[a-zA-Z0-9_.-]*$")

        name = QtWidgets.QLineEdit()
        name.setText(default)
        name.setValidator(validator)
        name.setPlaceholderText("Input context name..")
        name.setToolTip("Only alphanumeric characters A-Z, a-z, 0-9 and "
                        "_, -, . are allowed.")

        message = QtWidgets.QLabel()

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(name)
        layout.addWidget(message)

        timer = QtCore.QTimer(self)

        anim = QtCore.QPropertyAnimation()
        anim.setEasingCurve(QtCore.QEasingCurve.InCubic)
        anim.setDuration(1000)
        anim.setStartValue(self.colors["invalid"])
        anim.setEndValue(self.colors["ready"])

        validator.validated.connect(self.on_validated)
        name.textChanged.connect(self.on_named)
        timer.timeout.connect(lambda: message.setText(""))

        self._timer = timer
        self.animation = anim
        self._status_color = self.colors["ready"]
        self._name = ""
        self._message = message
        self._existing_names = existing

        anim.setTargetObject(self)
        anim.setPropertyName(QtCore.QByteArray(b"status_color"))

        self.validated.emit(False)

    def on_validated(self, state):
        if state == QtGui.QValidator.Invalid:
            self.log("Invalid char.")
            self.animation.stop()
            self.animation.start()

    def on_named(self, value):
        unique_name = value not in self._existing_names
        self._name = value
        self.validated.emit(unique_name and bool(value))
        if not unique_name:
            self.log("Duplicated name.")
            self.animation.stop()
            self.animation.start()

    def get_name(self):
        return self._name

    def log(self, message):
        self._message.setText(str(message))
        self._timer.setSingleShot(True)
        self._timer.start(1000)

    def _get_status_color(self):
        return self._status_color

    def _set_status_color(self, color):
        self._status_color = color
        self.setStyleSheet("border-color: %s;" % color.name())

    status_color = QtCore.Property(QtGui.QColor,
                                   _get_status_color,
                                   _set_status_color)


class RegExpValidator(QtGui.QRegExpValidator):
    validated = QtCore.Signal(QtGui.QValidator.State)

    def __init__(self, pattern):
        super(RegExpValidator, self).__init__(QtCore.QRegExp(pattern))
        self._pattern = re.compile(pattern)

    def validate(self, text, pos):
        state, t, c = super(RegExpValidator, self).validate(text, pos)
        self.validated.emit(state)
        return state, t, c


class ToolStack(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(ToolStack, self).__init__(*args, **kwargs)
        self.setObjectName("ToolStack")

        label = QtWidgets.QLabel("Tool Stack")

        btn_filter = QtWidgets.QPushButton()  # toggleable
        btn_filter.setIcon(res.icon("images", "funnel-fill.svg"))

        stack = TreeView()

        model = ToolStackModel()
        stack.setModel(model)

        # layout

        action_layout = QtWidgets.QVBoxLayout()
        action_layout.addWidget(btn_filter)
        action_layout.addStretch()

        stack_layout = QtWidgets.QHBoxLayout()
        stack_layout.addLayout(action_layout)
        stack_layout.addWidget(stack)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label)
        layout.addLayout(stack_layout)

        # signals


class StackedResolveView(QtWidgets.QStackedWidget):

    def __init__(self, *args, **kwargs):
        super(StackedResolveView, self).__init__(*args, **kwargs)
        self._add_panel_0()
        self._names = []

    def on_context_added(self, ctx):
        name = ctx.name
        is_first = len(self._names) == 0
        if is_first:
            panel = self.widget(0)
            panel.set_name(name)
            panel.setEnabled(True)
        else:
            self.add_panel(name)
            self.setCurrentIndex(0)

        self._names.insert(0, name)

    def on_context_renamed(self, name, new_name):
        index = self._names.index(name)
        panel = self.widget(index)
        panel.set_name(new_name)
        self._names.remove(name)
        self._names.insert(index, new_name)

    def on_context_dropped(self, name):
        index = self._names.index(name)
        self._names.remove(name)
        is_empty = len(self._names) == 0

        panel = self.widget(index)
        self.removeWidget(panel)
        if is_empty:
            self._add_panel_0()

    def on_context_selected(self, name):
        # name may not exists yet while the context is just being added.
        if name in self._names:
            self.setCurrentIndex(self._names.index(name))

    def add_panel(self, name, enabled=True):
        panel = ResolvePanel()
        panel.set_name(name)
        panel.setEnabled(enabled)
        self.insertWidget(0, panel)

    def _add_panel_0(self):
        self.add_panel("", enabled=False)


class ResolvePanel(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(ResolvePanel, self).__init__(*args, **kwargs)

        label = QtWidgets.QLabel()

        prefix = QtWidgets.QLineEdit()
        prefix.setPlaceholderText("context prefix..")
        suffix = QtWidgets.QLineEdit()
        suffix.setPlaceholderText("context suffix..")

        request_editor = RequestEditor()

        resolved_info = QtWidgets.QWidget()
        info = QtWidgets.QLabel("Resolved Context Info")
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(ResolvedTools(), "Tools")
        tabs.addTab(ResolvedPackages(), "Packages")
        tabs.addTab(ResolvedEnvironment(), "Environment")
        tabs.addTab(ResolvedCode(), "Code")
        tabs.addTab(ResolvedGraph(), "Graph")
        layout = QtWidgets.QVBoxLayout(resolved_info)
        layout.addWidget(info)
        layout.addWidget(tabs)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(request_editor)
        splitter.addWidget(resolved_info)

        splitter.setOrientation(QtCore.Qt.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 30)
        splitter.setStretchFactor(1, 70)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(splitter)

        self._label = label
        self._editor = request_editor

    def set_name(self, ctx_name):
        self._editor.set_name(ctx_name)
        self._label.setText("Context: %s" % ctx_name)


class RequestEditor(QtWidgets.QWidget):
    requested = QtCore.Signal(str, list)

    def __init__(self, *args, **kwargs):
        super(RequestEditor, self).__init__(*args, **kwargs)

        request = RequestTextEdit()
        resolve = QtWidgets.QPushButton("Resolve")
        resolve.setObjectName("ContextResolveOpBtn")

        request.setPlaceholderText("requests..")
        request.setAcceptRichText(False)
        request.setTabChangesFocus(True)

        completer = RequestCompleter(request)
        request.setCompleter(completer)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(request)
        layout.addWidget(resolve)

        resolve.clicked.connect(self.on_resolve_clicked)

        self._name = None
        self._text = request
        self._completer = completer

    def on_families_scanned(self, families):
        self._completer.model().add_families(families)

    def on_versions_scanned(self, versions):
        self._completer.model().add_versions(versions)

    def on_resolve_clicked(self):
        self.requested.emit(self._name, self._text.toPlainText().split())

    def set_name(self, ctx_name):
        self._name = ctx_name


class ResolvedTools(QtWidgets.QWidget):
    pass


class ResolvedPackages(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(ResolvedPackages, self).__init__(*args, **kwargs)

        view = TreeView()
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self.on_right_click)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(view)

        self._view = view

    def on_right_click(self, position):
        view = self._view
        index = view.indexAt(position)

        if not index.isValid():
            # Clicked outside any item
            return

        menu = QtWidgets.QMenu(view)
        openfile = QtWidgets.QAction("Open file location", menu)
        copyfile = QtWidgets.QAction("Copy file location", menu)

        menu.addAction(openfile)
        menu.addAction(copyfile)

        def on_openfile():
            package = index.data(role=ResolvedPackagesModel.PackageRole)
            pkg_uri = os.path.dirname(package.uri)
            fname = os.path.join(pkg_uri, "package.py")
            util.open_file_location(fname)

        def on_copyfile():
            package = index.data(role=ResolvedPackagesModel.PackageRole)
            pkg_uri = os.path.dirname(package.uri)
            fname = os.path.join(pkg_uri, "package.py")
            clipboard = QtWidgets.QApplication.instance().clipboard()
            clipboard.setText(fname)

        openfile.triggered.connect(on_openfile)
        copyfile.triggered.connect(on_copyfile)

        menu.move(QtGui.QCursor.pos())
        menu.show()


class JsonView(TreeView):

    def __init__(self, parent=None):
        super(JsonView, self).__init__(parent)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_right_click)

    def on_right_click(self, position):
        index = self.indexAt(position)

        if not index.isValid():
            # Clicked outside any item
            return

        model_ = index.model()
        menu = QtWidgets.QMenu(self)
        copy = QtWidgets.QAction("Copy JSON", menu)
        copy_full = QtWidgets.QAction("Copy full JSON", menu)

        menu.addAction(copy)
        menu.addAction(copy_full)
        menu.addSeparator()

        def on_copy():
            text = str(model_.data(index, JsonModel.JsonRole))
            app = QtWidgets.QApplication.instance()
            app.clipboard().setText(text)

        def on_copy_full():
            if isinstance(model_, QtCore.QSortFilterProxyModel):
                data = model_.sourceModel().json()
            else:
                data = model_.json()

            text = json.dumps(data,
                              indent=4,
                              sort_keys=True,
                              ensure_ascii=False)

            app = QtWidgets.QApplication.instance()
            app.clipboard().setText(text)

        copy.triggered.connect(on_copy)
        copy_full.triggered.connect(on_copy_full)

        menu.move(QtGui.QCursor.pos())
        menu.show()


class ResolvedEnvironment(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(ResolvedEnvironment, self).__init__(*args, **kwargs)

        view = JsonView()
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(view)


class ResolvedCode(QtWidgets.QWidget):
    pass


class ResolvedGraph(QtWidgets.QWidget):
    pass


class VerticalDocTabBar(QtWidgets.QTabBar):

    def __init__(self, *args, **kwargs):
        super(VerticalDocTabBar, self).__init__(*args, **kwargs)
        self.setShape(QtWidgets.QTabBar.RoundedWest)
        self.setDocumentMode(True)  # for MacOS
        self.setUsesScrollButtons(True)

    def tabSizeHint(self, index):
        s = QtWidgets.QTabBar.tabSizeHint(self, index)
        s.transpose()
        return s

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        opt = QtWidgets.QStyleOptionTab()

        for i in range(self.count()):
            self.initStyleOption(opt, i)
            painter.drawControl(QtWidgets.QStyle.CE_TabBarTabShape, opt)
            painter.save()

            s = opt.rect.size()
            s.transpose()
            r = QtCore.QRect(QtCore.QPoint(), s)
            r.moveCenter(opt.rect.center())
            opt.rect = r

            rect = self.tabRect(i)
            c = rect.center()
            painter.translate(c)
            painter.rotate(90)
            painter.translate(-c)
            painter.drawControl(QtWidgets.QStyle.CE_TabBarTabLabel, opt)
            painter.restore()


class InstalledPackagesTabBar(VerticalDocTabBar):
    def __init__(self, *args, **kwargs):
        super(InstalledPackagesTabBar, self).__init__(*args, **kwargs)
        self.setObjectName("PackageTabBar")
        self.setMinimumHeight(120)


class InstalledPackagesView(TreeView):

    def __init__(self, *args, **kwargs):
        super(InstalledPackagesView, self).__init__(*args, **kwargs)
        self.setObjectName("PackageTreeView")
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)

        time_delegate = delegates.PrettyTimeDelegate()
        self.setItemDelegateForColumn(1, time_delegate)

        self._time_delegate = time_delegate


class InstalledPackagesWidget(QtWidgets.QWidget):

    def __init__(self, *args, **kwargs):
        super(InstalledPackagesWidget, self).__init__(*args, **kwargs)

        wrap = QtWidgets.QWidget()
        body = QtWidgets.QWidget()
        body.setObjectName("PackagePage")
        side = QtWidgets.QWidget()
        side.setObjectName("PackageSide")

        search = QtWidgets.QLineEdit()
        view = InstalledPackagesView()
        model = InstalledPackagesModel()
        proxy = InstalledPackagesProxyModel()
        tabs = InstalledPackagesTabBar()

        proxy.setSourceModel(model)
        view.setModel(proxy)
        search.setPlaceholderText(" Search by family or tool..")
        tabs.addTab("")  # placeholder tab for startup

        # layout

        layout = QtWidgets.QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)
        layout.addStretch(100)
        layout.setSpacing(0)

        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(view)

        layout = QtWidgets.QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(side)
        layout.addWidget(body)
        layout.setSpacing(0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(search)
        layout.addSpacing(6)
        layout.addWidget(wrap)
        layout.setSpacing(0)

        # signals

        header = view.header()
        scroll = view.verticalScrollBar()

        model.modelReset.connect(self.on_model_reset)
        tabs.currentChanged.connect(self.on_tab_clicked)
        search.textChanged.connect(self.on_searched)
        header.sortIndicatorChanged.connect(self.on_sort_changed)
        scroll.valueChanged.connect(self.on_scrolled)

        self._view = view
        self._model = model
        self._proxy = proxy

        self._tabs = tabs
        self._groups = []

    def model(self):
        return self._model

    def proxy(self):
        return self._proxy

    def on_searched(self, text):
        self._proxy.setFilterRegExp(text)
        self._view.reset_extension()

    def on_tab_clicked(self, index):
        group = self._tabs.tabText(index)
        for i, item in enumerate(self._model.iter_items()):
            if item["_group"] == group:
                index = self._model.index(i, 0)
                index = self._proxy.mapFromSource(index)
                self._view.scroll_at_top(index)
                return

    def on_scrolled(self, value):
        if not self._tabs.isEnabled():
            return

        index = self._view.top_scrolled_index(value)
        index = self._proxy.mapToSource(index)
        name = self._model.data(index)
        if name:
            group = name[0].upper()
            index = self._groups.index(group)
            self._tabs.blockSignals(True)
            self._tabs.setCurrentIndex(index)
            self._tabs.blockSignals(False)

    def on_sort_changed(self, index, order):
        is_sort_name = index == 0

        self._tabs.setEnabled(is_sort_name)
        if is_sort_name:
            if len(self._groups) <= 1:
                return

            first, second = self._groups[:2]
            is_ascending = int(first > second)
            if is_ascending == int(order):
                return

            self._groups.reverse()
            for i, group in enumerate(self._groups):
                self._tabs.setTabText(i, group)

    def on_model_reset(self):
        # regenerate tabs
        tabs = self._tabs
        self._groups.clear()
        for index in range(tabs.count()):
            tabs.removeTab(index)

        for group in self._model.name_groups():
            self._groups.append(group)
            tabs.addTab(group)

        # (MacOS) Ensure tab bar *polished* even it's not visible on launch.
        tabs.updateGeometry()
