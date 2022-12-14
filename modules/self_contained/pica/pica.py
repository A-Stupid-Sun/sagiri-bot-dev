import hmac
import json
import time
import uuid
import asyncio
import aiohttp
from yarl import URL
from pathlib import Path
from loguru import logger
from hashlib import sha256
from typing import Literal
from aiohttp import TCPConnector, ClientSession

from creart import create

from shared.models.config import GlobalConfig

BASE_PATH = Path(__file__).parent
CACHE_PATH = BASE_PATH / "cache" / "download"
global_url = URL("https://picaapi.picacomic.com/")
api_key = "C69BAF41DA5ABD1FFEDC6D2FEA56B"
uuid_s = str(uuid.uuid4()).replace("-", "")
header = {
    "api-key": "C69BAF41DA5ABD1FFEDC6D2FEA56B",
    "app-channel": "3",
    "app-version": "2.2.1.3.3.4",
    "app-uuid": "defaultUuid",
    "image-quality": "original",
    "app-platform": "android",
    "app-build-version": "45",
    "Content-Type": "application/json; charset=UTF-8",
    "User-Agent": "okhttp/3.8.1",
    "accept": "application/vnd.picacomic.com.v1+json",
    "time": 0,
    "nonce": "",
    "signature": "encrypt",
}
path_filter = ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]

config = create(GlobalConfig)
loop = create(asyncio.AbstractEventLoop)
proxy = config.proxy if config.proxy != "proxy" else ""
pica_config = config.functions.get("pica", {})
username = pica_config.get("username", None)
password = pica_config.get("password", None)
compress_password = pica_config.get("compress_password", "i_luv_sagiri")
DOWNLOAD_CACHE = pica_config.get("download_cache", True)


