import asyncio
import logging
import sys
import msgpack
from typing import Callable, Any, Dict, List, Optional, Deque
from logging import Logger
from threading import Thread
from collections import deque

import nonebot
from nonebot import _driver as driver
from nonebot.log import default_filter, logger
from nonebot.utils import escape_tag, logger_wrapper
from nonebot.typing import overrides
from nonebot.config import Env, Config
from nonebot.drivers import Driver as BaseDriver
from nonebot.adapters.onebot.v12 import Bot, Message
from nonebot.adapters.onebot.v12 import Adapter as BaseAdapter
from nonebot.adapters.onebot.utils import handle_api_result


def msg_to_dict(msg: Message) -> List[Dict[str, Any]]:
    r = []
    for seg in msg:
        r.append({"type": seg.type, "data": seg.data})
    return r


class WalleDriver(BaseDriver):
    def __init__(self, env: Env, config: Config):
        super().__init__(env, config)

    @overrides(BaseDriver)
    def type(self) -> str:
        return "Walle"

    @overrides(BaseDriver)
    def logger(self) -> Logger:
        return logging.getLogger("Walle")

    @overrides(BaseDriver)
    def run(self, *args, **kwargs):
        logger.opt(colors=True).debug(
            f"<g>Loaded adapters: {escape_tag(', '.join(self._adapters))}</g>"
        )

    @overrides(BaseDriver)
    def on_startup(self, func: Callable) -> Callable:
        pass  # todo

    @overrides(BaseDriver)
    def on_shutdown(self, func: Callable) -> Callable:
        pass  # todo


class WalleAdapter(BaseAdapter):
    @classmethod
    @overrides(BaseAdapter)
    def get_name(cls) -> str:
        return "Walle"

    @overrides(BaseAdapter)
    def __init__(self, driver: BaseAdapter, **kwargs: Any):
        super().__init__(driver, **kwargs)
        self.actions: Deque[bytes] = deque()

    @overrides(BaseAdapter)
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        seq = self._result_store.get_seq()
        timeout = data.pop("timeout", self.config.api_timeout)
        if data.get("message"):
            data["message"] = msg_to_dict(data["message"])
        data["self_id"] = bot.self_id
        self.actions.append(
            msgpack.packb({"action": api, "params": data, "echo": str(seq)})
        )
        return handle_api_result(
            await self._result_store.fetch(bot.self_id, seq, timeout)
        )

    def rs_get_action(self) -> Optional[bytes]:
        if len(self.actions) <= 0:
            return None
        return self.actions.popleft()

    async def rs_push_event(self, event: bytes):
        data = msgpack.unpackb(event)
        self_id = data["self_id"]
        bot = self.bots.get(self_id)
        if not bot:
            bot = Bot(self, self_id)
            self.bot_connect(bot)
            log("INFO", f"<y>Bot {escape_tag(self_id)}</y> connected")
        event = self.json_to_event(data, self_id)
        asyncio.create_task(bot.handle_event(event))

    def rs_push_resp(self, self_id: str, resp: bytes):
        data = msgpack.unpackb(resp)
        self._result_store.add_result(self_id, data)


try:
    loop = asyncio.new_event_loop()
    t = Thread(target=loop.run_forever)
    t.start()

    log = logger_wrapper("Walle")
    env = Env()
    config = Config(_common_config=env.dict(), _env_file=f".env.{env.environment}")
    # default_filter.level = config.log_level
    default_filter.level = "DEBUG"
    logger.opt(colors=True).info(
        f"Current <y><b>Env: {escape_tag(env.environment)}</b></y>"
    )
    logger.opt(colors=True).debug(
        f"Loaded <y><b>Config</b></y>: {escape_tag(str(config.dict()))}"
    )
    driver = WalleDriver(env, config)
    driver.register_adapter(WalleAdapter)
    adapter = driver._adapters.get("Walle")
    nonebot.init()

    nonebot.load_builtin_plugin("echo")
except KeyboardInterrupt:
    sys.exit(1)
