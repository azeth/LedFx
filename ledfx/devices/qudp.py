import logging
import socket
from struct import pack

import numpy as np
import voluptuous as vol

from ledfx.devices import Device
from ledfx.utils import (
    resolve_destination,
)

_LOGGER = logging.getLogger(__name__)

class QUDPConnection:
    DATA_PACKET = 0
    RESET_PACKET = 1
    SETUP_PACKET = 2
    POWER_PACKET = 5
    MAGIC_NUMBER = 3042937533
    QUEUE_LENGTH = 8

    def __init__(self, ip, port) -> None:
        self.ip = ip
        self.port = port

        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        self.udp.connect((self.ip, self.port))

    def power(self, state) -> None:
        if state == True:
            flag = 1
        else:
            flag = 0

        data = pack('<IBB', self.MAGIC_NUMBER, self.POWER_PACKET, flag)
        self.udp.send(data)

    def send(self, strip_num, frame_num, frame_data) -> None:
        data = pack('<IBBIH', self.MAGIC_NUMBER, self.DATA_PACKET, strip_num, frame_num, len(frame_data))
        
        byte_data = frame_data.astype(np.dtype("B"))
        data += byte_data.flatten().tobytes()
        self.udp.send(data)

    def reset(self, strip_num) -> None:
        data = pack('<IBB', self.MAGIC_NUMBER, self.RESET_PACKET, strip_num)
        self.udp.send(data)

    def setup(self, queue_len, refresh_rate) -> None:
        self.refresh_rate = refresh_rate
        frame_time = int(1000000/refresh_rate)
        
        data = pack('<IBBI', self.MAGIC_NUMBER, self.SETUP_PACKET, queue_len, frame_time)
        self.udp.send(data)

class QUDPManager:
    def __init__(self) -> None:
        self._devices = []
        self._hosts = {}
        self._connections = {}
    
    def add(self, device) -> QUDPConnection:
        if device not in self._devices:
            addr = (device.ip_address, device.port)

            if addr not in self._hosts:
                connection = QUDPConnection(addr[0], addr[1])
                connection.setup(QUDPConnection.QUEUE_LENGTH, device._config["refresh_rate"])
                self._connections[addr] = connection
                self._hosts[addr] = []
            else:
                connection = self._connections[addr]

            self._devices.append(device)
            self._hosts[addr].append(device)

            return connection

    def remove(self, device) -> None:
        if device in self._devices:
            addr = (device.ip_address, device.port)

            self._hosts[addr].remove(device)
            self._devices.remove(device)

            if self._hosts[addr] == []:
                self._connections.pop(addr)
                self._hosts.pop(addr)


    def refresh_rate(self, device):
        if device in self._devices:
            addr = (device.ip_address, device.port)
            return self._connections[addr].refresh_rate


_MANAGER = QUDPManager()

class QUDPDevice(Device):
    """QUDP device support"""

    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Required(
                "name", description="Friendly name for the device"
            ): str,
            vol.Required(
                "ip_address",
                description="Hostname or IP address of the device",
            ): str,
            vol.Required(
                "port", description="Port for the UDP device"
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                "pixel_count",
                description="Number of individual pixels",
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            vol.Required(
                "strip_index",
                description="Index of individual UDP strip",
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
        }
    )

    def activate(self):
        # check if ip/hostname resolves okay
        self.ip_address = self._config["ip_address"]
        self.port = self._config["port"]

        self._frame_id = 0
        self._connection = _MANAGER.add(self)
        
        self._connection.power(True)
        self._connection.reset(self._config["strip_index"])
        
        super().activate()

    def deactivate(self):
        super().deactivate()
        
        self._connection.power(False)
        _MANAGER.remove(self)

        self._frame_id = 0
        self._connection = None

    @property
    def pixel_count(self):
        return int(self._config["pixel_count"])

    def flush(self, data):
        self._connection.send(self._config["strip_index"]-1, self._frame_id, data)
        self._frame_id += 1
    
    @property
    def refresh_rate(self):
        return _MANAGER.refresh_rate(self)
