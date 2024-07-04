from typing import TYPE_CHECKING, Callable

from bs4 import BeautifulSoup, Tag

from bs4_tools import markdown_from_tag, str_from_tag

if TYPE_CHECKING:
    from locations_container import Location


async def get_title(
    soup: BeautifulSoup,
    convert_tag: Callable,
    **convert_tag_kwargs,
) -> str:
    return convert_tag(soup.find("h1"), **convert_tag_kwargs)


async def get_summary(
    soup: BeautifulSoup,
    convert_tag: Callable,
    **convert_tag_kwargs,
) -> str:
    content = soup.find("div", id="mw-content-text")
    if not isinstance(content, Tag):
        raise Exception("Expected Tag object.")
    tags = [
        tag
        for tag in content.find_all(["p", "h2", "h3"])
        if not any(parent.name == "table" for parent in tag.parents)
    ]
    text = ""
    for tag in tags:
        if tag.name != "p":
            break
        tag_text = convert_tag(tag, **convert_tag_kwargs)
        if not tag_text:
            continue
        text += f"{tag_text}\n\n"

    return text.rstrip()


async def get_content(
    soup: BeautifulSoup,
    convert_tag: Callable,
    **convert_tag_kwargs,
) -> str:
    content = soup.find("div", id="mw-content-text")
    if not isinstance(content, Tag):
        raise Exception("Expected Tag object.")
    tags = content.find_all(["p", "h2", "h3", "ul", "ol"])

    text = ""
    for tag in tags:
        tag_text = convert_tag(tag, **convert_tag_kwargs)
        if not tag_text or any(parent.name == "table" for parent in tag.parents):
            continue
        if any(
            phrase in tag_text.lower()
            for phrase in ["see also", "notes", "references", "external links"]
        ):
            # Parse only main content
            break
        if tag.name == "p":
            text += f"{tag_text}\n\n"
        elif tag.name in ["ul", "ol", "menu"]:
            text = f"{text.rstrip()}\n{tag_text}\n\n"
        else:
            text += f"{tag_text}\n"

    return text.rstrip()


async def return_markdown_reply_chunks(
    location: "Location",
    is_summary: bool = True,
    continue_location: str = "",
) -> list[str | bytes]:
    soup = location.soup
    image = location.image
    if soup is None or image is None:
        raise Exception(f"Soup properties of {location} have not been retrieved")
    title = await get_title(
        soup,
        markdown_from_tag,
        url=location.link,
        url_domain="https://en.wikipedia.org",
    )

    if is_summary:
        text = await get_summary(
            soup,
            markdown_from_tag,
            url=location.link,
            url_domain="https://en.wikipedia.org",
        )
    else:
        text = await get_content(
            soup,
            markdown_from_tag,
            url=location.link,
            url_domain="https://en.wikipedia.org",
        )

    reply_chunks = (
        [title]
        + [image]
        + [chunk if chunk else "_ _" for chunk in into_chunks(text, 2000)]
    )
    if continue_location:
        reply_chunks += [
            "_ _",
            f"Type /continue for information on {continue_location}, another location in your message.",
        ]

    return reply_chunks


async def return_reply_chunks(
    location: "Location", is_summary: bool = True, continue_location: str = ""
) -> list[str]:
    soup = location.soup
    if soup is None:
        raise Exception(f"Soup properties of {location} have not been retrieved")

    title = await get_title(soup, str_from_tag)
    if is_summary:
        text = await get_summary(soup, str_from_tag)
    else:
        text = await get_content(soup, str_from_tag)
    reply_chunks = [title] + [
        chunk if chunk else "_ _" for chunk in into_chunks(text, 2000)
    ]
    if continue_location:
        reply_chunks += [
            "_ _",
            f"Type /continue for information on {continue_location}, another location in your message.",
        ]

    return reply_chunks


def find_last(initial_string: str, substr: str) -> int:
    return len(initial_string) - initial_string[::-1].find(substr[::-1]) - len(substr)


def into_chunks(initial_string: str, max_length: int) -> list:
    """
    Separate a string into chunks based on the full stop.
    """
    chunks = initial_string.split("\n")
    for i, chunk in enumerate(chunks.copy()):
        if len(chunk) > max_length:
            sub_chunks = []
            start_index = 0
            while start_index < len(chunk) - 1:
                max_sub_chunk = chunk[start_index : start_index + max_length]
                if ". " not in max_sub_chunk + " ":
                    sub_chunks.append(max_sub_chunk)
                    start_index += max_length
                else:
                    length = find_last(max_sub_chunk + " ", ". ") + 2
                    sub_chunks.append(chunk[start_index : start_index + length])
                    start_index += length
            chunks[i : i + len(sub_chunks)] = sub_chunks

    return chunks
