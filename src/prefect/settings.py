"""
Prefect settings management.
"""
import os
import string
import textwrap
from datetime import timedelta
from pathlib import Path
from typing import Callable, Dict, Generic, List, Optional, Type, TypeVar

import pydantic
import toml
from pydantic import BaseSettings, Field, create_model, root_validator

T = TypeVar("T")


class Setting(Generic[T]):
    """
    Setting definition type.
    """

    def __init__(
        self,
        type: Type[T],
        *,
        value_callback: Callable[["Settings", T], T] = None,
        **kwargs,
    ) -> None:
        self.field: pydantic.fields.FieldInfo = Field(**kwargs)
        self.type = type
        self.value_callback = value_callback
        self.name = None  # Will be populated after all settings are defined

        self.__doc__ = self.field.description

    def value(self) -> T:
        """
        Get the current value of a setting.

        Example:
        ```python
        from prefect.settings import PREFECT_API_URL
        PREFECT_API_URL.value()
        ```
        """
        return self.value_from(get_current_settings())

    def value_from(self, settings: "Settings") -> T:
        """
        Get the value of a setting from a settings object

        Example:
        ```python
        from prefect.settings import get_default_settings
        PREFECT_API_URL.value_from(get_default_settings())
        ```
        """
        return settings.value_of(self)

    def __repr__(self) -> str:
        return f"Setting({self.type.__name__}, {self.field!r})"


# Callbacks and validators


def get_extra_loggers(_: "Settings", value: str) -> List[str]:
    """
    `value_callback` for `PREFECT_LOGGING_EXTRA_LOGGERS`that parses the CSV string into a
    list and trims whitespace from logger names.
    """
    return [name.strip() for name in value.split(",")] if value else []


def debug_mode_log_level(settings, value):
    """
    `value_callback` for `PREFECT_LOGGING_LEVEL` that overrides the log level to DEBUG
    when debug mode is enabled.
    """
    if PREFECT_DEBUG_MODE.value_from(settings):
        return "DEBUG"
    else:
        return value


def template_with_settings(*upstream_settings: Setting) -> Callable[["Settings", T], T]:
    """
    Returns a `value_callback` that will template the given settings into the runtime
    value for the setting.
    """

    def templater(settings, value):
        original_type = type(value)
        template_values = {
            setting.name: setting.value_from(settings) for setting in upstream_settings
        }
        template = string.Template(str(value))
        return original_type(template.substitute(template_values))

    return templater


def max_log_size_smaller_than_batch_size(values):
    """
    Validator for settings asserting the batch size and match log size are compatible
    """
    if (
        values["PREFECT_LOGGING_ORION_BATCH_SIZE"]
        < values["PREFECT_LOGGING_ORION_MAX_LOG_SIZE"]
    ):
        raise ValueError(
            "`PREFECT_LOGGING_ORION_MAX_LOG_SIZE` cannot be larger than `PREFECT_LOGGING_ORION_BATCH_SIZE`"
        )
    return values


# Setting definitions


PREFECT_HOME = Setting(
    Path,
    default=Path("~/.prefect").expanduser(),
    description="""Prefect's home directory. Defaults to `~/.prefect`. This
        directory may be created automatically when required.""",
)

PREFECT_DEBUG_MODE = Setting(
    bool,
    default=False,
    description="""If `True`, places the API in debug mode. This may modify
        behavior to facilitate debugging, including extra logs and other verbose
        assistance. Defaults to `False`.""",
)

PREFECT_TEST_MODE = Setting(
    bool,
    default=False,
    description="""If `True`, places the API in test mode. This may modify
        behavior to faciliate testing. Defaults to `False`.""",
)

PREFECT_API_URL = Setting(
    str,
    default=None,
    description="""If provided, the url of an externally-hosted Orion API.
    Defaults to `None`.""",
)

PREFECT_API_KEY = Setting(
    str,
    default=None,
    description="""API key used to authenticate against Orion API.
    Defaults to `None`.""",
)

PREFECT_PROFILES_PATH = Setting(
    Path,
    default=Path("${PREFECT_HOME}/profiles.toml"),
    description="""The path to a profiles configuration files.""",
    value_callback=template_with_settings(PREFECT_HOME),
)

PREFECT_LOGGING_LEVEL = Setting(
    str,
    default="INFO",
    description="""The default logging level for Prefect loggers. Defaults to 
    "INFO" during normal operation. Is forced to "DEBUG" during debug mode.""",
    value_callback=debug_mode_log_level,
)

