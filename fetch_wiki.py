import logging

from aiohttp import ClientSession
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


async def fetch_soup(link: str, session: ClientSession) -> BeautifulSoup:
    logger.info(f"Started fetching soup: {link}.")
    async with session.get(link) as response:
        soup = BeautifulSoup(await response.text(), "html.parser")
    logger.info(f"Finished fetching soup {link}.")

    return soup


async def fetch_image(soup: BeautifulSoup, session: ClientSession) -> bytes:
    infobox = soup.find("table", class_="infobox")
    if infobox is None:
        raise Exception("No infobox table was found.")
    img_tag = infobox.find("img")
    if not isinstance(img_tag, Tag):
        raise Exception("No image found.")

    if not isinstance(src := img_tag["src"], str):
        raise Exception("Image has no source.")
    url = "https:" + src
    async with session.get(url) as resp:
        if resp.status != 200:
            logger.info("Could not download file.")
            raise Exception("Could not download file.")
        else:
            return await resp.read()
