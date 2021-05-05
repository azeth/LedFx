import asyncio
import logging
import time
from abc import abstractmethod
from functools import cached_property

import numpy as np
import voluptuous as vol
import zeroconf

from ledfx.config import save_config
from ledfx.events import DeviceUpdateEvent, Event
from ledfx.utils import (
    WLED,
    BaseRegistry,
    RegistryLoader,
    async_fire_and_forget,
    generate_id,
    resolve_destination,
)

_LOGGER = logging.getLogger(__name__)


@BaseRegistry.no_registration
class Device(BaseRegistry):

    CONFIG_SCHEMA = vol.Schema(
        {
            # vol.Optional(
            #     "rgbw_led",
            #     description="RGBW LEDs",
            #     default=False,
            # ): bool,
            vol.Optional(
                "icon_name",
                description="https://material-ui.com/components/material-icons/",
                default="mdi:led-strip",
            ): str,
            vol.Optional(
                "center_offset",
                description="Number of pixels from the perceived center of the device",
                default=0,
            ): int,
            vol.Optional(
                "refresh_rate",
                description="Maximum rate that pixels are sent to the device",
                default=60,
            ): int,
            vol.Optional(
                "silence_timeout",
                description="How many seconds of silence until we deactivate the device. 0 = Disabled.",
                default=0,
            ): int,
        }
    )

    _active = False

    def __init__(self, ledfx, config):
        self._ledfx = ledfx
        self._config = config
        self._segments = []
        self._pixels = None
        self._silence_start = None

    def __del__(self):
        if self._active:
            self.deactivate()

    def update_config(self, config):
        # TODO: Sync locks to ensure everything is thread safe
        if self._config is not None:
            config = self._config | config

        validated_config = type(self).schema()(config)
        self._config = validated_config

        # Iterate all the base classes and check to see if there is a custom
        # implementation of config updates. If to notify the base class.
        valid_classes = list(type(self).__bases__)
        valid_classes.append(type(self))
        for base in valid_classes:
            if hasattr(base, "config_updated"):
                if base.config_updated != super(base, base).config_updated:
                    base.config_updated(self, validated_config)

        _LOGGER.info(
            f"Device {self.name} config updated to {validated_config}."
        )

        for display in self._displays_objs:
            display.deactivate_segments()
            display.activate_segments(display._segments)

    def config_updated(self, config):
        """
        to be reimplemented by child classes
        """
        pass

    @property
    def pixel_count(self):
        return int(self._config["pixel_count"])

    def is_active(self):
        return self._active

    def update_pixels(self, display_id, data):
        # update each segment from this display
        if not self._active:
            _LOGGER.warning(
                f"Cannot update pixels of inactive device {self.name}"
            )
            return

        # This looks horrid but it seems to work.
        if (
            self._ledfx.audio is not None
            and self._ledfx.audio._volume == 0
            and self._silence_start is None
        ):
            self._silence_start = time.time()

            self._silence_timeout = self._silence_start + float(
                self._config["silence_timeout"]
            )
        elif self._ledfx.audio is not None and self._ledfx.audio._volume != 0:

            self._silence_start = None

        if (
            self._silence_start is not None
            and self._config["silence_timeout"] > 0
        ):
            if time.time() >= self._silence_timeout:
                _LOGGER.info(
                    f"Inactivity Timeout Reached. Deactivating {self._config['name']}"
                )
                for display in self._displays_objs:
                    display.clear_effect()
                    display.deactivate_segments()
                self.deactivate()
                self._silence_start = None
                self._silence_timeout = None
                return

        for pixels, start, end in data:
            self._pixels[start : end + 1] = pixels

        if display_id == self.priority_display.id:
            frame = self.assemble_frame()
            self.flush(frame)
            # _LOGGER.debug(f"Device {self.id} flushed by Display {display_id}")

            def trigger_device_update_event():
                self._ledfx.events.fire_event(
                    DeviceUpdateEvent(self.id, frame)
                )

            self._ledfx.loop.call_soon_threadsafe(trigger_device_update_event)

    def assemble_frame(self):
        """
        Assembles the frame to be flushed. Currently this will just return
        the active channels pixels, but will eventually handle things like
        merging multiple segments segments and alpha blending channels
        """
        frame = self._pixels

        if self._config["center_offset"]:
            frame = np.roll(frame, self._config["center_offset"], axis=0)
        return frame

    def activate(self):
        self._pixels = np.zeros((self.pixel_count, 3))
        self._active = True

    def deactivate(self):
        self._pixels = None
        self._active = False
        # self.flush(np.zeros((self.pixel_count, 3)))

    @abstractmethod
    def flush(self, data):
        """
        Flushes the provided data to the device. This abstract method must be
        overwritten by the device implementation.
        """

    @property
    def name(self):
        return self._config["name"]

    @property
    def max_refresh_rate(self):
        return self._config["refresh_rate"]

    @property
    def refresh_rate(self):
        return self.priority_display.refresh_rate

    @cached_property
    def priority_display(self):
        """
        Returns the first display that has the highest refresh rate of all displays
        associated with this device
        """
        if not any(display.active for display in self._displays_objs):
            return None

        refresh_rate = max(
            display.refresh_rate
            for display in self._displays_objs
            if display.active
        )
        return next(
            display
            for display in self._displays_objs
            if display.refresh_rate == refresh_rate
        )

    @cached_property
    def _displays_objs(self):
        return list(
            self._ledfx.displays.get(display_id)
            for display_id in self.displays
        )

    @property
    def active_displays(self):
        """
        list of id of the displays active on this device.
        it's a list bc there can be more than one display streaming
        to a device.
        """
        return list(
            display.id for display in self._displays_objs if display.active
        )

    @cached_property
    def displays(self):
        return list(segment[0] for segment in self._segments)

    def add_segment(self, display_id, start_pixel, end_pixel):
        # make sure this segment doesn't overlap with any others
        for _display_id, segment_start, segment_end in self._segments:
            if display_id == _display_id:
                continue
            overlap = (
                min(segment_end, end_pixel)
                - max(segment_start, start_pixel)
                + 1
            )
            if overlap > 0:
                display_name = self._ledfx.displays.get(display_id).name
                blocking_display_name = self._ledfx.displays.get(
                    _display_id
                ).name
                msg = f"Failed to activate effect! '{display_name}' overlaps with active device '{blocking_display_name}'"
                _LOGGER.warning(msg)
                raise ValueError(msg)

        # if the segment is from a new device, we need to recheck our priority display
        if display_id not in (segment[0] for segment in self._segments):
            self.invalidate_cached_props()
        self._segments.append((display_id, start_pixel, end_pixel))

    def clear_display_segments(self, display_id):
        self._segments = [
            segment for segment in self._segments if segment[0] != display_id
        ]
        if display_id == self.priority_display:
            self.invalidate_cached_props()

    def clear_segments(self):
        self._segments = []

    def invalidate_cached_props(self):
        # invalidate cached properties
        for prop in ["priority_display", "_displays_objs", "displays"]:
            if hasattr(self, prop):
                delattr(self, prop)