PREFECT_LOGGING_SERVER_LEVEL = Setting(
    str,
    default="WARNING",
    description="""The default logging level for the Orion API.""",
)

PREFECT_LOGGING_SETTINGS_PATH = Setting(
    Path,
    default=Path("${PREFECT_HOME}/logging.yml"),
    description=f"""The path to a custom YAML logging configuration file. If
    no file is found, the default `logging.yml` is used. Defaults to a logging.yml in the Prefect home directory.""",
    value_callback=template_with_settings(PREFECT_HOME),
)

PREFECT_LOGGING_EXTRA_LOGGERS = Setting(
    str,
    default="",
    description="""Additional loggers to attach to Prefect logging at runtime.
    Values should be comma separated. The handlers attached to the 'prefect' logger
    will be added to these loggers. Additionally, if the level is not set, it will
    be set to the same level as the 'prefect' logger.
    """,
    value_callback=get_extra_loggers,
)

PREFECT_LOGGING_ORION_ENABLED = Setting(
    bool,
    default=True,
    description="""Should logs be sent to Orion? If False, logs sent to the
    OrionHandler will not be sent to the API.""",
)

PREFECT_LOGGING_ORION_BATCH_INTERVAL = Setting(
    float,
    default=2.0,
    description="""The number of seconds between batched writes of logs to Orion.""",
)

PREFECT_LOGGING_ORION_BATCH_SIZE = Setting(
    int,
    default=4_000_000,
    description="""The maximum size in bytes for a batch of logs.""",
)

PREFECT_LOGGING_ORION_MAX_LOG_SIZE = Setting(
    int,
    default=1_000_000,
    description="""The maximum size in bytes for a single log.""",
)

PREFECT_AGENT_QUERY_INTERVAL = Setting(
    float,
    default=5,
    description="""The agent loop interval, in seconds. Agents will check
    for new runs this often. Defaults to `5`.""",
)

PREFECT_AGENT_PREFETCH_SECONDS = Setting(
    int,
    default=10,
    description="""Agents will look for scheduled runs this many seconds in
    the future and attempt to run them. This accounts for any additional
    infrastructure spin-up time or latency in preparing a flow run. Note
    flow runs will not start before their scheduled time, even if they are
    prefetched. Defaults to `10`.""",
)

PREFECT_ORION_DATA_NAME = Setting(
    str,
    default="default",
    description="""The name for the default data directory. Defaults to
    `default`.""",
)

PREFECT_ORION_DATA_SCHEME = Setting(
    str,
    default="file",
    description="""The scheme for the default data directory. Defaults to
    `file`.""",
)
PREFECT_ORION_DATA_BASE_PATH = Setting(
    str,
    default="/tmp",
    description="""The base path for the default data directory. Defaults to
    `/tmp`.""",
)

PREFECT_ORION_DATABASE_CONNECTION_URL = Setting(
    str,
    default="sqlite+aiosqlite:////${PREFECT_HOME}/orion.db",
    description=textwrap.dedent(
        f"""
        A database connection URL in a SQLAlchemy-compatible
        format. Orion currently supports SQLite and Postgres. Note that all
        Orion engines must use an async driver - for SQLite, use
        `sqlite+aiosqlite` and for Postgres use `postgresql+asyncpg`.

        SQLite in-memory databases can be used by providing the url
        `sqlite+aiosqlite:///file::memory:?cache=shared&uri=true&check_same_thread=false`,
        which will allow the database to be accessed by multiple threads. Note
        that in-memory databases can not be accessed from multiple processes and
        should only be used for simple tests.

        Defaults to a sqlite database stored in the Prefect home directory.
        """
    ),
    value_callback=template_with_settings(PREFECT_HOME),
)

PREFECT_ORION_DATABASE_ECHO = Setting(
    bool,
    default=False,
    description="If `True`, SQLAlchemy will log all SQL issued to the database. Defaults to `False`.",
)

PREFECT_ORION_DATABASE_TIMEOUT = Setting(
    Optional[float],
    default=1,
    description="""A statement timeout, in seconds, applied to all database
    interactions made by the API. Defaults to `1`.""",
)

PREFECT_ORION_SERVICES_RUN_IN_APP = Setting(
    bool,
    default=False,
    description="""If `True`, Orion services are started as part of the
    webserver and run in the same event loop. Defaults to `False`.""",
)

PREFECT_ORION_SERVICES_SCHEDULER_LOOP_SECONDS = Setting(
    float,
    default=60,
    description="""The scheduler loop interval, in seconds. This determines
    how often the scheduler will attempt to schedule new flow runs, but has
    no impact on how quickly either flow runs or task runs are actually
    executed. Creating new deployments or schedules will always create new
    flow runs optimistically, without waiting for the scheduler. Defaults to
    `60`.""",
)

