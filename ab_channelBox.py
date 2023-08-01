from PySide2 import QtWidgets, QtCore, QtGui
from shiboken2 import wrapInstance

from maya import cmds
import maya.OpenMaya as apiOM
import maya.OpenMayaUI as omui


from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

# ICON_URL = "C:/Users/abeck/Desktop/ab_channelBox/Icons"


def get_maya_window():

    """
    Returns a pointer to the Maya main window.

    :return: object

    """

    main_window_pointer = omui.MQtUtil.mainWindow()

    return wrapInstance(
        long(main_window_pointer), QtWidgets.QMainWindow)


class Window(MayaQWidgetDockableMixin, QtWidgets.QMainWindow):

    """
    Subclasses Maya dockable widget and QMainWindow.
    When subclassing constructor arguments must match.

    """

    _instance = None

    def __init__(self, parent, *args, **kwargs):
        super(Window, self).__init__(parent)

        if self._instance:
            self._instance.close()

        self.main_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.main_widget)

        self.__class__._instance = self

    @classmethod
    def run(cls, dockable, *args, **kwargs):

        """Instantiate the class with support
        for docking.

        :param dockable: bool
        :return: None

        """

        app = cls(get_maya_window(),
                  *args, **kwargs)

        app.close()

        app.show(dockable=dockable)

    def dockCloseEventTriggered(self):
        clean_up()


