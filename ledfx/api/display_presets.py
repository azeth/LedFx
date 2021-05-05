import logging
from json import JSONDecodeError

from aiohttp import web

from ledfx.api import RestEndpoint
from ledfx.config import save_config
from ledfx.utils import generate_id

_LOGGER = logging.getLogger(__name__)


class DisplayPresetsEndpoint(RestEndpoint):

    ENDPOINT_PATH = "/api/displays/{display_id}/presets"

    async def get(self, display_id) -> web.Response:
        """
        Get presets for active effect of a display
        """
        display = self._ledfx.displays.get(display_id)
        if display is None:
            response = {
                "status": "failed",
                "reason": f"Display with ID {display_id} not found",
            }
            return web.json_response(data=response, status=404)

        if not display.active_effect:
            response = {
                "status": "failed",
                "reason": f"Display {display_id} has no active effect",
            }
            return web.json_response(data=response, status=400)

        effect_id = display.active_effect.type

        if effect_id in self._ledfx.config["ledfx_presets"].keys():
            default = self._ledfx.config["ledfx_presets"][effect_id]
        else:
            default = {}

        if effect_id in self._ledfx.config["user_presets"].keys():
            custom = self._ledfx.config["user_presets"][effect_id]
        else:
            custom = {}

        response = {
            "status": "success",
            "display": display_id,
            "effect": effect_id,
            "default_presets": default,
            "custom_presets": custom,
        }

        return web.json_response(data=response, status=200)

    async def put(self, display_id, request) -> web.Response:
        """Set active effect of display to a preset"""
        display = self._ledfx.displays.get(display_id)
        if display is None:
            response = {
                "status": "failed",
                "reason": f"Display with ID {display_id} not found",
            }
            return web.json_response(data=response, status=404)

        try:
            data = await request.json()
        except JSONDecodeError:
            response = {
                "status": "failed",
                "reason": "JSON Decoding failed",
            }
            return web.json_response(data=response, status=400)
        category = data.get("category")
        effect_id = data.get("effect_id")
        preset_id = data.get("preset_id")

        if category is None:
            response = {
                "status": "failed",
                "reason": 'Required attribute "category" was not provided',
            }
            return web.json_response(data=response, status=400)

        if category not in ["default_presets", "custom_presets"]:
            response = {
                "status": "failed",
                "reason": f'Category {category} is not "ledfx_presets" or "user_presets"',
            }
            return web.json_response(data=response, status=400)

        if category == "default_presets":
            category = "ledfx_presets"
        else:
            category = "user_presets"

        if effect_id is None:
            response = {
                "status": "failed",
                "reason": 'Required attribute "effect_id" was not provided',
            }
            return web.json_response(data=response, status=400)

        if effect_id not in self._ledfx.config[category].keys():
            response = {
                "status": "failed",
                "reason": f"Effect {effect_id} does not exist in category {category}",
            }
            return web.json_response(data=response, status=400)

        if preset_id is None:
            response = {
                "status": "failed",
                "reason": 'Required attribute "preset_id" was not provided',
            }
            return web.json_response(data=response, status=400)

        if preset_id not in self._ledfx.config[category][effect_id].keys():
            response = {
                "status": "failed",
                "reason": "Preset {} does not exist for effect {} in category {}".format(
                    preset_id, effect_id, category
                ),
            }
            return web.json_response(data=response, status=400)

        # Create the effect and add it to the display
        effect_config = self._ledfx.config[category][effect_id][preset_id][
            "config"
        ]
        effect = self._ledfx.effects.create(
            ledfx=self._ledfx, type=effect_id, config=effect_config
        )
        try:
            display.set_effect(effect)
        except (ValueError, RuntimeError) as msg:
            response = {
                "status": "failed",
                "payload": {"type": "warning", "reason": str(msg)},
            }
            return web.json_response(data=response, status=202)

        # Update and save the configuration
        for display in self._ledfx.config["displays"]:
            if display["id"] == display_id:
                # if not ('effect' in display):
                display["effect"] = {}
                display["effect"]["type"] = effect_id
                display["effect"]["config"] = effect_config
                break
        save_config(
            config=self._ledfx.config,
            config_dir=self._ledfx.config_dir,
        )

        effect_response = {}
        effect_response["config"] = effect.config
        effect_response["name"] = effect.name
        effect_response["type"] = effect.type

        response = {"status": "success", "effect": effect_response}
        return web.json_response(data=response, status=200)

    async def post(self, display_id, request) -> web.Response:
        """save configuration of active display effect as a custom preset"""
        display = self._ledfx.displays.get(display_id)
        if display is None:
            response = {
                "status": "failed",
                "reason": f"Display with ID {display_id} not found",
            }
            return web.json_response(data=response, status=404)

        if not display.active_effect:
            response = {
                "status": "failed",
                "reason": f"Display {display_id} has no active effect",
            }
            return web.json_response(data=response, status=404)

        try:
            data = await request.json()
        except JSONDecodeError:
            response = {
                "status": "failed",
                "reason": "JSON Decoding failed",
            }
            return web.json_response(data=response, status=400)
        preset_name = data.get("name")
        if preset_name is None:
            response = {
                "status": "failed",
                "reason": 'Required attribute "preset_name" was not provided',
            }
            return web.json_response(data=response, status=400)

        preset_id = generate_id(preset_name)
        effect_id = display.active_effect.type

        # If no presets for the effect, create a dict to store them
        if effect_id not in self._ledfx.config["user_presets"].keys():
            self._ledfx.config["user_presets"][effect_id] = {}

        # Update the preset if it already exists, else create it
        self._ledfx.config["user_presets"][effect_id][preset_id] = {}
        self._ledfx.config["user_presets"][effect_id][preset_id][
            "name"
        ] = preset_name
        self._ledfx.config["user_presets"][effect_id][preset_id][
            "config"
        ] = display.active_effect.config

        save_config(
            config=self._ledfx.config,
            config_dir=self._ledfx.config_dir,
        )

        response = {
            "status": "success",
            "preset": {
                "id": preset_id,
                "name": preset_name,
                "config": display.active_effect.config,
            },
        }
        return web.json_response(data=response, status=200)

    async def delete(self, display_id) -> web.Response:
        """clear effect of a display"""
        display = self._ledfx.displays.get(display_id)
        if display is None:
            response = {
                "status": "failed",
                "reason": f"Display with ID {display_id} not found",
            }
            return web.json_response(data=response, status=404)

        # Clear the effect
        display.clear_effect()

        for display in self._ledfx.config["displays"]:
            if display["id"] == display_id:
                if "effect" in display:
                    del display["effect"]
                    break
        save_config(
            config=self._ledfx.config,
            config_dir=self._ledfx.config_dir,
        )

        response = {"status": "success", "effect": {}}
        return web.json_response(data=response, status=200)