PREFECT_ORION_SERVICES_SCHEDULER_DEPLOYMENT_BATCH_SIZE = Setting(
    int,
    default=100,
    description="""The number of deployments the scheduler will attempt to
    schedule in a single batch. If there are more deployments than the batch
    size, the scheduler immediately attempts to schedule the next batch; it
    does not sleep for `scheduler_loop_seconds` until it has visited every
    deployment once. Defaults to `100`.""",
)

PREFECT_ORION_SERVICES_SCHEDULER_MAX_RUNS = Setting(
    int,
    default=100,
    description="""The scheduler will attempt to schedule up to this many
    auto-scheduled runs in the future. Note that runs may have fewer than
    this many scheduled runs, depending on the value of
    `scheduler_max_scheduled_time`.  Defaults to `100`.
    """,
)

PREFECT_ORION_SERVICES_SCHEDULER_MAX_SCHEDULED_TIME = Setting(
    timedelta,
    default=timedelta(days=100),
    description="""The scheduler will create new runs up to this far in the
    future. Note that this setting will take precedence over
    `scheduler_max_runs`: if a flow runs once a month and
    `scheduled_max_scheduled_time` is three months, then only three runs will be
    scheduled. Defaults to 100 days (`8640000` seconds).
    """,
)

PREFECT_ORION_SERVICES_SCHEDULER_INSERT_BATCH_SIZE = Setting(
    int,
    default=500,
    description="""The number of flow runs the scheduler will attempt to insert
    in one batch across all deployments. If the number of flow runs to
    schedule exceeds this amount, the runs will be inserted in batches of this size. Defaults to `500`.
    """,
)

PREFECT_ORION_SERVICES_LATE_RUNS_LOOP_SECONDS = Setting(
    float,
    default=5,
    description="""The late runs service will look for runs to mark as late
    this often. Defaults to `5`.""",
)

PREFECT_ORION_SERVICES_MARK_LATE_AFTER = Setting(
    timedelta,
    default=timedelta(seconds=5),
    description="""The late runs service will mark runs as late after they
    have exceeded their scheduled start time by this many seconds. Defaults
    to `5` seconds.""",
)

PREFECT_ORION_API_DEFAULT_LIMIT = Setting(
    int,
    default=200,
    description="""The default limit applied to queries that can return
    multiple objects, such as `POST /flow_runs/filter`.""",
)

PREFECT_ORION_API_HOST = Setting(
    str,
    default="127.0.0.1",
    description="""The API's host address (defaults to `127.0.0.1`).""",
)

PREFECT_ORION_API_PORT = Setting(
    int,
    default=4200,
    description="""The API's port address (defaults to `4200`).""",
)

PREFECT_ORION_UI_ENABLED = Setting(
    bool,
    default=True,
    description="""Whether or not to serve the Orion UI.""",
)


# Collect all defined settings

SETTING_VARIABLES = {
    name: val for name, val in tuple(globals().items()) if isinstance(val, Setting)
}

# Populate names in settings objects from assignments above

for name, setting in SETTING_VARIABLES.items():
    setting.name = name

# Define the pydantic model for loading from the environment / validating settings


def reduce_settings(settings):
    """
    Workaround for issues with cloudpickle when using cythonized pydantic which
    throws exceptions when attempting to pickle the class which has "compiled"
    validator methods dynamically attached to it.

    We cannot define this in the model class because the class is the type that
    contains unserializable methods.

    Note that issue is not specific to the `Settings` model or its implementation.
    Any model using some features of Pydantic (e.g. `Path` validation) with a Cython
    compiled Pydantic installation may encounter pickling issues.

    See related issue at https://github.com/cloudpipe/cloudpickle/issues/408
    """
    # TODO: Consider moving this to the cloudpickle serializer and applying it to all
    #       pydantic models
    return (
        unreduce_settings,
        (settings.json(),),
    )


def unreduce_settings(json):
    """Helper for restoring settings"""
    return Settings.parse_raw(json)


# Dynamically create a pydantic model that includes all of our settings

SettingsFieldsMixin = create_model(
    "SettingsFieldsMixin",
    # Inheriting from `BaseSettings` provides environment variable loading
    __base__=BaseSettings,
    **{
        setting.name: (setting.type, setting.field)
        for setting in SETTING_VARIABLES.values()
    },
)


