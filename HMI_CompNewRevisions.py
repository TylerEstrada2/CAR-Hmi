import sys
import time
import logging
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
    QStackedWidget, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, 
    QSpacerItem, QSizePolicy
)
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QPixmap, QAction
from PySide6.QtCore import Qt, QRect, QMetaObject, Slot, Q_ARG
import can
from cantools.database.can.signal import NamedSignalValue
import cantools
import threading

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

db = cantools.database.load_file("/home/user/Code/CAN14_Update_CAVS_2_17_REV2.dbc")

# Updated PCM_SIGNALS to include MIL_SignalWarning
PCM_SIGNALS = [
    'FEM_Power', 'REM_Power', 'RESS_SOC', 'RESS_Temp',
    'F_MotTmp', 'R_MotTmp', 'F_InvTmp', 'R_InvTmp', 'Master_Warning',
    'Dyno_mode_req_team', 'CACC_light', 'CACC_mileage', 'Dyno_mode_req_sim', 'Headway_time',
    'Target_distance', 'USP_data_rx', 'Vehicle_ahead', 'ActETRS', 'BrakePdlPos', 'AccelPdlPos',
    'UDP_data_received', 'Sim_state', 'Dyno_mode_request', 'DTC_Code',
    'LCC_Status_Placeholder', 'ACC_StopLight_Placeholder',
    'AIN_ACTIVATE_PLACEHOLDER', 'HMI2DMS_ActivateSignal',
    'MIL_SignalWarning'  # Added MIL signal
]

TX_SIGNALS = ['Dyno_mode_req_sim', 'AIN_ACTIVATE_PLACEHOLDER', 'HMI2DMS_ActivateSignal']

MAIN_DASHBOARD_SIGNALS = [
    'Front Motor Power (kW)', 'Rear Motor Power (kW)', 'Battery Temperature (C)',
    'Accelerator Pedal Position (%)', 'Brake Pedal Position (%)', 'Drive Mode', 'DTC'
]

PCM_SIGNALS_PCM = [
    'Front Motor Power (kW)', 'Rear Motor Power (kW)', 'Battery Percentage', 'Battery Temperature (C)',
    'Front Motor Temperature (C)', 'Rear Motor Temperature (C)', 'Front Inverter Temperature (C)', 
    'Rear Inverter Temperature (C)', 'Master_Warning', 'Drive Mode', 'DTC'
]

SIGNAL_NAME_MAPPING = {
    'Front Motor Power (kW)': 'FEM_Power', 'Rear Motor Power (kW)': 'REM_Power',
    'Battery Percentage': 'RESS_SOC', 'Battery Temperature (C)': 'RESS_Temp',
    'Front Motor Temperature (C)': 'F_MotTmp', 'Rear Motor Temperature (C)': 'R_MotTmp',
    'Front Inverter Temperature (C)': 'F_InvTmp', 'Rear Inverter Temperature (C)': 'R_InvTmp',
    'Master_Warning': 'Master_Warning', 'Accelerator Pedal Position (%)': 'AccelPdlPos',
    'Brake Pedal Position (%)': 'BrakePdlPos', 'Drive Mode': 'ActETRS',
    'Headway': 'Headway_time', 'Distance': 'Target_distance', 'DTC': 'DTC_Code'
}

CACC_STATES = {
    1: ("Off", "gray"), 2: ("Active", "green"), 3: ("Acceleration Override, standby", "blue"),
    4: ("Brake Override, Cancel", "white"), 5: ("Off", "gray"), 7: ("Fault", "red")
}

DRIVE_MODE_MAPPING = {0: "Unknown", 1: "Park", 2: "Reverse", 3: "Neutral", 4: "Drive"}

DTC_MAPPING = {0: "No Issues", 1: "Engine Issue", 2: "Battery Issue", 3: "Transmission Issue"}

