"""Constants for the vtherm_pellet_stove integration."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Integration identity
# ---------------------------------------------------------------------------

DOMAIN = "vtherm_pellet_stove"
NAME = "Versatile Thermostat Pellet Stove"

#: Name used to register the algorithm factory in VThermAPI.
PROP_FUNCTION_PELLET_REGULATION = "pellet_regulation"

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------

#: Unique ID of the target VTherm (absent for the global defaults entry).
CONF_TARGET_VTHERM = "target_vtherm_unique_id"

#: Key used to read the proportional function name from a VTherm config entry.
CONF_PROP_FUNCTION = "proportional_function"

# -- Hysteresis (§6.1.1) ----------------------------------------------------

#: Start heating when current_temp ≤ target − hysteresis_on (°C).
CONF_HYSTERESIS_ON = "hysteresis_on"

#: Stop heating when current_temp ≥ target + hysteresis_off (°C).
CONF_HYSTERESIS_OFF = "hysteresis_off"

#: on_percent value sent to the cycle scheduler when the algorithm requests OFF.
CONF_MIN_ON_PERCENT = "min_on_percent"

#: on_percent value sent to the cycle scheduler when the algorithm requests ON.
CONF_MAX_ON_PERCENT = "max_on_percent"

# -- Pellet guard-rails (§6.1.2) --------------------------------------------

#: Minimum burn duration before an OFF is allowed (minutes).
CONF_MIN_ON_DURATION_MIN = "min_on_duration_min"

#: Minimum off duration before a new ignition is allowed (minutes).
CONF_MIN_OFF_DURATION_MIN = "min_off_duration_min"

#: Extra cooldown added on top of min_off_duration_min (minutes).
CONF_COOLDOWN_DURATION_MIN = "cooldown_duration_min"

#: Ambient temperature above which the stove is forced OFF (°C).
CONF_SAFETY_ROOM_TEMP = "safety_room_temp"

# -- Power level control (§6.1.3) -------------------------------------------

#: Enable/disable fan_mode / preset_mode piloting on the underlying climate.
CONF_POWER_CONTROL_ENABLED = "power_control_enabled"

#: HA climate attribute used to set power level: "fan_mode" or "preset_mode".
CONF_POWER_CONTROL_ATTRIBUTE = "power_control_attribute"

#: Ordered list of power level values (weakest → strongest).
CONF_POWER_LEVELS = "power_levels"

#: Default level index when no slope information is available.
CONF_POWER_DEFAULT_LEVEL_INDEX = "power_default_level_index"

#: Enable temporary boost (max level) after a setpoint increase.
CONF_POWER_BOOST_ENABLED = "power_boost_enabled"

#: Duration of the boost phase (minutes).
CONF_POWER_BOOST_DURATION_MIN = "power_boost_duration_min"

# ---------------------------------------------------------------------------
# Default option values
# ---------------------------------------------------------------------------

DEFAULT_HYSTERESIS_ON: float = 0.5
DEFAULT_HYSTERESIS_OFF: float = 0.3
DEFAULT_MIN_ON_PERCENT: float = 0.0
DEFAULT_MAX_ON_PERCENT: float = 1.0

DEFAULT_MIN_ON_DURATION_MIN: int = 30
DEFAULT_MIN_OFF_DURATION_MIN: int = 20
DEFAULT_COOLDOWN_DURATION_MIN: int = 5
DEFAULT_SAFETY_ROOM_TEMP: float = 26.0

DEFAULT_POWER_CONTROL_ENABLED: bool = True
DEFAULT_POWER_CONTROL_ATTRIBUTE: str = "fan_mode"
DEFAULT_POWER_LEVELS: list[str] = ["1", "2", "3", "4", "5"]
DEFAULT_POWER_DEFAULT_LEVEL_INDEX: int = 2
DEFAULT_POWER_BOOST_ENABLED: bool = True
DEFAULT_POWER_BOOST_DURATION_MIN: int = 15

DEFAULT_OPTIONS: dict = {
    CONF_HYSTERESIS_ON: DEFAULT_HYSTERESIS_ON,
    CONF_HYSTERESIS_OFF: DEFAULT_HYSTERESIS_OFF,
    CONF_MIN_ON_PERCENT: DEFAULT_MIN_ON_PERCENT,
    CONF_MAX_ON_PERCENT: DEFAULT_MAX_ON_PERCENT,
    CONF_MIN_ON_DURATION_MIN: DEFAULT_MIN_ON_DURATION_MIN,
    CONF_MIN_OFF_DURATION_MIN: DEFAULT_MIN_OFF_DURATION_MIN,
    CONF_COOLDOWN_DURATION_MIN: DEFAULT_COOLDOWN_DURATION_MIN,
    CONF_SAFETY_ROOM_TEMP: DEFAULT_SAFETY_ROOM_TEMP,
    CONF_POWER_CONTROL_ENABLED: DEFAULT_POWER_CONTROL_ENABLED,
    CONF_POWER_CONTROL_ATTRIBUTE: DEFAULT_POWER_CONTROL_ATTRIBUTE,
    CONF_POWER_LEVELS: DEFAULT_POWER_LEVELS,
    CONF_POWER_DEFAULT_LEVEL_INDEX: DEFAULT_POWER_DEFAULT_LEVEL_INDEX,
    CONF_POWER_BOOST_ENABLED: DEFAULT_POWER_BOOST_ENABLED,
    CONF_POWER_BOOST_DURATION_MIN: DEFAULT_POWER_BOOST_DURATION_MIN,
}

# ---------------------------------------------------------------------------
# Internal data keys
# ---------------------------------------------------------------------------

DATA_FACTORY_REGISTERED = "factory_registered"

#: Key in hass.data[DOMAIN] holding the async_add_entities callback for the sensor platform.
DATA_SENSOR_ADD_CB = "sensor_add_entities"

#: Prefix for keys in hass.data[DOMAIN] holding live PelletDebugSensor instances,
#: keyed as DATA_DEBUG_SENSORS_PREFIX + vtherm_uid. Sensors are stored here so
#: they can be reused across handler recreations instead of re-registered (which
#: would create duplicate-unique-id collisions on the sensor platform).
DATA_DEBUG_SENSORS_PREFIX = "debug_sensor_"

STORAGE_VERSION = 1
STORAGE_KEY = "vtherm_pellet_stove.{}"
