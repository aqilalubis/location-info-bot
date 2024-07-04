import asyncio
import logging
import logging.config
import re
import time

import aiohttp
from bs4 import Tag
from unidecode import unidecode

from bs4_tools import str_from_tag
from fetch_wiki import fetch_soup
from locations_container import Location, LocationsContainer, combine

logger = logging.getLogger(__name__)


async def parse_rows(
    rows,
    headers,
    column_select=None,
    data_tag=("td",),
    extra_columns=None,
    skip_same=False,
):
    """
    Returns a LocationsContainer objet after parsing a list of row Tag objects and a
    list of header strings.
    """
    locations = LocationsContainer()
    if column_select:
        if all(isinstance(column_name, str) for column_name in column_select):
            column_select = [
                headers.index(header) for header in column_select if header in headers
            ]
        headers = [headers[i] for i in column_select]

    for row in rows:
        raw_row = row.find_all(data_tag)
        if column_select:
            raw_row = [raw_row[i] for i in column_select]
        row_data = [str_from_tag(data).strip() for data in raw_row]
        key = unidecode(
            row_data[0].lower()
        )  # The key is the ascii transliteration of the location name
        if skip_same and key in locations.container.keys():
            continue

        row_dict = dict(zip(headers, row_data))
        anchor = raw_row[0].find("a", href=re.compile(r"wiki/.*"))
        if not anchor:
            continue

        row_dict["link"] = "https://en.wikipedia.org" + anchor["href"]
        row_dict["key"] = key
        if extra_columns:
            row_dict = {**row_dict, **extra_columns}

        location = Location.from_dict(row_dict)
        if key == "santa cruz":
            pass
        try:

            if len(location.extra_info) > len(locations[location].extra_info):
                locations[key] = location
        except KeyError:
            locations[key] = location

    return locations


async def from_city_homepage(link, column_select=None):
    async with aiohttp.ClientSession() as session:
        soup = await fetch_soup(link, session)
        logger.info(f"Started parsing soup: {link}")
        anchors = soup.find_all(
            "a",
            title=re.compile(
                r"List of towns and cities with 100,000 or more inhabitants/country.*"
            ),
        )
        links = ["https://en.wikipedia.org" + anchor["href"] for anchor in anchors]
        locations = await asyncio.gather(
            *[
                from_city_wiki_tables(link, column_select=column_select)
                for link in links
            ]
        )

        logger.info(f"Finished parsing soup: {link}")

        return combine(*locations)


async def from_city_wiki_tables(link, column_select=None):
    """
    Return a cities + states/districts dictionary given a Wiki page with links to list
    of cities Wiki pages.
    """
    locations = LocationsContainer()
    async with aiohttp.ClientSession() as session:
        soup = await fetch_soup(link, session)
        logger.info(f"Started parsing soup: {link}")
        for table in soup.find_all("table", class_="wikitable"):
            rows = table.find_all("tr")
            headers = [
                str_from_tag(header, separator=" ") for header in table.find_all("th")
            ]
            country = str_from_tag(table.find_previous("h2"))
            cities = await parse_rows(
                rows[1:],
                headers,
                column_select=column_select,
                extra_columns={"Country": country},
            )
            if (
                len(headers) > 2
            ):  # Some tables contain only 2 columns without a state/district
                states = await parse_rows(
                    rows[1:], headers, column_select=[1], skip_same=True
                )
            else:
                states = LocationsContainer()
            locations += cities + states
        logger.info(f"Finished parsing soup: {link}")

    return locations


async def from_country_wiki_tables(link, column_select=None):
    """
    Return a countries dictionary given a link to a list of countries Wiki page.
    """
    async with aiohttp.ClientSession() as session:
        soup = await fetch_soup(link, session)
        logger.info(f"Started parsing soup: {link}")
        table = soup.table
        if not isinstance(table, Tag):
            raise NotImplementedError(f"Expected {table} to be Tag object.")
        rows = table.find_all("tr")
        headers = [str_from_tag(header) for header in table.find_all("th")]
        locations = await parse_rows(rows[2:], headers, column_select=column_select)
        logger.info(f"Finished parsing soup: {link}")

    return locations


async def from_continent_wiki_tables(link, column_select=None):
    """
    Return a continents dictionary given a link to a list of continents Wiki page.
    """
    async with aiohttp.ClientSession() as session:
        soup = await fetch_soup(link, session)
        logger.info(f"Started parsing soup: {link}")
        table = soup.table
        if not isinstance(table, Tag):
            raise NotImplementedError(f"Expected {table} to be Tag object.")
        rows = table.find_all("tr")
        headers = [str_from_tag(header) for header in rows[0].find_all(["th", "td"])]
        locations = await parse_rows(
            rows[2:], headers, column_select=column_select, data_tag=["th", "td"]
        )
        logger.info(f"Finished parsing soup: {link}")

    return locations


async def create_locations():
    start = time.time()
    cities_coro = from_city_homepage(
        "https://en.wikipedia.org/wiki/List_of_towns_and_cities_with_100,000_or_more_inhabitants",
    )
    countries_coro = from_country_wiki_tables(
        "https://en.wikipedia.org/wiki/List_of_countries_by_population_(United_Nations)",
        column_select=["Location", "Population (1 July 2023)", "UN Continental Region"],
    )
    continent_coro = from_continent_wiki_tables(
        "https://en.wikipedia.org/wiki/List_of_continents_and_continental_subregions_by_population",
        column_select=["Continent", "Population (2021)", "Countries (2021)"],
    )
    locations = await asyncio.gather(cities_coro, countries_coro, continent_coro)
    locations = combine(*locations)
    logger.info(f"TIME: {time.time() - start}")
    return locations


if __name__ == "__main__":
    import json

    with open("logging_config.json", "rt") as f:
        config = json.load(f)
    logging.config.dictConfig(config)

    async def main():
        all_locations = await create_locations()
        await all_locations.get_possible_locations("santa cruz")
        await all_locations.search_by_name("Santa Cruz Province, Argentina")

    asyncio.run(main())