class AB_ChannelBox(Window):

    attr_change_cb = None

    def __init__(self, parent=None):
        super(AB_ChannelBox, self).__init__(parent=parent)

        # kill existing script jobs
        existing_sj = [_ for _ in cmds.scriptJob(listJobs=True) if "AB_ChannelBox" in _]
        for i in existing_sj:
            cmds.scriptJob(kill=int(i.split(":")[0]))

        # scriptJob to detect selection changes
        self.sel_changed_sj = cmds.scriptJob(event=["SelectionChanged", self._sel_changed])

        self._increment = 5

        self._validator = QtGui.QRegExpValidator(QtCore.QRegExp("[+-]?([0-9]*[.])?[0-9]+"))

        self._current_sel = "*no selection*"
        self._sel_locked = False
        self._object_space = True

        self._channels = ["translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"]
        self._transforms = dict(translate=["translateX", "translateY", "translateZ"],
                                rotate=["rotateX", "rotateY", "rotateZ"])

        self.setWindowTitle("Channel Box")
        self.adjustSize()

        self.main_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.main_widget)

        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.setAlignment(QtCore.Qt.AlignTop)
        self.main_widget.setLayout(self.main_layout)

        self._interface = self._populate_ui()
        self._marking_menu()
        self._connect_signals()

        self._sel_changed()

    def _populate_ui(self):

        self._interface = dict(
            layout=dict(),
            widget=dict(),
            label=dict(),
            channel=dict(),
            input=dict(),
            button=dict(),
            checkbox=dict(),
            menu=dict()
        )

        # header grid line
        self._interface["layout"]["header"] = QtWidgets.QGridLayout()
        self._interface["layout"]["header"].setColumnStretch(1, 1)
        self.main_layout.addLayout(self._interface["layout"]["header"])

        self._interface["checkbox"]["sel_lock"] = QtWidgets.QCheckBox()
        self._interface["checkbox"]["sel_lock"].setStyleSheet("QCheckBox::indicator {height:15; width:15;}"
                                                              "QCheckBox::indicator:unchecked {image: url(" + ICON_URL + "/lock_opened_v2.png)}"
                                                              "QCheckBox::indicator:unchecked:hover {image: url(" + ICON_URL + "/lock_opened_hover_v2.png)}"
                                                              "QCheckBox::indicator:checked {image: url(" + ICON_URL + "/lock_closed_v2.png)}"
                                                              "QCheckBox::indicator:checked:hover {image: url(" + ICON_URL + "/lock_closed_hover_v2.png)}")
        self._interface["layout"]["header"].addWidget(self._interface["checkbox"]["sel_lock"], 0, 0)

        self._interface["button"]["sel"] = QtWidgets.QPushButton("*no selection*")
        self._interface["button"]["sel"].setStyleSheet("color: #999999;"
                                                       "background-color: #444444;"
                                                       "border: none;"
                                                       "font-weight: bold;"
                                                       "padding: 0;"
                                                       "text-align: left")
        self._interface["button"]["sel"].clicked.connect(lambda: _select_obj(self._current_sel))
        self._interface["layout"]["header"].addWidget(self._interface["button"]["sel"], 0, 1)

        self._interface["button"]["reset"] = QtWidgets.QPushButton("Reset")
        self._interface["button"]["reset"].setMinimumWidth(100)
        self._interface["button"]["reset"].setStyleSheet("padding: 0")
        self._interface["layout"]["header"].addWidget(self._interface["button"]["reset"], 0, 2)

        self._interface["input"]["increment"] = QtWidgets.QLineEdit(str(self._increment))
        self._interface["input"]["increment"].setValidator(self._validator)
        self._interface["input"]["increment"].setFixedWidth(50)
        self._interface["layout"]["header"].addWidget(self._interface["input"]["increment"], 0, 3)

        self._interface["button"]["space"] = QtWidgets.QPushButton("Object")
        self._interface["button"]["space"].setFixedWidth(60)
        self._interface["button"]["space"].setStyleSheet("padding: 0")
        self._interface["layout"]["header"].addWidget(self._interface["button"]["space"], 0, 4)

        for transform in self._transforms:

            # stacked widget
            self._interface["widget"][transform] = QtWidgets.QStackedWidget()
            self.main_layout.addWidget(self._interface["widget"][transform])

            # stacked index 0: empty
            self._interface["widget"]["{}_blank".format(transform)] = QtWidgets.QWidget()
            self._interface["widget"][transform].addWidget(self._interface["widget"]["{}_blank".format(transform)])

            # stacked index 1: show button
            self._interface["button"]["{}_show".format(transform)] = QtWidgets.QPushButton("Show {}".format(transform.capitalize()))
            self._interface["button"]["{}_show".format(transform)].setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self._interface["widget"][transform].addWidget(self._interface["button"]["{}_show".format(transform)])

            # stacked index 2: attributes
            self._interface["widget"]["{}_attrs".format(transform)] = QtWidgets.QWidget()
            self._interface["widget"][transform].addWidget(self._interface["widget"]["{}_attrs".format(transform)])

            self._interface["layout"]["{}_attrs".format(transform)] = QtWidgets.QGridLayout()
            self._interface["layout"]["{}_attrs".format(transform)].setVerticalSpacing(0)
            self._interface["layout"]["{}_attrs".format(transform)].setColumnStretch(1, 1)
            self._interface["layout"]["{}_attrs".format(transform)].setContentsMargins(0, 0, 0, 0)
            self._interface["widget"]["{}_attrs".format(transform)].setLayout(self._interface["layout"]["{}_attrs".format(transform)])

            for idx, attr in enumerate(self._transforms[transform]):

                self._interface["checkbox"]["{}_lock".format(attr)] = QtWidgets.QCheckBox()
                self._interface["checkbox"]["{}_lock".format(attr)].setStyleSheet("QCheckBox::indicator {height:15; width:15;}"
                                                                                  "QCheckBox::indicator:unchecked {image: url(" + ICON_URL + "/lock_opened_v2.png)}"
                                                                                  "QCheckBox::indicator:unchecked:hover {image: url(" + ICON_URL + "/lock_opened_hover_v2.png)}"
                                                                                  "QCheckBox::indicator:checked {image: url(" + ICON_URL + "/lock_closed_v2.png)}"
                                                                                  "QCheckBox::indicator:checked:hover {image: url(" + ICON_URL + "/lock_closed_hover_v2.png)}")
                self._interface["layout"]["{}_attrs".format(transform)].addWidget(self._interface["checkbox"]["{}_lock".format(attr)], idx, 0)

                self._interface["label"][attr] = QtWidgets.QLabel("{} {}".format(attr[:-1].capitalize(), attr[-1]))
                self._interface["label"][attr].setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
                self._interface["layout"]["{}_attrs".format(transform)].addWidget(self._interface["label"][attr], idx, 1)

                self._interface["input"][attr] = QtWidgets.QLineEdit("0")
                self._interface["input"][attr].setValidator(self._validator)
                self._interface["input"][attr].setStyleSheet("padding: 0 5")
                self._interface["input"][attr].setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
                self._interface["layout"]["{}_attrs".format(transform)].addWidget(self._interface["input"][attr], idx, 2)

                # increment up down
                self._interface["layout"]["{}_increment".format(attr)] = QtWidgets.QHBoxLayout()
                self._interface["layout"]["{}_increment".format(attr)].setContentsMargins(0, 0, 0, 0)
                self._interface["layout"]["{}_increment".format(attr)].setSpacing(0)
                self._interface["layout"]["{}_attrs".format(transform)].addLayout(self._interface["layout"]["{}_increment".format(attr)], idx, 3)

                self._interface["button"]["{}_down".format(attr)] = QtWidgets.QPushButton("<")
                self._interface["button"]["{}_down".format(attr)].setFixedWidth(23)
                self._interface["button"]["{}_down".format(attr)].setStyleSheet("padding: 0")
                self._interface["layout"]["{}_increment".format(attr)].addWidget(self._interface["button"]["{}_down".format(attr)])

                self._interface["layout"]["{}_increment".format(attr)].addItem(
                    QtWidgets.QSpacerItem(4, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum))

                self._interface["button"]["{}_up".format(attr)] = QtWidgets.QPushButton(">")
                self._interface["button"]["{}_up".format(attr)].setFixedWidth(23)
                self._interface["button"]["{}_up".format(attr)].setStyleSheet("padding: 0")
                self._interface["layout"]["{}_increment".format(attr)].addWidget(self._interface["button"]["{}_up".format(attr)])

            self._interface["button"]["{}_hide".format(transform)] = QtWidgets.QPushButton("Hide")
            self._interface["button"]["{}_hide".format(transform)].setFixedWidth(60)
            self._interface["button"]["{}_hide".format(transform)].setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Expanding)
            self._interface["layout"]["{}_attrs".format(transform)].addWidget(self._interface["button"]["{}_hide".format(transform)], 0, 4, 3, 1)

        self.main_layout.addStretch(1)

        return self._interface

    def _marking_menu(self):

        self._interface["menu"]["main"] = cmds.popupMenu('Menu',
                                                         parent=self.objectName(),
                                                         markingMenu=True)

        self._interface["menu"]["sel_lock"] = cmds.menuItem(label="Lock Selection",
                                                            parent=self._interface["menu"]["main"],
                                                            checkBox=False,
                                                            radialPosition="N",
                                                            command=self._lock_ui_sel)

        self._interface["menu"]["lock_translate"] = cmds.menuItem(label="Lock Translate",
                                                                  parent=self._interface["menu"]["main"],
                                                                  checkBox=False,
                                                                  radialPosition="NE",
                                                                  command=lambda x: self._lock_all(
                                                                      "translate", cmds.menuItem(self._interface["menu"]["lock_translate"], query=True, checkBox=True)))
        self._interface["menu"]["show_translate"] = cmds.menuItem(label="Show Translate",
                                                                  parent=self._interface["menu"]["main"],
                                                                  checkBox=False,
                                                                  radialPosition="E",
                                                                  command=lambda x: self._show_attrs("translate"))

        self._interface["menu"]["lock_rotate"] = cmds.menuItem(label="Lock Rotate",
                                                               parent=self._interface["menu"]["main"],
                                                               checkBox=False,
                                                               radialPosition="NW",
                                                               command=lambda x: self._lock_all(
                                                                   "rotate", cmds.menuItem(self._interface["menu"]["lock_rotate"], query=True, checkBox=True)))
        self._interface["menu"]["show_rotate"] = cmds.menuItem(label="Show Rotate",
                                                               parent=self._interface["menu"]["main"],
                                                               checkBox=False,
                                                               radialPosition="W",
                                                               command=lambda x: self._show_attrs("rotate"))

        self._interface["menu"]["reset"] = cmds.menuItem("Reset",
                                                         parent=self._interface["menu"]["main"],
                                                         radialPosition="S",
                                                         command=self._reset_attr)

    def _connect_signals(self):

        self._interface["checkbox"]["sel_lock"].clicked.connect(self._lock_ui_sel)

        self._interface["button"]["reset"].clicked.connect(self._reset_attr)
        self._interface["button"]["space"].clicked.connect(self._space_switch)

        self._interface["input"]["increment"].editingFinished.connect(self._increment_change)

        self._interface["checkbox"]["translateX_lock"].clicked.connect(lambda: self._lock_attr("translateX"))
        self._interface["checkbox"]["translateY_lock"].clicked.connect(lambda: self._lock_attr("translateY"))
        self._interface["checkbox"]["translateZ_lock"].clicked.connect(lambda: self._lock_attr("translateZ"))

        self._interface["checkbox"]["rotateX_lock"].clicked.connect(lambda: self._lock_attr("rotateX"))
        self._interface["checkbox"]["rotateY_lock"].clicked.connect(lambda: self._lock_attr("rotateY"))
        self._interface["checkbox"]["rotateZ_lock"].clicked.connect(lambda: self._lock_attr("rotateZ"))

        self._interface["input"]["translateX"].editingFinished.connect(
            lambda: cmds.setAttr("{}.translateX".format(self._current_sel), float(self._interface["input"]["translateX"].text())))
        self._interface["input"]["translateY"].editingFinished.connect(
            lambda: cmds.setAttr("{}.translateY".format(self._current_sel), float(self._interface["input"]["translateY"].text())))
        self._interface["input"]["translateZ"].editingFinished.connect(
            lambda: cmds.setAttr("{}.translateZ".format(self._current_sel), float(self._interface["input"]["translateZ"].text())))

        self._interface["input"]["rotateX"].editingFinished.connect(
            lambda: cmds.setAttr("{}.rotateX".format(self._current_sel), float(self._interface["input"]["rotateX"].text())))
        self._interface["input"]["rotateY"].editingFinished.connect(
            lambda: cmds.setAttr("{}.rotateY".format(self._current_sel), float(self._interface["input"]["rotateY"].text())))
        self._interface["input"]["rotateZ"].editingFinished.connect(
            lambda: cmds.setAttr("{}.rotateZ".format(self._current_sel), float(self._interface["input"]["rotateZ"].text())))

        self._interface["button"]["translateX_down"].clicked.connect(lambda: self._set_transform("translateX", True, self._increment * -1))
        self._interface["button"]["translateX_up"].clicked.connect(lambda: self._set_transform("translateX", True, self._increment))
        self._interface["button"]["translateY_down"].clicked.connect(lambda: self._set_transform("translateY", True, self._increment * -1))
        self._interface["button"]["translateY_up"].clicked.connect(lambda: self._set_transform("translateY", True, self._increment))
        self._interface["button"]["translateZ_down"].clicked.connect(lambda: self._set_transform("translateZ", True, self._increment * -1))
        self._interface["button"]["translateZ_up"].clicked.connect(lambda: self._set_transform("translateZ", True, self._increment))

        self._interface["button"]["rotateX_down"].clicked.connect(lambda: self._set_transform("rotateX", False, self._increment * -1))
        self._interface["button"]["rotateX_up"].clicked.connect(lambda: self._set_transform("rotateX", False, self._increment))
        self._interface["button"]["rotateY_down"].clicked.connect(lambda: self._set_transform("rotateY", False, self._increment * -1))
        self._interface["button"]["rotateY_up"].clicked.connect(lambda: self._set_transform("rotateY", False, self._increment))
        self._interface["button"]["rotateZ_down"].clicked.connect(lambda: self._set_transform("rotateZ", False, self._increment * -1))
        self._interface["button"]["rotateZ_up"].clicked.connect(lambda: self._set_transform("rotateZ", False, self._increment))

        self._interface["button"]["translate_show"].clicked.connect(lambda: self._show_attrs("translate"))
        self._interface["button"]["rotate_show"].clicked.connect(lambda: self._show_attrs("rotate"))

        self._interface["button"]["translate_hide"].clicked.connect(lambda: self._show_attrs("translate"))
        self._interface["button"]["rotate_hide"].clicked.connect(lambda: self._show_attrs("rotate"))

    def _sel_changed(self):

        """
        Handles UI updates and callback functions on selection change.

        :return: None
        """

        # return if selection is locked
        if self._sel_locked:
            return

        # get new selection
        sel = "*no selection*"
        if cmds.ls(sl=True):
            sel = cmds.ls(sl=True)[-1]
        self._current_sel = sel

        # update and reset UI
        self._interface["button"]["sel"].setText(self._current_sel.split("|")[-1])
        self._interface["button"]["reset"].setEnabled(False)
        self._interface["widget"]["translate"].setCurrentIndex(0)
        self._interface["widget"]["rotate"].setCurrentIndex(0)

        # try to remove previous AttributeChangedCallback
        try:
            apiOM.MNodeMessage.removeCallback(AB_ChannelBox.attr_change_cb)
            AB_ChannelBox.attr_change_cb = None
        except:
            pass

        cmds.menuItem(self._interface["menu"]["show_translate"], edit=True, checkBox=False, enable=False)
        cmds.menuItem(self._interface["menu"]["lock_translate"], edit=True, checkBox=False, enable=False)
        cmds.menuItem(self._interface["menu"]["show_rotate"], edit=True, checkBox=False, enable=False)
        cmds.menuItem(self._interface["menu"]["lock_rotate"], edit=True, checkBox=False, enable=False)

        # if selection is not empty
        if self._current_sel != "*no selection*":
            # has to be separate if statement in case selection is empty
            if cmds.objectType(self._current_sel) == "transform":

                # activate UI reset button
                self._interface["button"]["reset"].setEnabled(True)

                # show transforms accordingly
                for i in self._transforms.keys():

                    cmds.menuItem(self._interface["menu"]["show_{}".format(i)], edit=True, enable=True)
                    cmds.menuItem(self._interface["menu"]["lock_{}".format(i)], edit=True, enable=True)

                    if self._transform_hidden(i):
                        self._interface["widget"][i].setCurrentIndex(2)
                        cmds.menuItem(self._interface["menu"]["show_{}".format(i)], edit=True, checkBox=True)
                    else:
                        self._interface["widget"][i].setCurrentIndex(1)
                        cmds.menuItem(self._interface["menu"]["show_{}".format(i)], edit=True, checkBox=False)

                # update UI attr values
                for attr in self._channels:
                    self._set_ui_attr(attr)

                # add AttributeChangedCallback to current selection
                sel_mobject = get_mobject(self._current_sel)
                AB_ChannelBox.attr_change_cb = apiOM.MNodeMessage.addAttributeChangedCallback(sel_mobject, self._on_attr_change)

    def _on_attr_change(self, msg, plug, otherPlug, clientData):

        """
        Updates UI based on attribute changes

        :param msg: integer
        :param plug: MPlug
        :param otherPlug: MPlug
        :param clientData: None
        :return: None
        """

        # return if changed attr is not translate or rotate
        if "translate" not in plug.name() and "rotate" not in plug.name():
            return

        plug_name = plug.name()
        # if axis is part of name, remove it - standardized data
        if plug_name[-1] in ["X", "Y", "Z"]:
            plug_name = plug_name[:-1]

        # isolate attr
        attr = plug_name.split(".")[-1]

        # hide attrs by default in UI
        self._interface["widget"][attr].setCurrentIndex(1)

        # default lock state bool
        for axis in ["X", "Y", "Z"]:
            # call function to set attr values in UI
            self._set_ui_attr("{}{}".format(attr, axis))

            # if attrs not hidden, show in UI
            if cmds.getAttr("{}{}".format(plug_name, axis), keyable=True):
                self._interface["widget"][attr].setCurrentIndex(2)

    def _lock_ui_sel(self, *args):

        if self._sel_locked:
            self._sel_locked = False
            self._interface["checkbox"]["sel_lock"].setChecked(self._sel_locked)
            self._interface["button"]["sel"].setStyleSheet("color: #bbbbbb;"
                                                           "background-color: #444444;"
                                                           "border: none;"
                                                           "font-weight: bold;"
                                                           "padding: 0;"
                                                           "text-align: left")
            cmds.menuItem(self._interface["menu"]["sel_lock"], edit=True, checkBox=False)
            self._sel_changed()
        else:
            self._sel_locked = True
            self._interface["checkbox"]["sel_lock"].setChecked(self._sel_locked)
            self._interface["button"]["sel"].setStyleSheet("color: #999999;"
                                                           "background-color: #444444;"
                                                           "border: none;"
                                                           "font-weight: bold;"
                                                           "padding: 0;"
                                                           "text-align: left")
            cmds.menuItem(self._interface["menu"]["sel_lock"], edit=True, checkBox=True)

    def _set_transform(self, attr, tra, increment):

        obj = False
        if self._interface["button"]["space"].text() == "Object":
            obj = True

        values = cmds.xform(self._current_sel, query=True, worldSpace=not obj, objectSpace=obj, translation=tra, rotation=not tra)

        for idx, axis in enumerate(["X", "Y", "Z"]):
            if axis in attr:
                values[idx] = values[idx] + increment

        if "translate" in attr:
            cmds.xform(self._current_sel, worldSpace=not obj, objectSpace=obj, translation=values)
        else:
            cmds.xform(self._current_sel, worldSpace=not obj, objectSpace=obj, rotation=values)

    def _reset_attr(self, *args):

        if self._current_sel == "*no selection*" or cmds.objectType(self._current_sel) != "transform":
            cmds.error("Object is not valid for reset")
            return

        for attr in self._channels:
            if not cmds.getAttr("{}.{}".format(self._current_sel, attr), lock=True):
                self._interface["input"][attr].setText("0")
                cmds.setAttr("{}.{}".format(self._current_sel, attr), 0)

    def _lock_all(self, transform, lock):

        for attr in self._transforms[transform]:
            self._interface["checkbox"]["{}_lock".format(attr)].setChecked(lock)
            self._lock_attr(attr)

    def _lock_attr(self, attr):

        """
        Locks or unlocks object attributes, depending on current state

        :return: None
        """

        if self._interface["checkbox"]["{}_lock".format(attr)].isChecked():
            cmds.setAttr("{}.{}".format(self._current_sel, attr), lock=True)
            cmds.menuItem(self._interface["menu"]["lock_{}".format(attr[:-1])], edit=True, checkBox=True)
        else:
            cmds.setAttr("{}.{}".format(self._current_sel, attr), lock=False)
            if self._transforms_unlocked(attr[:-1]):
                cmds.menuItem(self._interface["menu"]["lock_{}".format(attr[:-1])], edit=True, checkBox=False)

    def _show_attrs(self, transform):

        """
        Locks and hides or unlocks and unhides object attributes, depending on current state

        :return: None
        """

        if self._interface["widget"][transform].currentIndex() == 1:
            print("1")
            cmds.menuItem(self._interface["menu"]["show_{}".format(transform)], edit=True, checkBox=True)
            cmds.menuItem(self._interface["menu"]["lock_{}".format(transform)], edit=True, checkBox=False)
            cmds.setAttr("{}.{}X".format(self._current_sel, transform), keyable=True, lock=False)
            cmds.setAttr("{}.{}Y".format(self._current_sel, transform), keyable=True, lock=False)
            cmds.setAttr("{}.{}Z".format(self._current_sel, transform), keyable=True, lock=False)
        elif self._interface["widget"][transform].currentIndex() == 2:
            cmds.menuItem(self._interface["menu"]["show_{}".format(transform)], edit=True, checkBox=False)
            cmds.menuItem(self._interface["menu"]["lock_{}".format(transform)], edit=True, checkBox=True)
            cmds.setAttr("{}.{}X".format(self._current_sel, transform), keyable=False, lock=True)
            cmds.setAttr("{}.{}Y".format(self._current_sel, transform), keyable=False, lock=True)
            cmds.setAttr("{}.{}Z".format(self._current_sel, transform), keyable=False, lock=True)

    def _transform_hidden(self, transform):

        """
        Returns whether at least on axis of transform is hidden

        :param transform: string
        :return: bool
        """

        for attr in self._transforms[transform]:
            if cmds.getAttr("{}.{}".format(self._current_sel, attr), keyable=True):
                return True
        return False

    def _transforms_unlocked(self, transform):

        """
        Returns whether at least on axis of transform is hidden

        :param transform: string
        :return: bool
        """

        for attr in self._transforms[transform]:
            if cmds.getAttr("{}.{}".format(self._current_sel, attr), lock=True):
                return False
        return True

    def _attr_locked(self, transform):

        """
        Returns whether at least on axis of transform is locked

        :param transform: string
        :return: bool
        """

        for attr in self._transforms[transform]:
            if cmds.getAttr("{}.{}".format(self._current_sel, attr), lock=True):
                return True
        return False

    def _space_switch(self):
        if self._interface["button"]["space"].text() == "Object":
            self._interface["button"]["space"].setText("World")
        else:
            self._interface["button"]["space"].setText("Object")

    def _show_ui_transform(self, show, transform):

        """
        Shows or hides UI attributes, depending on current state

        :param show: bool
        :param transform: string
        :return: None
        """

        if show:
            self._interface["widget"][transform].setCurrentIndex(2)
        else:
            self._interface["widget"][transform].setCurrentIndex(1)

    def _set_ui_attr(self, attr):

        """
        Updates UI attribute values and lock state if check_locks is True

        :param attr: string
        :param check_locks: bool
        :return: None
        """

        # updates UI attribute value with current obj value
        self._interface["input"][attr].setText(
            str((round(cmds.getAttr("{}.{}".format(self._current_sel, attr)), 3) or 0)))

        # locks attribute if conditions apply
        self._lock_ui_attr(attr, lock=False)
        if cmds.getAttr("{}.{}".format(self._current_sel, attr), lock=True):
            cmds.menuItem(self._interface["menu"]["lock_{}".format(attr[:-1])], edit=True, checkBox=True)
            self._lock_ui_attr(attr, lock=True)

    def _lock_ui_attr(self, attr, lock):

        """
        Locks and Unlocks UI transform attributes

        :param attr: string
        :param lock: bool
        :return: None
        """

        # if no object is selected, return from function
        if self._current_sel == "*no selection*":
            return

        self._interface["checkbox"]["{}_lock".format(attr)].setChecked(lock)

        # depending on lock state, enable or disable input line
        self._interface["button"]["{}_down".format(attr)].setEnabled(not lock)
        self._interface["button"]["{}_up".format(attr)].setEnabled(not lock)
        self._interface["input"][attr].setEnabled(not lock)

    def _increment_change(self):

        """
        Updates internal increment values or resets them if input is NULL

        :return: None
        """

        if len(self._interface["input"]["increment"].text()) > 0:
            self._increment = float(self._interface["input"]["increment"].text())
        else:
            self._interface["input"]["increment"].setText(str(self._increment))


