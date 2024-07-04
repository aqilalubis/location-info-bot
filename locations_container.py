import asyncio
import logging
import random
import re
from collections.abc import Iterable
from copy import deepcopy

from aiohttp import ClientSession
from bs4 import BeautifulSoup, Tag
from unidecode import unidecode

from bs4_tools import str_from_tag
from create_reply import return_markdown_reply_chunks, return_reply_chunks
from fetch_wiki import fetch_image, fetch_soup

logger = logging.getLogger(__name__)


class Location:
    def __init__(self, link: str, key: str = "", **kwargs) -> None:
        self.key = key
        self.link = link
        self.extra_info = {**kwargs}

        self.soup: None | BeautifulSoup = None
        self.name: None | str = None
        self.image: None | bytes = None

    @classmethod
    def from_dict(cls, loc_dict: dict) -> "Location":
        return cls(loc_dict.pop("link"), loc_dict.pop("key"), **loc_dict)

    def __repr__(self) -> str:
        return f'Location("{self.link}")'

    def __eq__(self, value: "Location") -> bool:
        return self.link == value.link and self.__dict__ == value.__dict__

    async def get_soup_properties(self, session: ClientSession) -> None:
        if self.soup is None:
            self.soup = await fetch_soup(self.link, session)
        if self.name is None:
            if isinstance(tag := self.soup.find("h1"), Tag):
                self.name = str_from_tag(tag)
            else:
                raise Exception("Couldn't get tag from heading.")
        if self.image is None:
            self.image = await fetch_image(self.soup, session)

    async def get_name(self, session: ClientSession) -> str:
        if self.soup is None:
            self.soup = await fetch_soup(self.link, session)
        if self.name is None:
            if isinstance(tag := self.soup.find("h1"), Tag):
                self.name = str_from_tag(tag)
            else:
                raise Exception("Couldn't get tag from heading.")

        return self.name

    async def get_reply_chunks(
        self,
        is_summary: bool,
        is_markdown: bool,
        continue_location: str = "",
        session: ClientSession | None = None,
    ) -> list:
        if session is not None:
            await self.get_soup_properties(session=session)
        if self.soup is None:
            raise Exception("Soup properties are undefined.")

        logger.info(f"Started parsing soup: {self}.")
        if is_markdown:
            if self.image is None:
                raise Exception("Soup properties are undefined.")
            reply_chunks = await return_markdown_reply_chunks(
                self, is_summary, continue_location
            )
        else:
            reply_chunks = await return_reply_chunks(
                self, is_summary, continue_location
            )
        logger.info(f"Finished parsing soup: {self}.")

        return reply_chunks


class LocationsContainer:
    def __init__(self, container_dict: dict | None = None) -> None:
        if container_dict is not None:
            self.container = container_dict
        else:
            self.container: dict = dict()
        self.next_id = 0

    def __getitem__(self, item: str | Location) -> Location:
        if isinstance(item, str):
            return self.container[item][0]
        else:
            for location in self.container[item.key]:
                if location.link == item.link:
                    return location
            else:
                raise KeyError

    def __setitem__(self, key: str | Location, value: Location) -> None:
        if isinstance(key, Location):
            key = key.key
        for location in self.container.get(key, []):
            if value.link == location.link:
                if value != location:
                    logger.info(f"{location} modified")
                self.container[key].remove(location)
                self.container[key].append(value)
                break
        else:
            self.container[key] = self.container.get(key, []) + [value]

    def __iter__(self) -> Iterable:
        return self.container.__iter__()

    def __len__(self) -> int:
        return len(self.container)

    def __add__(self, other: "LocationsContainer") -> "LocationsContainer":
        locations1 = deepcopy(self)
        locations2 = deepcopy(other)
        for location_list in locations2.container.values():
            for location in location_list:
                try:
                    current_location = locations1[location]
                    if len(location.extra_info) > len(current_location.extra_info):
                        locations1[location] = location
                except KeyError:
                    locations1[location] = location

        return locations1

    def __repr__(self) -> str:
        return f"LocationsContainer({len(self)} locations)"

    @classmethod
    async def from_container(cls, container: dict) -> "LocationsContainer":
        return cls(container)

    async def get_possible_locations(
        self, sentence: str, soup_properties: bool = True
    ) -> list[Location]:
        """Returns a list of locations found in the sentence."""
        possible_locations = []
        sentence = f" {unidecode(sentence).lower()} "
        for key in self.container.keys():
            regex = r"\s[\W_]*" + re.escape(key) + r"[\W_]*\s"
            if re.search(regex, sentence):
                possible_locations += self.container.get(key, [])
        if not possible_locations:
            return []

        if soup_properties:
            no_soup = [
                location
                for location in possible_locations
                if any(value is None for value in location.__dict__.values())
            ]
            if no_soup:
                async with ClientSession() as session:
                    await asyncio.gather(
                        *[
                            location.get_soup_properties(session)
                            for location in possible_locations
                        ]
                    )
                for location in no_soup:
                    logger.info(f"{location} modified")

        return possible_locations

    async def search_by_name(
        self, name: str, possible_locations: None | list[Location] = None
    ) -> Location:
        """Returns a location based on its "name" i.e. the wiki page's title."""
        # We don't get the image to save time.
        if possible_locations is None:
            possible_locations = await self.get_possible_locations(
                name, soup_properties=False
            )
        if not possible_locations:
            raise KeyError("No name found")
        no_soup = [
            location
            for location in possible_locations
            if any(
                value is None
                for key, value in location.__dict__.items()
                if key != "image"
            )
        ]
        if no_soup:
            async with ClientSession() as session:
                await asyncio.gather(
                    *[location.get_name(session) for location in possible_locations]
                )
            for location in no_soup:
                logger.info(f"{location} modified")

        for location in possible_locations:
            if location.name is None:
                raise KeyError(f"Name couldn't be found for {location}.")
            if name.lower() == location.name.lower() or len(possible_locations) == 1:
                return location
        else:
            raise KeyError("No location found.")

    async def random_location(self, soup_properties: bool = True) -> Location:
        """Returns a random location in the LocationsContainer."""
        location: Location = random.choice(
            [location for key in self.container.values() for location in key]
        )
        if soup_properties:
            if any(value is None for value in location.__dict__.values()):
                async with ClientSession() as session:
                    await location.get_soup_properties(session)
                logger.info(f"{location} modified")

        return location


def combine(*args: LocationsContainer):
    combined = args[0]
    for locations_container in args[1:]:
        combined += locations_container

    return combined
