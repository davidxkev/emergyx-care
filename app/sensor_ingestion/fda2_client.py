from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aioesphomeapi import APIClient


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class SensorStateUpdate:
    key: int
    name: str
    value: Any


class FDA2SensorClient:
    def __init__(self, *, host: str, port: int, password: str | None = None) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.client = APIClient(host, port, password)
        self._entity_names: dict[int, str] = {}

    async def _maybe_await(self, result: Any) -> Any:
        if inspect.isawaitable(result):
            return await result
        return result

    async def listen(
        self,
        on_update: Callable[[SensorStateUpdate], Awaitable[None] | None],
    ) -> None:
        stop_event = asyncio.Event()
        stop_expected = True

        async def on_stop(expected: bool) -> None:
            nonlocal stop_expected
            stop_expected = expected
            if expected:
                LOGGER.info("Sensor client stopped cleanly")
            else:
                LOGGER.warning("Sensor client disconnected unexpectedly")
            stop_event.set()

        try:
            await self._maybe_await(self.client.connect(on_stop=on_stop, login=True))
        except TypeError:
            await self._maybe_await(self.client.connect(on_stop=on_stop))
        device_info = await self._maybe_await(self.client.device_info())
        device_name = getattr(device_info, "name", self.host)
        LOGGER.info("Connected to %s", device_name)

        entities_services = await self._maybe_await(self.client.list_entities_services())
        if isinstance(entities_services, tuple):
            entity_infos = entities_services[0]
        elif hasattr(entities_services, "entities"):
            entity_infos = entities_services.entities
        else:
            entity_infos = entities_services
        for entity in entity_infos:
            key = getattr(entity, "key", None)
            if key is None:
                continue
            name = getattr(entity, "name", None) or getattr(entity, "object_id", f"entity_{key}")
            self._entity_names[key] = name

        loop = asyncio.get_running_loop()

        async def dispatch_state(state: Any) -> None:
            key = getattr(state, "key", None)
            value = getattr(state, "state", None)
            if key is None:
                return
            update = SensorStateUpdate(
                key=key,
                name=self._entity_names.get(key, f"entity_{key}"),
                value=value,
            )
            result = on_update(update)
            if inspect.isawaitable(result):
                await result

        def state_callback(state: Any) -> None:
            loop.create_task(dispatch_state(state))

        self.client.subscribe_states(state_callback)
        try:
            await stop_event.wait()
        finally:
            await self._maybe_await(self.client.disconnect())

        if not stop_expected:
            raise ConnectionError(f"Sensor connection to {device_name} was reset")