def init_can_bus():
    retries = 3
    for attempt in range(retries):
        try:
            bus = can.interface.Bus(channel='can0', interface='socketcan', bitrate=500000)
            return bus
        except Exception as e:
            print(f"Error initializing CAN bus: {e}")
            return None

def decode_message(message):
    try:
        return db.decode_message(message.arbitration_id, message.data)
    except Exception as e:
        print(f"Error decoding message: {e}")
        return {}

class VehicleAheadIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.icon_label = QLabel()
        icon_pixmap = QPixmap("/home/user/Code/VehicleAheadIndicator.png")
        icon_pixmap = icon_pixmap.scaled(150, 150)
        self.icon_label.setPixmap(icon_pixmap)
        self.icon_label.setFixedSize(150, 150)
        self.update_color()
        layout.addWidget(self.icon_label)

    def update_color(self):
        color = "green" if self.state == 1 else "gray"
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state
        self.update_color()

class CACCIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.icon_label = QLabel()
        self.icon_pixmap = QPixmap("/home/user/Code/CACCIndicator_transparent.png")
        self.icon_pixmap = self.icon_pixmap.scaled(150, 150, Qt.KeepAspectRatio)
        self.icon_label.setPixmap(self.icon_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(150, 150)
        self.update_color()
        layout.addWidget(self.icon_label)

    def update_color(self):
        _, color = CACC_STATES.get(self.state, ("Unknown", "gray"))
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state
        self.update_color()

class LCCIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.icon_label = QLabel()
        self.icon_pixmap = QPixmap("/home/user/Code/LCCIndicator_transparent.png")
        self.icon_pixmap = self.icon_pixmap.scaled(150, 150, Qt.KeepAspectRatio)
        self.icon_label.setPixmap(self.icon_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(150, 150)
        self.update_color()
        layout.addWidget(self.icon_label)

    def update_color(self):
        color = "green" if self.state == 1 else "gray"
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state if state in [0, 1] else 0
        self.update_color()

class TrafficLightIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.icons = {}
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.icon_label = QLabel()
        self.icons[0] = QPixmap("/home/user/Code/TrafficLightNone.png").scaled(150, 150, Qt.KeepAspectRatio)
        self.icons[1] = QPixmap("/home/user/Code/TrafficLightGreen.png").scaled(150, 150, Qt.KeepAspectRatio)
        self.icons[2] = QPixmap("/home/user/Code/TrafficLightYellow.png").scaled(150, 150, Qt.KeepAspectRatio)
        self.icons[3] = QPixmap("/home/user/Code/TrafficLightRed.png").scaled(150, 150, Qt.KeepAspectRatio)
        self.update_icon()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(150, 150)
        layout.addWidget(self.icon_label)

    def update_icon(self):
        state = self.state if self.state in self.icons else 0
        self.icon_label.setPixmap(self.icons[state])

    @Slot(int)
    def set_state(self, state):
        self.state = state if state in [0, 1, 2, 3] else 0
        self.update_icon()

class BatteryWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.charge = 0
        self.setFixedSize(400, 100)

    @Slot(int)
    def set_charge(self, charge):
        self.charge = min(charge, 100)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        bar_width = (rect.width() - 10) // 4
        bar_height = rect.height() - 10
        gap = 2
        for i in range(4):
            x = rect.left() + 5 + i * (bar_width + gap)
            y = rect.top() + 5
            if self.charge > i * 25:
                painter.setBrush(QColor(0, 255, 0))
            else:
                painter.setBrush(Qt.gray)
            painter.drawRect(QRect(x, y, bar_width, bar_height))

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autonomous Vehicle HMI")
        self.setStyleSheet("background-color: #555F61; color: white;")
        self.showFullScreen()

        self.exit_fullscreen_action = QAction("Exit Fullscreen", self)
        self.exit_fullscreen_action.setShortcut("Esc")
        self.exit_fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(self.exit_fullscreen_action)

        self.signals = PCM_SIGNALS
        self.txsignals = TX_SIGNALS
        self.signal_units = {}
        for message in db.messages:
            for signal in message.signals:
                if signal.name in self.signals:
                    self.signal_units[signal.name] = signal.unit or ""
        self.signal_values = {signal: "-" for signal in self.signals}

        self.bus = init_can_bus()
        if self.bus is None:
            self.showErrorDialog("Failed to initialize CAN bus. Exiting...")
            sys.exit(1)

        self.dyno_mode_active = False
        self.dyno_mode_lock = threading.Lock()
        self.dyno_thread_running = True
        self.dyno_send_thread = threading.Thread(target=self.send_dyno_messages, daemon=True)
        self.dyno_send_thread.start()

        self.ain_mode_active = False
        self.ain_mode_lock = threading.Lock()
        self.ain_thread_running = True
        self.ain_send_thread = threading.Thread(target=self.send_ain_messages, daemon=True)
        self.ain_send_thread.start()

        self.dms_active = False
        self.dms_mode_lock = threading.Lock()
        self.dms_thread_running = True
        self.dms_send_thread = threading.Thread(target=self.send_dms_messages, daemon=True)
        self.dms_send_thread.start()

        self.battery_widgets = []
        self.battery_labels = []
        self.dtc_labels = []
        self.mil_indicator = None  # Add MIL indicator attribute

        self.initUI()
        self.can_listener_thread = threading.Thread(target=self.listen_can_messages, daemon=True)
        self.can_listener_thread.start()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def send_dyno_messages(self):
        while self.dyno_thread_running:
            with self.dyno_mode_lock:
                value = 1 if self.dyno_mode_active else 0
            self.send_can_message(value)
            time.sleep(0.01)

    def send_ain_messages(self):
        while self.ain_thread_running:
            with self.ain_mode_lock:
                value = 0 if self.ain_mode_active else 1
            self.send_ain_can_message(value)
            time.sleep(0.01)

    def send_dms_messages(self):
        while self.dms_thread_running:
            with self.dms_mode_lock:
                value = 1 if self.dms_active else 0
            self.send_dms_can_message(value)
            time.sleep(0.01)

    def send_can_message(self, value):
        try:
            message_id = 0x519
            signal_name = "Dyno_mode_req_team"
            data = db.encode_message(message_id, {signal_name: value}, strict=False)
            can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
            self.bus.send(can_msg)
            logger.info(f"Sent CAN message: ID={hex(message_id)}, Data={data.hex()}")
        except Exception as e:
            logger.error(f"Error sending CAN message: {e}")

    def send_ain_can_message(self, value):
        try:
            message_id = 0x520
            signal_name = "AIN_ACTIVATE_PLACEHOLDER"
            data = db.encode_message(message_id, {signal_name: value}, strict=False)
            can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
            self.bus.send(can_msg)
            logger.info(f"Sent AIN CAN message: ID={hex(message_id)}, Data={data.hex()}")
        except Exception as e:
            logger.error(f"Error sending AIN CAN message: {e}")

    def send_dms_can_message(self, value):
        try:
            message_id = 0x521
            signal_name = "HMI2DMS_ActivateSignal"
            data = db.encode_message(message_id, {signal_name: value}, strict=False)
            can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
            self.bus.send(can_msg)
            logger.info(f"Sent DMS CAN message: ID={hex(message_id)}, Data={data.hex()}")
        except Exception as e:
            logger.error(f"Error sending DMS CAN message: {e}")

    def listen_can_messages(self):
        while True:
            try:
                msg = self.bus.recv(timeout=0.1)
                if msg:
                    decoded = decode_message(msg)
                    logger.debug(f"Decoded message: {decoded}")
                    for signal in self.signals:
                        if signal in decoded:
                            value = decoded[signal]
                            if isinstance(value, NamedSignalValue):
                                value = value.value
                            elif isinstance(value, bool):
                                value = 1 if value else 0
                            self.signal_values[signal] = value
                            logger.info(f"Signal: {signal}, Value: {value}, Type: {type(value)}")
                            if signal == 'ActETRS':
                                drive_mode = DRIVE_MODE_MAPPING.get(int(value), "Unknown")
                                QMetaObject.invokeMethod(self, "update_drive_mode_display", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(str, drive_mode))
                            else:
                                if isinstance(value, int):
                                    QMetaObject.invokeMethod(self, "update_signal_display_int", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(int, value))
                                elif isinstance(value, float):
                                    QMetaObject.invokeMethod(self, "update_signal_display_float", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(float, value))
                                elif isinstance(value, str):
                                    QMetaObject.invokeMethod(self, "update_signal_display_str", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(str, value))
                                else:
                                    logger.warning(f"Unsupported type for signal {signal}: {type(value)}")
            except Exception as e:
                logger.error(f"Error processing CAN message: {e}")
                time.sleep(0.1)

    @Slot(str, str)
    def update_drive_mode_display(self, signal_name, value):
        if signal_name == 'ActETRS':
            logger.debug(f"Received ActETRS signal: {value}, Type: {type(value)}")
            drive_mode = value
            row = MAIN_DASHBOARD_SIGNALS.index('Drive Mode')
            self.pcm_table_main.setItem(row, 1, QTableWidgetItem(drive_mode))
            if hasattr(self, 'pcm_table'):
                row = PCM_SIGNALS_PCM.index('Drive Mode')
                self.pcm_table.setItem(row, 1, QTableWidgetItem(drive_mode))

    @Slot(str, object)
    def update_signal_display(self, signal_name, value):
        if hasattr(value, 'name'):
            value = value.name
        logger.info(f"Processing signal: {signal_name}, Value: {value}")
        if signal_name == 'ActETRS':
            return
        if signal_name == 'CACC_light':
            self.cacc_indicator.set_state(int(value))
        elif signal_name == 'Vehicle_ahead':
            self.VAI_Indicator.set_state(int(value))
        elif signal_name == 'Sim_state':
            color = "green" if value == 1 else "white"
            self.sim_active_label.setStyleSheet(f"color: {color};")
        elif signal_name == 'Dyno_mode_request':
            color = "green" if value == 1 else "white"
            self.dyno_request_label.setStyleSheet(f"color: {color};")
        elif signal_name == 'UDP_data_received':
            color = "green" if value == 1 else "white"
            self.sim_udp_label.setStyleSheet(f"color: {color};")
        elif signal_name == 'DTC_Code':
            dtc_desc = DTC_MAPPING.get(int(value), "Unknown")
            row = MAIN_DASHBOARD_SIGNALS.index('DTC')
            self.pcm_table_main.setItem(row, 1, QTableWidgetItem(dtc_desc))
            if 'DTC' in PCM_SIGNALS_PCM:
                row = PCM_SIGNALS_PCM.index('DTC')
                self.pcm_table.setItem(row, 1, QTableWidgetItem(dtc_desc))
            if int(value) == 0:  # "No Issues"
                if self.dtc_label in self.header_layout.children():
                    self.header_layout.removeWidget(self.dtc_label)
                    self.dtc_label.setParent(None)
            else:
                if self.dtc_label not in self.header_layout.children():
                    self.header_layout.insertWidget(2, self.dtc_label)
            for label in self.dtc_labels:
                label.setText(f"DTC: {dtc_desc}")
        elif signal_name == 'LCC_Status_Placeholder':
            self.lcc_indicator.set_state(int(value))
        elif signal_name == 'ACC_StopLight_Placeholder':
            self.traffic_light_indicator.set_state(int(value))
        elif signal_name == 'MIL_SignalWarning':
            self.mil_indicator.setVisible(bool(value))

        if isinstance(value, float):
            rounded_value = round(value, 1)
        else:
            rounded_value = value

        if signal_name == 'RESS_SOC':
            soc_rounded = round(value, 1)
            for label, widget in zip(self.battery_labels, self.battery_widgets):
                label.setText(f"Battery: {soc_rounded}%")
                widget.set_charge(soc_rounded)
            mapped_name = SIGNAL_NAME_MAPPING.get('Battery Percentage')
            if mapped_name and mapped_name in PCM_SIGNALS_PCM:
                row = PCM_SIGNALS_PCM.index(mapped_name)
                self.pcm_table.setItem(row, 1, QTableWidgetItem(str(soc_rounded)))

        mapped_name = None
        for new_name, original_name in SIGNAL_NAME_MAPPING.items():
            if original_name == signal_name:
                mapped_name = new_name
                break

        if mapped_name:
            if mapped_name in PCM_SIGNALS_PCM:
                row = PCM_SIGNALS_PCM.index(mapped_name)
                self.pcm_table.setItem(row, 1, QTableWidgetItem(str(rounded_value)))
                logger.info(f"Updated {mapped_name} in PCM table: {rounded_value}")
            if mapped_name in MAIN_DASHBOARD_SIGNALS:
                row = MAIN_DASHBOARD_SIGNALS.index(mapped_name)
                self.pcm_table_main.setItem(row, 1, QTableWidgetItem(str(rounded_value)))

        if signal_name == 'RESS_Temp':
            self.battery_temp_label.setText(f"Battery Temperature: {rounded_value} °C")
        elif signal_name == 'FEM_Power':
            self.front_motor_power_label.setText(f"Front Motor Power: {round(rounded_value/1000,3)} kW")
        elif signal_name == 'REM_Power':
            self.rear_motor_power_label.setText(f"Rear Motor Power: {round(rounded_value/1000,3)} kW")
        elif signal_name == 'AccelPdlPos':
            row = MAIN_DASHBOARD_SIGNALS.index('Accelerator Pedal Position (%)')
            self.pcm_table_main.setItem(row, 1, QTableWidgetItem(f"{rounded_value}%"))
        elif signal_name == 'BrakePdlPos':
            row = MAIN_DASHBOARD_SIGNALS.index('Brake Pedal Position (%)')
            self.pcm_table_main.setItem(row, 1, QTableWidgetItem(f"{rounded_value}%"))
        elif signal_name == 'Target_distance':
            self.VAI_Distance_Label.setText(f"Distance: {rounded_value} m" if rounded_value != 0.0 else "Distance: N/A")
        elif signal_name == 'Headway_time':
            self.VAI_Headway_Label.setText(f"Headway: {rounded_value} s" if rounded_value != 0.0 else "Headway: N/A")
        elif signal_name == 'CACC_mileage':
            self.cacc_mileage_label.setText(f"Current CACC Mileage: {round(rounded_value*0.621371,1)} mi")

    def toggle_dyno_icon(self):
        button = self.sender()
        button.setFixedSize(200, 100)
        with self.dyno_mode_lock:
            if button.isChecked():
                button.setStyleSheet("background-color: green; color: white;")
                self.dyno_mode_active = True
            else:
                button.setStyleSheet("background-color: gray; color: black;")
                self.dyno_mode_active = False

    def toggle_ain_button(self):
        button = self.sender()
        with self.ain_mode_lock:
            if button.isChecked():
                button.setStyleSheet("background-color: green; color: white;")
                self.ain_mode_active = True
            else:
                button.setStyleSheet("background-color: gray; color: black;")
                self.ain_mode_active = False

    def toggle_dms_icon(self):
        button = self.sender()
        button.setFixedSize(200, 100)
        with self.dms_mode_lock:
            if button.isChecked():
                button.setStyleSheet("background-color: green; color: white;")
                self.dms_active = True
            else:
                button.setStyleSheet("background-color: gray; color: black;")
                self.dms_active = False

    @Slot(str, int)
    def update_signal_display_int(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    @Slot(str, float)
    def update_signal_display_float(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    @Slot(str, str)
    def update_signal_display_str(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    def initUI(self):
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)

        self.header_layout = QHBoxLayout()
        self.header_layout.setSpacing(50)
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #555F61;")
        header_widget.setLayout(self.header_layout)

        battery_container = QWidget()
        battery_layout = QHBoxLayout(battery_container)
        self.battery_widget = BatteryWidget()
        self.battery_label = QLabel("Battery: N/A%")
        self.battery_label.setFont(QFont("Arial", 24))
        battery_layout.addWidget(self.battery_widget)
        battery_layout.addWidget(self.battery_label)
        self.header_layout.addWidget(battery_container)

        self.header_layout.addSpacerItem(QSpacerItem(100, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        self.dtc_label = QLabel("DTC: No Issues")
        self.dtc_label.setFont(QFont("Arial", 20))

        self.mil_indicator = QLabel()
        mil_pixmap = QPixmap("Home/Code/MIL.png")  # Replace with actual path
        mil_pixmap = mil_pixmap.scaled(60, 60, Qt.KeepAspectRatio)
        self.mil_indicator.setPixmap(mil_pixmap)
        self.mil_indicator.setVisible(False)
        self.header_layout.addWidget(self.mil_indicator)
        self.header_layout.addSpacerItem(QSpacerItem(40, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

        self.ain_button = QPushButton("AIN ACTIVATE")
        self.ain_button.setFixedSize(200, 60)
        self.ain_button.setCheckable(True)
        self.ain_button.setStyleSheet("background-color: gray; color: black;")
        self.ain_button.clicked.connect(self.toggle_ain_button)
        self.header_layout.addWidget(self.ain_button)

        self.header_layout.addStretch()
        self.main_layout.addWidget(header_widget)

        self.battery_widgets = [self.battery_widget]
        self.battery_labels = [self.battery_label]
        self.dtc_labels = [self.dtc_label]

        self.top_bar = QHBoxLayout()
        screen_names = ["Dyno Mode", "PCM", "ACC", "LCC", "AIN"]
        for i, name in enumerate(screen_names):
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, index=i: self.switch_screen(index + 1))
            btn.setFixedSize(230, 60)
            self.top_bar.addWidget(btn)
        self.main_layout.addLayout(self.top_bar)

        self.stacked_widget = QStackedWidget()
        self.main_screen = QWidget()
        self.initMainScreen()
        self.stacked_widget.addWidget(self.main_screen)

        self.dyno_mode = self.create_dyno_screen()
        self.pcm = self.create_pcm_screen()
        self.acc = self.create_acc_screen()
        self.lcc = self.create_lcc_screen()
        self.ain = self.create_ain_screen()

        self.stacked_widget.addWidget(self.dyno_mode)
        self.stacked_widget.addWidget(self.pcm)
        self.stacked_widget.addWidget(self.acc)
        self.stacked_widget.addWidget(self.lcc)
        self.stacked_widget.addWidget(self.ain)

        self.main_layout.addWidget(self.stacked_widget)

        self.setLayout(self.main_layout)

    def showErrorDialog(self, error_message):
        error_dialog = QMessageBox(self)
        error_dialog.setWindowTitle("Error")
        error_dialog.setText(f"{error_message} error occurred. Consult manual to fix.")
        error_dialog.setStandardButtons(QMessageBox.Ok)

    def initMainScreen(self):
        main_layout = QVBoxLayout(self.main_screen)
        content_layout = QHBoxLayout()

        dms_container = QHBoxLayout()
        dms_label = QLabel("Activate DMS System:")
        dms_label.setFont(QFont("Arial", 28))
        dms_container.addWidget(dms_label)
        self.dms_button = QPushButton("DMS")
        self.dms_button.setFixedSize(200, 100)
        self.dms_button.setCheckable(True)
        self.dms_button.setStyleSheet("background-color: gray; color: black;")
        self.dms_button.clicked.connect(self.toggle_dms_icon)
        dms_container.addWidget(self.dms_button)
        content_layout.addLayout(dms_container)

        self.pcm_table_main = QTableWidget()
        self.pcm_table_main.setRowCount(len(MAIN_DASHBOARD_SIGNALS))
        self.pcm_table_main.setColumnCount(2)
        self.pcm_table_main.setHorizontalHeaderLabels(["Signal", "Value"])
        self.pcm_table_main.verticalHeader().setVisible(False)
        self.pcm_table_main.setFixedWidth(960)
        self.pcm_table_main.setMinimumHeight(400)
        
        table_font = QFont("Arial", 24)
        self.pcm_table_main.setFont(table_font)
        
        for row in range(self.pcm_table_main.rowCount()):
            self.pcm_table_main.setRowHeight(row, 80)
        for row, signal in enumerate(MAIN_DASHBOARD_SIGNALS):
            signal_item = QTableWidgetItem(signal)
            value_item = QTableWidgetItem("0" if signal not in ['Drive Mode', 'DTC'] else "Unknown" if signal == 'Drive Mode' else "No Issues")
            signal_item.setFont(table_font)
            value_item.setFont(table_font)
            self.pcm_table_main.setItem(row, 0, signal_item)
            self.pcm_table_main.setItem(row, 1, value_item)
        self.pcm_table_main.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        content_layout.addWidget(self.pcm_table_main)

        main_layout.addLayout(content_layout)
        main_layout.addStretch()

    def create_dyno_screen(self):
        dyno_screen = QWidget()
        screen_layout = QVBoxLayout(dyno_screen)

        dyno_layout = QHBoxLayout()
        dyno_label = QLabel("Activate Dyno Mode:")
        dyno_label.setFont(QFont("Arial", 28))
        dyno_layout.addWidget(dyno_label)
        self.dyno_button = QPushButton()
        self.dyno_button.setFixedSize(200, 100)
        self.dyno_button.setCheckable(True)
        self.dyno_button.setStyleSheet("background-color: gray; color: black;")
        self.dyno_button.clicked.connect(self.toggle_dyno_icon)
        dyno_layout.addWidget(self.dyno_button)
        screen_layout.addLayout(dyno_layout)

        self.sim_udp_label = QLabel("Sim UDP received and byte count")
        self.sim_udp_label.setFont(QFont("Arial", 28))
        self.sim_udp_label.setStyleSheet("color: white;")
        screen_layout.addWidget(self.sim_udp_label, alignment=Qt.AlignLeft)
        self.dyno_request_label = QLabel("Request for Dyno Mode")
        self.dyno_request_label.setFont(QFont("Arial", 28))
        self.dyno_request_label.setStyleSheet("color: white;")
        screen_layout.addWidget(self.dyno_request_label, alignment=Qt.AlignLeft)
        self.sim_active_label = QLabel("Sim Active")
        self.sim_active_label.setFont(QFont("Arial", 28))
        self.sim_active_label.setStyleSheet("color: white;")
        screen_layout.addWidget(self.sim_active_label, alignment=Qt.AlignLeft)

        back_button = QPushButton("Back to Main Dashboard")
        back_button.setFixedSize(1000, 100)
        back_button.clicked.connect(lambda: self.switch_screen(0))
        screen_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
        return dyno_screen

    def create_pcm_screen(self):
        pcm_screen = QWidget()
        pcm_layout = QVBoxLayout(pcm_screen)

        self.pcm_table = QTableWidget()
        self.pcm_table.setRowCount(len(PCM_SIGNALS_PCM))
        self.pcm_table.setColumnCount(2)
        self.pcm_table.setHorizontalHeaderLabels(["Signal", "Value"])
        self.pcm_table.verticalHeader().setVisible(False)
        self.pcm_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pcm_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row, signal in enumerate(PCM_SIGNALS_PCM):
            signal_item = QTableWidgetItem(signal)
            value_item = QTableWidgetItem("0" if signal != 'DTC' else "No Issues")
            self.pcm_table.setItem(row, 0, signal_item)
            self.pcm_table.setItem(row, 1, value_item)
        pcm_layout.addWidget(self.pcm_table)

        back_button = QPushButton("Back to Main Dashboard")
        back_button.setFixedSize(1000, 100)
        back_button.clicked.connect(lambda: self.switch_screen(0))
        pcm_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
        return pcm_screen

    def create_acc_screen(self):
        acc_screen = QWidget()
        acc_layout = QVBoxLayout(acc_screen)

        cacc_layout = QHBoxLayout()
        cacc_layout.setSpacing(100)
        self.cacc_indicator = CACCIndicator()
        cacc_layout.addWidget(self.cacc_indicator)
        self.cacc_mileage_label = QLabel("Current CACC Mileage: N/A")
        self.cacc_mileage_label.setFont(QFont("Arial", 20, QFont.Bold))
        cacc_layout.addWidget(self.cacc_mileage_label)
        cacc_layout.addStretch()
        acc_layout.addLayout(cacc_layout)

        vai_layout = QHBoxLayout()
        vai_layout.setSpacing(100)
        self.VAI_Indicator = VehicleAheadIndicator()
        vai_layout.addWidget(self.VAI_Indicator)
        self.VAI_Headway_Label = QLabel("Headway: N/A")
        self.VAI_Headway_Label.setFont(QFont("Arial", 20, QFont.Bold))
        vai_layout.addWidget(self.VAI_Headway_Label)
        self.VAI_Distance_Label = QLabel("Distance: N/A")
        self.VAI_Distance_Label.setFont(QFont("Arial", 20, QFont.Bold))
        vai_layout.addWidget(self.VAI_Distance_Label)
        vai_layout.addStretch()
        acc_layout.addLayout(vai_layout)

        traffic_light_layout = QHBoxLayout()
        self.traffic_light_indicator = TrafficLightIndicator()
        traffic_light_layout.addWidget(self.traffic_light_indicator, alignment=Qt.AlignCenter)
        traffic_light_layout.addStretch()
        acc_layout.addLayout(traffic_light_layout)

        acc_layout.addStretch()

        back_button = QPushButton("Back to Main Dashboard")
        back_button.setFixedSize(1000, 100)
        back_button.clicked.connect(lambda: self.switch_screen(0))
        acc_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
        return acc_screen

    def create_lcc_screen(self):
        lcc_screen = QWidget()
        lcc_layout = QVBoxLayout(lcc_screen)

        lcc_indicator_layout = QHBoxLayout()
        self.lcc_indicator = LCCIndicator()
        lcc_indicator_layout.addWidget(self.lcc_indicator, alignment=Qt.AlignCenter)
        lcc_indicator_layout.addStretch()
        lcc_layout.addLayout(lcc_indicator_layout)

        lcc_layout.addStretch()

        back_button = QPushButton("Back to Main Dashboard")
        back_button.setFixedSize(1000, 100)
        back_button.clicked.connect(lambda: self.switch_screen(0))
        lcc_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
        return lcc_screen

    def create_ain_screen(self):
        ain_screen = QWidget()
        ain_layout = QVBoxLayout(ain_screen)

        ain_label = QLabel("AIN Content")
        ain_label.setAlignment(Qt.AlignCenter)
        ain_layout.addWidget(ain_label)

        back_button = QPushButton("Back to Main Dashboard")
        back_button.setFixedSize(1000, 100)
        back_button.clicked.connect(lambda: self.switch_screen(0))
        ain_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
        return ain_screen

    def switch_screen(self, index):
        self.stacked_widget.setCurrentIndex(index)

    def closeEvent(self, event):
        self.dyno_thread_running = False
        self.ain_thread_running = False
        self.dms_thread_running = False
        if self.bus:
            self.bus.shutdown()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    globalFont = QFont("Arial", 18)
    app.setFont(globalFont)
    window = Dashboard()       
    window.showFullScreen()
    sys.exit(app.exec())