class Pica:
    def __init__(self, account, pwd):
        CACHE_PATH.mkdir(parents=True, exist_ok=True)
        self.init = False
        self.account = account
        self.password = pwd
        self.header = header.copy()
        self.header["nonce"] = uuid_s
        self.__SigFromNative = (
            "~d}$Q7$eIni=V)9\\RK/P.RM4;9[7|@/CA}b~OW!3?EV`:<>M7pddUBL5n|0/*Cn"
        )
        asyncio.run_coroutine_threadsafe(self.check(), loop)

    @logger.catch
    async def check(self) -> bool | None:
        try:
            await self.login()
            self.init = True
            return True
        except aiohttp.ClientConnectorError:
            logger.error("proxy???????????????????????????????????????")
        except KeyError:
            logger.error("pica ????????????????????????????????????")

    def update_signature(self, url: str | URL, method: Literal["GET", "POST"]) -> dict:
        if isinstance(url, str):
            url = URL(url)
        ts = str(int(time.time()))
        temp_header = self.header.copy()
        temp_header["time"] = ts
        temp_header["signature"] = self.encrypt(url, ts, method)
        if method == "GET":
            temp_header.pop("Content-Type")
        return temp_header

    def encrypt(self, url: URL, ts, method):
        datas = [
            global_url,
            url.path[1:],
            ts,
            uuid_s,
            method,
            "C69BAF41DA5ABD1FFEDC6D2FEA56B",
            "2.2.1.3.3.4",
            "45",
        ]
        _src = self.__ConFromNative(datas)
        _key = self.__SigFromNative
        return Pica.HashKey(_src, _key)

    @staticmethod
    def __ConFromNative(datas):
        return "".join(map(str, datas[1:6]))

    @staticmethod
    def HashKey(src, key):
        app_secret = key.encode("utf-8")  # ??????
        data = src.lower().encode("utf-8")  # ??????
        return hmac.new(app_secret, data, digestmod=sha256).hexdigest()

    async def request(
        self,
        url: str | URL,
        params: dict[str, str] | None = None,
        method: Literal["GET", "POST"] = "GET",
    ):
        temp_header = self.update_signature(url, method)
        # print(temp_header)
        data = json.dumps(params) if params else None
        # print(data)
        async with aiohttp.ClientSession(connector=TCPConnector(ssl=False)) as session:
            async with session.request(method, url=url, headers=temp_header, proxy=proxy, data=data) as resp:
                ret_data = await resp.json()
                if not resp.ok:
                    logger.warning(f"????????????json:{ret_data}")
                # print(await resp.json())
                return await resp.json()

    async def login(self):
        """????????????token"""
        url = global_url / "auth" / "sign-in"
        send = {"email": self.account, "password": self.password}
        ret = await self.request(url, send, "POST")
        self.header["authorization"] = ret["data"]["token"]

    async def categories(self):
        """??????????????????"""
        url = global_url / "categories"
        return (await self.request(url))["data"]["categories"]

    async def search(self, keyword: str):
        """???????????????"""
        url = global_url / "comics" / "advanced-search" % {"page": 1}
        # print(url)
        param = {"categories": [], "keyword": keyword, "sort": "ua"}
        return [
            {"name": comic["title"], "id": comic["_id"]}
            for q in range(1, 3)
            for comic in (await self.request(url % {"q": q}, param, "POST"))["data"]["comics"]["docs"]
            if comic["likesCount"] > 200
            and comic["pagesCount"] / comic["epsCount"] < 60
            and comic["epsCount"] < 10
        ]

    async def random(self):
        """????????????"""
        url = global_url / "comics" / "random"
        return (await self.request(url))["data"]["comics"]

    async def rank(self, tt: Literal["H24", "D7", "D30"] = "H24"):
        """?????????"""
        url = global_url / "comics" / "leaderboard" % {"ct": "VC", "tt": tt}
        return (await self.request(url))["data"]["comics"]

    async def comic_info(self, book_id: str):
        """????????????"""
        url = global_url / "comics" / book_id
        return (await self.request(url))["data"]["comic"]

    async def download_image(self, url: str, path: str | Path | None = None) -> bytes:
        async with aiohttp.ClientSession(connector=TCPConnector(ssl=False)) as session:
            return await self.download_image_session(session, url, path)

    async def download_image_session(
        self, session: ClientSession, url: str, path: str | Path | None = None
    ):
        temp_header = self.update_signature(url, "GET")
        async with session.get(url=url, headers=temp_header, proxy=proxy) as resp:
            resp.raise_for_status()
            image_bytes = await resp.read()

        if path:
            Path(path).write_bytes(image_bytes)
        return image_bytes

    async def download_comic(self, book_id: str) -> tuple[Path, str]:
        info = await self.comic_info(book_id)
        episodes = info["epsCount"]
        comic_name = f"{info['title']} - {info['author']}"
        tasks = []
        for char in path_filter:
            comic_name = comic_name.replace(char, " ")
        comic_path = CACHE_PATH / comic_name
        comic_path.mkdir(exist_ok=True)
        for episode in range(episodes):
            url = global_url / "comics" / book_id / "order" / str(episode + 1) / "pages"
            data = (await self.request(url))["data"]
            episode_title: str = data["ep"]["title"]
            episode_path = comic_path / episode_title
            episode_path.mkdir(exist_ok=True)
            for img in data["pages"]["docs"]:
                media = img["media"]
                img_url = f"{media['fileServer']}/static/{media['path']}"
                image_path: Path = episode_path / media["originalName"]
                if not image_path.exists():
                    tasks.append([img_url, image_path])
        async with aiohttp.ClientSession(
            connector=TCPConnector(ssl=False, limit=5)
        ) as session:
            tasks = [self.download_image_session(session, *t) for t in tasks]
            await asyncio.gather(*tasks)
        return comic_path, comic_name


pica = Pica(username, password)
# print(loop.run_until_complete(pica.search("SAGIRI")))
# print(loop.run_until_complete(pica.categories()))
# print(loop.run_until_complete(pica.random()))
# print(loop.run_until_complete(pica.rank()))
# print(loop.run_until_complete(pica.comic_info("5ce4d819431b5d017ddc8199")))
# loop.run_until_complete(pica.download_comic("5821a1d55f6b9a4f93ef4a6b"))
