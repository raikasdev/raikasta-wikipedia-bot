import pywikibot
from collections.abc import Sequence
import re
from pywikibot.exceptions import InvalidTitleError, SiteDefinitionError

def replace_links(text: str, replace, site: 'pywikibot.site.BaseSite') -> str:
    """Replace wikilinks selectively.

    The text is searched for a link and on each link it replaces the text
    depending on the result for that link. If the result is just None it skips
    that link. When it's False it unlinks it and just inserts the label. When
    it is a Link instance it'll use the target, section and label from that
    Link instance. If it's a Page instance it'll use just the target from the
    replacement and the section and label from the original link.

    If it's a string and the replacement was a sequence it converts it into a
    Page instance. If the replacement is done via a callable it'll use it like
    unlinking and directly replace the link with the text itself.

    If either the section or label should be used the replacement can be a
    function which returns a Link instance and copies the value which should
    remaining.

    .. versionchanged:: 7.0
       `site` parameter is mandatory

    :param text: the text in which to replace links
    :param replace: either a callable which reacts like described above.
        The callable must accept four parameters link, text, groups, rng and
        allows for user interaction. The groups are a dict containing 'title',
        'section', 'label' and 'linktrail' and the rng are the start and end
        position of the link. The 'label' in groups contains everything after
        the first pipe which might contain additional data which is used in
        File namespace for example.
        Alternatively it can be a sequence containing two items where the first
        must be a Link or Page and the second has almost the same meaning as
        the result by the callable. It'll convert that into a callable where
        the first item (the Link or Page) has to be equal to the found link and
        in that case it will apply the second value from the sequence.
    :type replace: sequence of pywikibot.Page/pywikibot.Link/str or
        callable
    :param site: a Site object to use. It should match the origin or
        target site of the text
    :raises TypeError: missing positional argument 'site'
    :raises ValueError: Wrong site type
    :raises ValueError: Wrong replacement number
    :raises ValueError: Wrong replacement types
    """
    def to_link(source):
        """Return the link from source when it's a Page otherwise itself."""
        if isinstance(source, pywikibot.Page):
            return source._link
        if isinstance(source, str):
            return pywikibot.Link(source, site)
        return source

    def replace_callable(link, text, groups, rng):
        if replace_list[0] == link:
            return replace_list[1]
        return None

    def check_classes(replacement):
        """Normalize the replacement into a list."""
        if not isinstance(replacement, (pywikibot.Page, pywikibot.Link)):
            raise ValueError('The replacement must be None, False, '
                             'a sequence, a Link or a str but '
                             'is "{}"'.format(type(replacement)))

    def title_section(link) -> str:
        title = link.title
        if link.section:
            title += '#' + link.section
        return title

    if not isinstance(site, pywikibot.site.BaseSite):
        raise ValueError('The "site" argument must be a BaseSite not {}.'
                         .format(type(site).__name__))

    if isinstance(replace, Sequence):
        if len(replace) != 2:
            raise ValueError('When used as a sequence, the "replace" '
                             'argument must contain exactly 2 items.')
        replace_list = [to_link(replace[0]), replace[1]]
        if not isinstance(replace_list[0], pywikibot.Link):
            raise ValueError(
                'The original value must be either str, Link or Page '
                'but is "{}"'.format(type(replace_list[0])))
        if replace_list[1] is not False and replace_list[1] is not None:
            if isinstance(replace_list[1], str):
                replace_list[1] = pywikibot.Page(site, replace_list[1])
            check_classes(replace_list[0])
        replace = replace_callable

    linktrail = site.linktrail()
    link_pattern = re.compile(
        r'\[\[(?P<title>.*?)(#(?P<section>.*?))?(\|(?P<label>.*?))?\]\]'
        r'(?P<linktrail>{})'.format(linktrail))
    extended_label_pattern = re.compile(fr'(.*?\]\])({linktrail})')
    linktrail = re.compile(linktrail)
    curpos = 0
    # This loop will run until we have finished the current page
    while True:
        m = link_pattern.search(text, pos=curpos)
        if not m:
            break

        m_title = m['title'].strip()

        # Ignore links to sections of the same page
        if not m_title:
            curpos = m.end()
            continue

        # Ignore interwiki links (And those who's requests fail :/)
        try:
          if site.isInterwikiLink(m_title) and not m_title.startswith(':'):
              curpos = m.end()
              continue
        except:
          print("Request error on interwiki link")
          curpos = m.end()
          continue

        groups = m.groupdict()
        if groups['label'] and '[[' in groups['label']:
            # TODO: Work on the link within the label too
            # A link within a link, extend the label to the ]] after it
            extended_match = extended_label_pattern.search(text, pos=m.end())
            if not extended_match:
                # TODO: Unclosed link label, what happens there?
                curpos = m.end()
                continue
            groups['label'] += groups['linktrail'] + extended_match[1]
            groups['linktrail'] = extended_match[2]
            end = extended_match.end()
        else:
            end = m.end()

        start = m.start()
        # Since this point the m variable shouldn't be used as it may not
        # contain all contents
        del m

        try:
            link = pywikibot.Link.create_separated(
                groups['title'], site, section=groups['section'],
                label=groups['label'])
        except (SiteDefinitionError, InvalidTitleError):
            # unrecognized iw prefix or invalid title
            curpos = end
            continue

        # Check whether the link found should be replaced.
        # Either None, False or tuple(Link, bool)
        new_link = replace(link, text, groups.copy(), (start, end))
        if new_link is None:
            curpos = end
            continue

        # The link looks like this:
        # [[page_title|new_label]]new_linktrail
        page_title = groups['title']
        new_label = groups['label']

        if not new_label:
            # or like this: [[page_title]]new_linktrail
            new_label = page_title
            # remove preleading ":" from the link text
            if new_label[0] == ':':
                new_label = new_label[1:]

        new_linktrail = groups['linktrail']
        if new_linktrail:
            new_label += new_linktrail

        if new_link is False:
            # unlink - we remove the section if there's any
            assert isinstance(new_label, str), 'link text must be str.'
            new_link = new_label

        if isinstance(new_link, str):
            text = text[:start] + new_link + text[end:]
            # Make sure that next time around we will not find this same hit.
            curpos = start + len(new_link)
            continue

        if isinstance(new_link, bytes):
            raise ValueError('The result must be str and not bytes.')

        # Verify that it's either Link, Page or str
        check_classes(new_link)
        # Use section and label if it's a Link and not otherwise
        if isinstance(new_link, pywikibot.Link):
            is_link = True
        else:
            new_link = new_link._link
            is_link = False

        new_title = new_link.canonical_title()
        # Make correct langlink if needed
        if new_link.site != site:
            new_title = ':' + new_link.site.code + ':' + new_title

        if is_link:
            # Use link's label
            new_label = new_link.anchor
            must_piped = new_label is not None
            new_section = new_link.section
        else:
            must_piped = True
            new_section = groups['section']

        if new_section:
            new_title += '#' + new_section

        if new_label is None:
            new_label = new_title

        # Parse the link text and check if it points to the same page
        parsed_new_label = pywikibot.Link(new_label, new_link.site)
        try:
            parsed_new_label.parse()
        except InvalidTitleError:
            pass
        else:
            parsed_link_title = title_section(parsed_new_label)
            new_link_title = title_section(new_link)
            # compare title, but only with parts if linktrail works
            if not linktrail.sub('',
                                 parsed_link_title[len(new_link_title):]):
                # TODO: This must also compare everything that was used as a
                #       prefix (in case insensitive)
                must_piped = (
                    not parsed_link_title.startswith(new_link_title)
                    or parsed_new_label.namespace != new_link.namespace)

        if must_piped:
            new_text = f'[[{new_title}|{new_label}]]'
        else:
            new_text = (f'[[{new_label[:len(new_title)]}]]'
                        f'{new_label[len(new_title):]}')

        text = text[:start] + new_text + text[end:]
        # Make sure that next time around we will not find this same hit.
        curpos = start + len(new_text)
    return text
