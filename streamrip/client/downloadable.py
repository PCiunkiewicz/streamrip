import asyncio
import functools
import hashlib
import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import aiofiles
import aiohttp
import requests
from Cryptodome.Cipher import Blowfish

from streamrip.exceptions import NonStreamableError

logger = logging.getLogger("streamrip")


BLOWFISH_SECRET = "g4el58wc0zvf9na1"


def generate_temp_path(url: str):
    return os.path.join(
        tempfile.gettempdir(),
        f"__streamrip_{hash(url)}_{time.time()}.download",
    )


async def fast_async_download(path, url, headers, callback):
    """Synchronous download with yield for every 1MB read.

    Using aiofiles/aiohttp resulted in a yield to the event loop for every 1KB,
    which made file downloads CPU-bound. This resulted in a ~10MB max total download
    speed. This fixes the issue by only yielding to the event loop for every 1MB read.
    """
    chunk_size: int = 2**17  # 131 KB
    counter = 0
    yield_every = 8  # 1 MB
    with open(path, "wb") as file:  # noqa: ASYNC230
        with requests.get(  # noqa: ASYNC210
            url,
            headers=headers,
            allow_redirects=True,
            stream=True,
        ) as resp:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                file.write(chunk)
                callback(len(chunk))
                if counter % yield_every == 0:
                    await asyncio.sleep(0)
                counter += 1


@dataclass(slots=True)
class Downloadable(ABC):
    session: aiohttp.ClientSession
    url: str
    extension: str
    source: str = "Unknown"
    _size_base: int | None = None

    async def download(self, path: str, callback: Callable[[int], Any]):
        await self._download(path, callback)

    async def size(self) -> int:
        if hasattr(self, "_size") and self._size is not None:
            return self._size

        async with self.session.head(self.url) as response:
            response.raise_for_status()
            content_length = response.headers.get("Content-Length", 0)
            self._size = int(content_length)
            return self._size

    @property
    def _size(self):
        return self._size_base

    @_size.setter
    def _size(self, v):
        self._size_base = v

    @abstractmethod
    async def _download(self, path: str, callback: Callable[[int], None]):
        raise NotImplementedError


class BasicDownloadable(Downloadable):
    """Just downloads a URL."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        extension: str,
        source: str | None = None,
    ):
        self.session = session
        self.url = url
        self.extension = extension
        self._size = None
        self.source: str = source or "Unknown"

    async def _download(self, path: str, callback):
        await fast_async_download(path, self.url, self.session.headers, callback)


class DeezerDownloadable(Downloadable):
    is_encrypted = re.compile("/m(?:obile|edia)/")

    def __init__(self, session: aiohttp.ClientSession, info: dict):
        logger.debug("Deezer info for downloadable: %s", info)
        self.session = session
        self.url = info["url"]
        self.source: str = "deezer"
        qualities_available = [
            i for i, size in enumerate(info["quality_to_size"]) if size > 0
        ]
        if len(qualities_available) == 0:
            raise NonStreamableError(
                "Missing download info. Skipping.",
            )
        max_quality_available = max(qualities_available)
        self.quality = min(info["quality"], max_quality_available)
        self._size = info["quality_to_size"][self.quality]
        if self.quality <= 1:
            self.extension = "mp3"
        else:
            self.extension = "flac"
        self.id = str(info["id"])

    async def _download(self, path: str, callback):
        async with self.session.get(self.url, allow_redirects=True) as resp:
            resp.raise_for_status()
            self._size = int(resp.headers.get("Content-Length", 0))
            if self._size < 20000 and not self.url.endswith(".jpg"):
                try:
                    info = await resp.json()
                    try:
                        # Usually happens with deezloader downloads
                        raise NonStreamableError(f"{info['error']} - {info['message']}")
                    except KeyError:
                        raise NonStreamableError(info)

                except json.JSONDecodeError:
                    raise NonStreamableError("File not found.")

            if self.is_encrypted.search(self.url) is None:
                logger.debug(f"Deezer file at {self.url} not encrypted.")
                await fast_async_download(
                    path, self.url, self.session.headers, callback
                )
            else:
                blowfish_key = self._generate_blowfish_key(self.id)
                logger.debug(
                    "Deezer file (id %s) at %s is encrypted. Decrypting with %s",
                    self.id,
                    self.url,
                    blowfish_key,
                )

                buf = bytearray()
                async for data, _ in resp.content.iter_chunks():
                    buf += data
                    callback(len(data))

                encrypt_chunk_size = 3 * 2048
                async with aiofiles.open(path, "wb") as audio:
                    buflen = len(buf)
                    for i in range(0, buflen, encrypt_chunk_size):
                        data = buf[i : min(i + encrypt_chunk_size, buflen)]
                        if len(data) >= 2048:
                            decrypted_chunk = (
                                self._decrypt_chunk(blowfish_key, data[:2048])
                                + data[2048:]
                            )
                        else:
                            decrypted_chunk = data
                        await audio.write(decrypted_chunk)

    @staticmethod
    def _decrypt_chunk(key, data):
        """Decrypt a chunk of a Deezer stream.

        :param key:
        :param data:
        """
        return Blowfish.new(
            key,
            Blowfish.MODE_CBC,
            b"\x00\x01\x02\x03\x04\x05\x06\x07",
        ).decrypt(data)

    @staticmethod
    def _generate_blowfish_key(track_id: str) -> bytes:
        """Generate the blowfish key for Deezer downloads.

        :param track_id:
        :type track_id: str
        """
        md5_hash = hashlib.md5(track_id.encode()).hexdigest()
        # good luck :)
        return "".join(
            chr(functools.reduce(lambda x, y: x ^ y, map(ord, t)))
            for t in zip(md5_hash[:16], md5_hash[16:], BLOWFISH_SECRET)
        ).encode()


async def concat_audio_files(paths: list[str], out: str, ext: str, max_files_open=128):
    """Concatenate audio files using FFmpeg. Batched by max files open.

    Recurses log_{max_file_open}(len(paths)) times.
    """
    if shutil.which("ffmpeg") is None:
        raise Exception("FFmpeg must be installed.")

    # Base case
    if len(paths) == 1:
        shutil.move(paths[0], out)
        return

    it = iter(paths)
    num_batches = len(paths) // max_files_open + (
        1 if len(paths) % max_files_open != 0 else 0
    )
    tempdir = tempfile.gettempdir()
    outpaths = [
        os.path.join(
            tempdir,
            f"__streamrip_ffmpeg_{hash(paths[i * max_files_open])}.{ext}",
        )
        for i in range(num_batches)
    ]

    for p in outpaths:
        try:
            os.remove(p)  # in case of failure
        except FileNotFoundError:
            pass

    proc_futures = []
    for i in range(num_batches):
        command = (
            "ffmpeg",
            "-i",
            f"concat:{'|'.join(itertools.islice(it, max_files_open))}",
            "-acodec",
            "copy",
            "-loglevel",
            "warning",
            outpaths[i],
        )
        fut = asyncio.create_subprocess_exec(*command, stderr=asyncio.subprocess.PIPE)
        proc_futures.append(fut)

    # Create all processes concurrently
    processes = await asyncio.gather(*proc_futures)

    # wait for all of them to finish
    await asyncio.gather(*[p.communicate() for p in processes])
    for proc in processes:
        if proc.returncode != 0:
            raise Exception(
                f"FFMPEG returned with status code {proc.returncode} error: {proc.stderr} output: {proc.stdout}",
            )

    # Recurse on remaining batches
    await concat_audio_files(outpaths, out, ext)
