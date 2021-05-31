import numpy as np
import voluptuous as vol

from ledfx.color import COLORS
from ledfx.effects.audio import FREQUENCY_RANGES, AudioReactiveEffect
from ledfx.effects.gradient import GradientEffect
from ledfx.effects.hsv_effect import HSVEffect


class BladePowerPlus(AudioReactiveEffect, HSVEffect, GradientEffect):

    NAME = "Blade Power+"
    CATEGORY = "2.0"

    CONFIG_SCHEMA = vol.Schema(
        {
            vol.Optional(
                "mirror",
                description="Mirror the effect",
                default=False,
            ): bool,
            vol.Optional(
                "blur",
                description="Amount to blur the effect",
                default=2,
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=10)),
            vol.Optional(
                "multiplier",
                description="Make the reactive bar bigger/smaller",
                default=0.5,
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=1.0)),
            vol.Optional(
                "background_color",
                description="Color of Background",
                default="black",
            ): vol.In(list(COLORS.keys())),
            vol.Optional(
                "color", description="Color of bar", default="cyan"
            ): vol.In(list(COLORS.keys())),
            vol.Optional(
                "frequency_range",
                description="Frequency range for the beat detection",
                default="Bass (60-250Hz)",
            ): vol.In(list(FREQUENCY_RANGES.keys())),
            vol.Optional(
                "solid_color",
                description="Display a solid color bar",
                default=False,
            ): bool,
            vol.Optional(
                "invert_roll",
                description="Invert the direction of the gradient roll",
                default=False,
            ): bool,
        }
    )

    def activate(self, pixel_count):
        super().activate(pixel_count)

        #   HSV array is in vertical orientation:
        #   Pixel 1: [ H, S, V ]
        #   Pixel 2: [ H, S, V ]
        #   Pixel 3: [ H, S, V ] and so on...

        self.hsv = np.zeros((pixel_count, 3))
        self._bar = 0
        self._roll_count = 0

        rgb_gradient = self.apply_gradient(1)
        self.hsv = self.rgb_to_hsv(rgb_gradient)

        if self.config["solid_color"] is True:
            hsv_color = self.rgb_to_hsv(
                np.array(COLORS[self._config["color"]])
            )
            self.hsv[:, 0] = hsv_color[0]
            self.hsv[:, 1] = hsv_color[1]
            self.hsv[:, 2] = hsv_color[2]

    def config_updated(self, config):
        # Create the filters used for the effect
        self._bar_filter = self.create_filter(alpha_decay=0.1, alpha_rise=0.99)
        self._frequency_range = np.linspace(
            FREQUENCY_RANGES[self.config["frequency_range"]].min,
            FREQUENCY_RANGES[self.config["frequency_range"]].max,
            20,
        )

    def audio_data_updated(self, data):
        # Get frequency range power and apply filter
        self._bar = (
            np.max(data.sample_melbank(list(self._frequency_range)))
            * self.config["multiplier"]
        )
        self._bar = self._bar_filter.update(self._bar)

    def render_hsv(self):
        # Must be zeroed every cycle to clear the previous frame
        self.out = np.zeros((self.pixel_count, 3))
        bar_idx = int(self._bar * self.pixel_count)

        # Manually roll gradient because apply_gradient is only called once in activate instead of every render
        if self.config["gradient_roll"] != 0:
            # Hack to slow down roll since np.roll can only accept integers, 1 is a pretty fast minimum
            self._roll_count += (
                self.config["gradient_roll"] / 5
            )  # Roll 1/5th as fast as the config
            if self._roll_count >= 1:
                self._roll_count = 0
                if self.config["invert_roll"] is True:
                    self.hsv = np.roll(
                        self.hsv,
                        -self._config["gradient_roll"],
                        axis=0,
                    )
                else:
                    self.hsv = np.roll(
                        self.hsv,
                        self._config["gradient_roll"],
                        axis=0,
                    )

        # Construct hsv array
        self.out[:, 0] = self.hsv[:, 0]
        self.out[:, 1] = self.hsv[:, 1]
        self.out[:bar_idx, 2] = self.config["brightness"]

        self.hsv_array = self.out