# Defining a class after this that inherits the dynamic class rather than setting
# __base__ to the following class ensures that mkdocstrings properly generates
# reference documentation. It does not support module-level variables, even if they are
# an object which has __doc__ set.


class Settings(SettingsFieldsMixin):
    """
    Contains validated Prefect settings.

    Settings should be accessed using the relevant `Setting` object. For example:
    ```python
    from prefect.settings import PREFECT_HOME
    PREFECT_HOME.value()
    ```

    Accessing a setting attribute directly will ignore any `value_callback` mutations.
    This is not recommended:
    ```python
    from prefect.settings import Settings
    Settings().PREFECT_PROFILE_PATH  # PosixPath('${PREFECT_HOME}/profiles.toml')
    ```
    """

    def value_of(self, setting: Setting[T]) -> T:
        """
        Retrieve a setting's value.
        """
        value = getattr(self, setting.name)
        if setting.value_callback:
            value = setting.value_callback(self, value)
        return value

    @root_validator
    def post_root_validators(cls, values):
        """
        Add root validation functions for settings here.
        """
        # TODO: We could probably register these dynamically but this is the simpler
        #       approach for now. We can explore more interesting validation features
        #       in the future.
        values = max_log_size_smaller_than_batch_size(values)
        return values

    class Config:
        frozen = True

    __reduce__ = reduce_settings


# Functions to instantiate `Settings` instances

_DEFAULTS_CACHE: Settings = None
_FROM_ENV_CACHE: Dict[int, Settings] = {}


def get_current_settings() -> Settings:
    """
    Returns a settings object populated with values from the current profile.
    """
    from prefect.context import get_profile_context

    return get_profile_context().settings


def get_settings_from_env() -> Settings:
    """
    Returns a settings object populated with default values and overrides from
    environment variables, ignoring any values in profiles.

    Calls with the same environment return a cached object instead of reconstructing
    to avoid validation overhead.
    """
    # Since os.environ is a Dict[str, str] we can safely hash it by contents, but we
    # must be careful to avoid hashing a generator instead of a tuple
    cache_key = hash(tuple((key, value) for key, value in os.environ.items()))

    if cache_key not in _FROM_ENV_CACHE:
        _FROM_ENV_CACHE[cache_key] = Settings()

    return _FROM_ENV_CACHE[cache_key]


def get_default_settings() -> Settings:
    """
    Returns a settings object populated with default values, ignoring any overrides
    from environment variables or profiles.

    This is cached since the defaults should not change during the lifetime of the
    module.
    """
    global _DEFAULTS_CACHE

    if not _DEFAULTS_CACHE:
        old = os.environ
        try:
            os.environ = {}
            settings = get_settings_from_env()
        finally:
            os.environ = old

        _DEFAULTS_CACHE = settings

    return _DEFAULTS_CACHE


# Profile input / output

DEFAULT_PROFILES = {"default": {}}


def load_profiles() -> Dict[str, Dict[str, str]]:
    """
    Load all profiles from the profiles path.
    """
    path = PREFECT_PROFILES_PATH.value_from(get_settings_from_env())
    if not path.exists():
        profiles = DEFAULT_PROFILES
    else:
        profiles = {**DEFAULT_PROFILES, **toml.loads(path.read_text())}

    return profiles


def write_profiles(profiles: dict):
    """
    Writes all profiles to the profiles path.

    Existing data will be lost.

    Asserts that all variables are known settings names.
    """
    path = PREFECT_PROFILES_PATH.value_from(get_settings_from_env())

    for profile, variables in profiles.items():
        unknown_keys = set(variables).difference(SETTING_VARIABLES)
        if unknown_keys:
            raise ValueError(
                f"Unknown setting(s) found in profile {profile!r}: {unknown_keys}"
            )

    profiles = {**DEFAULT_PROFILES, **profiles}
    return path.write_text(toml.dumps(profiles))


def load_profile(name: str) -> Dict[str, str]:
    """
    Loads a profile from the TOML file.

    Asserts that all variables are valid string key/value pairs and that keys are valid
    setting names.
    """
    profiles = load_profiles()

    if name not in profiles:
        raise ValueError(f"Profile {name!r} not found.")

    variables = profiles[name]
    for var, value in variables.items():
        try:
            variables[var] = str(value)
        except Exception as exc:
            raise TypeError(
                f"Invalid value {value!r} for variable {var!r}: Cannot be coerced to string."
            ) from exc

    unknown_keys = set(variables).difference(SETTING_VARIABLES)
    if unknown_keys:
        raise ValueError(f"Unknown setting(s) found in profile: {unknown_keys}")

    return variables