def move_obj(obj, user_axis, move_by):

    """moves object along axis

    :param obj: string - name of object you want to move
    :param user_axis: string - user input
    :param move_by: integer - value by how much you want to move the object
    :return: None
    """

    # get positional values from object
    values = cmds.xform(obj, query=True, worldSpace=True, translation=True)

    # iterate through possible axis
    for idx, axis in enumerate(["x", "y", "z"]):
        # until you hit user axis
        if user_axis in axis:
            # replace old axis value with old axis value + move_by value
            values[idx] = values[idx] + move_by

    # move object by new values
    cmds.xform(obj, worldSpace=True, translation=values)


def get_mobject(obj):

    """
    Returns MObject pointer of maya object name string

    :param obj: string
    :return: MObject
    """

    sel_list = apiOM.MSelectionList()
    sel_list.add(obj)
    m_object = apiOM.MObject()
    sel_list.getDependNode(0, m_object)

    return m_object


def _select_obj(obj):
    if cmds.objExists(obj):
        cmds.select(obj)


def clean_up():

    """
    Cleans up left over script jobs and callback
    """

    existing_sj = [_ for _ in cmds.scriptJob(listJobs=True) if "AB_ChannelBox" in _]
    for i in existing_sj:
        cmds.scriptJob(kill=int(i.split(":")[0]))

    try:
        apiOM.MNodeMessage.removeCallback(AB_ChannelBox.attr_change_cb)
    except:
        pass
