import logging
import re

from bs4 import NavigableString, Tag

logger = logging.getLogger(__name__)


def str_from_tag(tag: Tag, separator: str = "") -> str:
    """
    Return the text displayed by a Tag object as a string without any superscripts/references.
    """

    final_string = ""
    if tag.name in ["ul", "ol", "menu"]:
        for i, li in enumerate(tag.find_all("li")):
            if not isinstance(li, Tag):
                raise NotImplementedError
            li_text = str_from_tag(li)
            if not li_text:
                continue
            elif tag.name == "ol":
                final_string += f"{i}. {li_text}\n"
            else:
                final_string += f"- {li_text}\n"
    else:
        for string in tag.strings:
            if not isinstance(string, NavigableString):
                raise NotImplementedError(f"Expected {string} to be NavigableString.")
            elif string.parent is None:
                raise NotImplementedError(f"{string} has no parent.")
            if not string.strip("\n"):
                continue
            elif any(parent.name == "sup" for parent in string.parents):
                continue
            elif any(
                parent.name == "span"
                and parent.has_attr("class")
                and "mw-editsection" in parent["class"]
                for parent in string.parents
            ):
                continue
            if separator:
                final_string += string.strip() + separator
            else:
                final_string += string.strip("\n")

    return final_string.rstrip()


def markdown_from_tag(tag: Tag, url: str, url_domain: str) -> str:
    """
    Return the text displayed by a Tag object as markdown without any superscripts/references.
    """

    markdown = ""
    if not isinstance(tag.name, str):
        raise Exception("tag.name is undefined.")
    if tag.name in ["ul", "ol", "menu"]:
        for i, li in enumerate(tag.find_all("li")):
            li_markdown = markdown_from_tag(li, url, url_domain)
            if not li_markdown:
                continue
            elif tag.name == "ol":
                markdown += f"{i}. {li_markdown}\n"
            else:
                markdown += f"- {li_markdown}\n"
    else:
        for string in tag.strings:
            if not isinstance(string, NavigableString):
                raise NotImplementedError(f"Expected {string} to be NavigableString.")
            elif string.parent is None:
                raise NotImplementedError(f"{string} has no parent.")

            if not string.strip("\n"):
                continue
            elif any(parent.name == "sup" for parent in string.parents):
                continue
            elif any(
                parent.name == "span"
                and parent.has_attr("class")
                and "mw-editsection" in parent["class"]
                for parent in string.parents
            ):
                continue
            if string.parent.name == "a":
                href = string.parent.get("href")
                if not isinstance(href, str):
                    raise NotImplementedError("Expected href to be string.")

                if (
                    string.parent.has_attr("class")
                    and "mw-selflink" in string.parent["class"]
                ):
                    href = url
                elif href.startswith("#"):
                    href = url + href
                else:
                    href = url_domain + href

                if match := re.search(r"^\[*", string):
                    leading_brackets = match.group()
                else:
                    leading_brackets = ""
                if match := re.search(r"\[*$", string):
                    trailing_brackets = match.group()
                else:
                    trailing_brackets = ""
                link_name = re.sub(r"[\[\]]+", "", string)
                markdown += (
                    leading_brackets + f"[{link_name}](<{href}>)" + trailing_brackets
                )
            else:
                markdown += string.strip("\n")

    if tag.name.startswith("h") and len(tag.name) == 2:
        markdown = f'{"#" * int(tag.name[1])} {markdown}'

    return markdown.rstrip()
