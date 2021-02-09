""" This script finds new cards and fetches their content. This should be run
    periodically as a cron job.
"""
from bs4 import BeautifulSoup
from crabber import app
from datetime import datetime
from extensions import db
from models import Card
import os
import requests
from requests.exceptions import RequestException
from typing import Optional, Tuple


class Lock:
    """ Creates a lock file until exit.
    """
    def __init__(self, name: Optional[str] = None):
        self.filename: str = f'.{name + "-" if name else ""}lock'
        self.locked = False

    def __enter__(self) -> bool:
        # Lock already in place
        if os.path.exists(self.filename):
            return self.locked

        # Create lock
        with open(self.filename, 'w') as f:
            f.write('Job started at {datetime.now().isoformat()}')
        self.locked = True
        return self.locked

    def __exit__(self, type, value, traceback):
        if self.locked:
            os.remove(self.filename)


def parse_metadata(html: str) -> Tuple[str, str, str]:
    soup = BeautifulSoup(html, 'html.parser')

    # Get title
    title = None
    # OpenGraph title
    meta_og_title = soup.find('meta', property='og:title')
    if meta_og_title:
        title = meta_og_title.get('content', None)
    # Meta tag title
    else:
        meta_title = soup.find('meta', {'name': 'title'})
        if meta_title:
            title = meta_title.get('content', None)
    title = title or soup.title.text

    # Get description
    description = None
    # OpenGraph description
    meta_og_description = soup.find('meta', property='og:description')
    if meta_og_description:
        description = meta_og_description.get('content', None)
    # Meta tag description
    else:
        meta_description = soup.find('meta', {'name': 'description'})
        if meta_description:
            description = meta_description.get('content', None)
    description = description or ''

    # Get image
    image = None
    # OpenGraph image
    meta_og_image = soup.find('meta', property='og:image')
    if meta_og_image:
        image = meta_og_image.get('content', None)
    # Scrape image
    if image is None:
        favicons = soup.select('link[class*=icon]')
        if len(favicons):
            image = favicons[0].get('href', None)
    # Fallback
    if image is None:
        image = '/static/img/avatar.jpg'

    return title, description, image


with Lock('fetch-cards') as lock:
    if lock:
        app.app_context().push()

        for card in Card.query_unready():
            try:
                r = requests.get(card.url, timeout=5)
                if r.ok:
                    metadata = parse_metadata(r.content)
                    card.title, card.description, card.image = metadata
                    card.ready = True
                    print(f'Fetched {card.url}')
            except RequestException:
                pass
            if not card.ready:
                print(f'Failed to fetch {card.url}')
                card.failed = True
        db.session.commit()
    else:
        print('Job already in process. Exiting.')