@BaseRegistry.no_registration
class NetworkedDevice(Device):
    """
    Networked device, handles resolving IP
    """

    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Required(
                "ip_address",
                description="Hostname or IP address of the device",
            ): str,
        }
    )

    async def async_initialize(self):
        self._destination = None
        await self.resolve_address()

    async def resolve_address(self):
        try:
            self._destination = await resolve_destination(
                self._ledfx.loop, self._config["ip_address"]
            )
        except ValueError as msg:
            _LOGGER.warning(f"Device {self.name}: {msg}")

    def activate(self, *args, **kwargs):
        if self._destination is None:
            _LOGGER.warning(
                f"Device {self.name}: Cannot activate, destination {self._config['ip_address']} is not yet resolved"
            )
            async_fire_and_forget(
                self.resolve_address(), loop=self._ledfx.loop
            )
            return
        else:
            super().activate(*args, **kwargs)

    @property
    def destination(self):
        if self._destination is None:
            _LOGGER.warning(
                f"Device {self.name}: Destination {self._config['ip_address']} is not yet resolved"
            )
            async_fire_and_forget(
                self.resolve_address(), loop=self._ledfx.loop
            )
            return
        else:
            return self._destination


class Devices(RegistryLoader):
    """Thin wrapper around the device registry that manages devices"""

    PACKAGE_NAME = "ledfx.devices"

    def __init__(self, ledfx):
        super().__init__(ledfx, Device, self.PACKAGE_NAME)

        def on_shutdown(e):
            self._zeroconf.close()
            self.deactivate_devices()

        self._ledfx.events.add_listener(on_shutdown, Event.LEDFX_SHUTDOWN)
        self._zeroconf = zeroconf.Zeroconf()

    def create_from_config(self, config):
        for device in config:
            _LOGGER.info(f"Loading device from config: {device}")
            self._ledfx.devices.create(
                id=device["id"],
                type=device["type"],
                config=device["config"],
                ledfx=self._ledfx,
            )

    def deactivate_devices(self):
        for device in self.values():
            device.deactivate()

    def get_device(self, device_id):
        for device in self.values():
            if device_id == device.id:
                return device
        return None

    async def async_initialize_devices(self):
        tasks = [
            device.async_initialize()
            for device in self.values()
            if hasattr(device, "async_initialize")
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if type(result) is ValueError:
                _LOGGER.warning(result)

    async def add_new_device(self, device_type, device_config):
        """
        Creates a new device.
        """
        # First, we try to make sure this device doesn't share a destination with any existing device
        # if "ip_address" in device_config.keys():
        #     device_ip = device_config["ip_address"].rstrip(".")
        #     device_config["ip_address"] = device_ip
        #     try:
        #         resolved_dest = await resolve_destination(
        #             self._ledfx.loop, device_ip
        #         )
        #     except ValueError:
        #         _LOGGER.error(f"Failed to resolve address {device_ip}")
        #         return

        #     for existing_device in self._ledfx.devices.values():
        #         if "ip_address" in existing_device.config.keys() and (
        #             existing_device.config["ip_address"] == device_ip
        #             or existing_device.config["ip_address"] == resolved_dest
        #         ):
        #             if device_type == "e131":
        #                 # check the universes for e131, it might still be okay at a shared ip_address
        #                 # eg. for multi output controllers
        #                 if (
        #                     device_config["universe"]
        #                     == existing_device.config["universe"]
        #                 ):
        #                     msg = f"Ignoring {device_ip}: Shares IP and starting universe with existing device {existing_device.name}"
        #                     _LOGGER.info(msg)
        #                     raise ValueError(msg)
        #             else:
        #                 msg = f"Ignoring {device_ip}: Shares destination with existing device {existing_device.name}"
        #                 _LOGGER.info(msg)
        #                 raise ValueError(msg)

        # If WLED device, get all the necessary config from the device itself
        if device_type == "wled":
            resolved_dest = "127.0.0.1"
            wled = WLED(resolved_dest)
            wled_config = await wled.get_config()

            led_info = wled_config["leds"]
            wled_name = wled_config["name"]

            wled_count = led_info["count"]
            wled_rgbmode = led_info["rgbw"]

            wled_config = {
                "name": wled_name,
                "pixel_count": wled_count,
                "icon_name": "wled",
                "rgbw_led": wled_rgbmode,
            }

            # determine sync mode
            # UDP < 480
            # DDP or E131 depending on: ledfx's configured preferred mode first, else the device's mode
            # ARTNET can do one
            sync_mode = "UDP"
            if wled_count > 480:
                preferred_mode = self._ledfx.config["wled_preferences"][
                    "wled_preferred_mode"
                ]
                if preferred_mode:
                    sync_mode = preferred_mode
                else:
                    await wled.get_sync_settings()
                    sync_mode = wled.get_sync_mode()

            if sync_mode == "ARTNET":
                msg = f"Cannot add WLED device at {resolved_dest}. Unsupported mode: 'ARTNET', and too many pixels for UDP sync (>480)"
                _LOGGER.warning(msg)
                raise ValueError(msg)

            wled_config["sync_mode"] = sync_mode
            device_config |= wled_config

        device_id = generate_id(device_config["name"])

        # Create the device
        _LOGGER.info(
            "Adding device of type {} with config {}".format(
                device_type, device_config
            )
        )
        device = self._ledfx.devices.create(
            id=device_id,
            type=device_type,
            config=device_config,
            ledfx=self._ledfx,
        )

        if hasattr(device, "async_initialize"):
            await device.async_initialize()

        # Update and save the configuration
        self._ledfx.config["devices"].append(
            {
                "id": device.id,
                "type": device.type,
                "config": device.config,
            }
        )

        # Generate display configuration for the device
        _LOGGER.info(f"Creating a display for device {device.name}")
        display_id = generate_id(device.name)
        display_config = {
            "name": device.name,
            "icon_name": device_config["icon_name"],
        }
        segments = [[device.id, 0, device_config["pixel_count"] - 1, False]]

        # Create the display
        display = self._ledfx.displays.create(
            id=display_id,
            config=display_config,
            ledfx=self._ledfx,
            is_device=device.id,
        )

        # Create the device as a single segment on the display
        display.update_segments(segments)

        # Update the configuration
        self._ledfx.config["displays"].append(
            {
                "id": display.id,
                "config": display.config,
                "segments": display.segments,
                "is_device": device.id,
            }
        )

        # Finally, save the config to file!
        save_config(
            config=self._ledfx.config,
            config_dir=self._ledfx.config_dir,
        )

        return device

    async def set_wleds_sync_mode(self, mode):
        for device in self.values():
            if (
                device.type == "wled"
                and device.pixel_count > 480
                and device.config["sync_mode"] != mode
            ):
                device.wled.set_sync_mode(mode)
                await device.wled.flush_sync_settings()
                device.update_config({"sync_mode": mode})

    async def find_wled_devices(self):
        # Scan the LAN network that match WLED using zeroconf - Multicast DNS
        # Service Discovery Library
        _LOGGER.info("Scanning for WLED devices...")
        wled_listener = WLEDListener(self._ledfx)
        wledbrowser = self._zeroconf.add_service_listener(
            "_wled._tcp.local.", wled_listener
        )
        try:
            await asyncio.sleep(30)
        finally:
            _LOGGER.info("Scan Finished")
            self._zeroconf.remove_service_listener(wled_listener)


class WLEDListener(zeroconf.ServiceBrowser):
    def __init__(self, _ledfx):
        self._ledfx = _ledfx

    def remove_service(self, zeroconf_obj, type, name):
        _LOGGER.info(f"Service {name} removed")

    def add_service(self, zeroconf_obj, type, name):
        info = zeroconf_obj.get_service_info(type, name)

        if info:
            hostname = str(info.server)
            _LOGGER.info(f"Found device: {hostname}")

            device_type = "wled"
            device_config = {"ip_address": hostname}

            def handle_exception(future):
                # Ignore exceptions, these will be raised when a device is found that already exists
                exc = future.exception()

            async_fire_and_forget(
                self._ledfx.devices.add_new_device(device_type, device_config),
                loop=self._ledfx.loop,
                exc_handler=handle_exception,
            )
