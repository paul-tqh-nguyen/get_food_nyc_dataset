'#!/usr/bin/python3 -OO' # @todo enable this

'''
'''

# @todo update doc string

###########
# Imports #
###########

import os
import json
import asyncio
import pyppeteer
import bs4
import tqdm
from contextlib import asynccontextmanager
from functools import lru_cache
from shapely.geometry import Point, Polygon
from typing_extensions import Literal
from typing import Union, List, Tuple, Iterable, Callable, Awaitable, Coroutine

from misc_utilities import *

###########
# Globals #
###########

GET_FOOD_URL = 'https://dsny.maps.arcgis.com/apps/webappviewer/index.html?id=35901167a9d84fb0a2e0672d344f176f'
LAT_LONG_URL = 'https://www.google.com/maps'

# https://data.cityofnewyork.us/City-Government/Borough-Boundaries/tqmj-j8zm
BOROUGH_GEOJSON_FILE = './borough_data/Borough Boundaries.geojson'

RAW_SCRAPED_DATA_JSON_FILE = './raw_scraped_html_data.json'
OUTPUT_JSON_FILE = './scraped_data_with_geo_spatial.json'

MAX_NUMBER_OF_CONCURRENT_LAT_LONG_GATHERING_BROWSERS = 10

##########################
# Web Scraping Utilities #
##########################

EVENT_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

@asynccontextmanager
async def new_browser(*args, **kwargs) -> Generator:
    sentinel = object()
    browser = sentinel
    while browser is sentinel:
        try:
            browser: pyppeteer.browser.Browser = await pyppeteer.launch(kwargs, args=args)
        except Exception as browser_launch_error:
            pass
    try:
        yield browser
        await browser.close()
    except Exception as error:
        await browser.close()
        raise error
    return

########################
# Pyppeteer Extensions #
########################

async def _get_elements(self: Union[pyppeteer.page.Page, pyppeteer.element_handle.ElementHandle], selector: str) -> List[pyppeteer.element_handle.ElementHandle]:
    if isinstance(self, pyppeteer.page.Page):
        await self.waitForSelector(selector)
    elements = await self.querySelectorAll(selector)
    return elements
setattr(pyppeteer.page.Page, 'get_elements', _get_elements)
setattr(pyppeteer.element_handle.ElementHandle, 'get_elements', _get_elements)

async def _get_sole_element(self: Union[pyppeteer.page.Page, pyppeteer.element_handle.ElementHandle], selector: str) -> pyppeteer.element_handle.ElementHandle:
    return only_one(await self.get_elements(selector))
setattr(pyppeteer.page.Page, 'get_sole_element', _get_sole_element)
setattr(pyppeteer.element_handle.ElementHandle, 'get_sole_element', _get_sole_element)

async def _safelyWaitForSelector(self: pyppeteer.page.Page, *args, **kwargs) -> bool:
    try:
        await self.waitForSelector(*args, **kwargs)
        success = True
    except pyppeteer.errors.TimeoutError:
        success = False
    return success
setattr(pyppeteer.page.Page, 'safelyWaitForSelector', _safelyWaitForSelector)

async def _safelyWaitForNavigation(self: pyppeteer.page.Page, *args, **kwargs) -> bool:
    try:
        await self.waitForNavigation(*args, **kwargs)
        success = True
    except pyppeteer.errors.TimeoutError:
        success = False
    return success
setattr(pyppeteer.page.Page, 'safelyWaitForNavigation', _safelyWaitForNavigation)

###################
# Sanity Checking #
###################

def sanity_check_raw_scraped_location_dict(location_dict: dict) -> None:
    assert len(location_dict) >= 4
    assert isinstance(location_dict['raw_html_string'], str) and len(location_dict['raw_html_string']) > 0
    assert isinstance(location_dict['location_type'], str) and len(location_dict['location_type']) > 0
    assert isinstance(location_dict['location_name'], str) and len(location_dict['location_name']) > 0
    assert isinstance(location_dict['location_address'], list) and len(location_dict['location_address']) > 0 and all(isinstance(address_line, str) for address_line in location_dict['location_address'])
    assert implies('location_operating_hours' in location_dict, isinstance(location_dict.get('location_operating_hours'), list) and len(location_dict.get('location_operating_hours')) > 0)
    assert implies('location_accepts_ebt' in location_dict, isinstance(location_dict.get('location_accepts_ebt'), bool))
    assert implies('location_halal_meal_availability' in location_dict, isinstance(location_dict.get('location_halal_meal_availability'), bool))
    assert implies('location_available_programs' in location_dict, isinstance(location_dict.get('location_available_programs'), list) and len(location_dict.get('location_available_programs')) > 0 and \
                   all(isinstance(program, str) and len(program) > 0 for program in location_dict.get('location_available_programs')))
    assert implies('location_accessibility' in location_dict, isinstance(location_dict.get('location_accessibility'), str) and len(location_dict.get('location_accessibility')) > 0)
    return 

########################
# Get Food NYC Scraper #
########################

def simplify_newlines(input_string: str) -> str:
    output_string = input_string
    for _ in range(len(input_string)):
        if '\n\n' not in output_string:
            break
        output_string = output_string.replace('\n\n', '\n')
    return output_string

def process_location_html_string(raw_html_string: str) -> dict:
    html_string = raw_html_string.replace('<b>', '').replace('</b>', '')
    soup = bs4.BeautifulSoup(html_string, 'html.parser')
    location_dict = dict(location_type=only_one(soup.findAll('div', {'dojoattachpoint' : '_title'})).text, raw_html_string=raw_html_string)
    description_div = only_one(soup.findAll('div', {'dojoattachpoint' : '_description'}))
    lines = simplify_newlines(description_div.get_text(separator='\n')).split('\n')
    current_tag_into_type: Literal[None, 'name', 'address', 'available_programs', 'operating_hours', 'halal_meal_availability', 'accessibility'] = 'name'
    for line in lines:
        line = line.replace('\xa0', ' ').strip()
        if line == 'is located at':
            current_tag_into_type = 'address'
        elif line == 'Operating hours are':
            current_tag_into_type = 'operating_hours'
        elif line == 'Halal':
            current_tag_into_type = 'halal_meal_availability'
        elif line == 'This site is':
            current_tag_into_type = 'accessibility'
        elif line in ('.', '', 'which has  programs.', 'To ensure every New York City resident can access nutritious meals, the Department of Education meal hub sites provide three meals a day, Monday through Friday, to both youth and adults in need. There is no registration or identification required.'):
            pass
        elif line.startswith('which has '):
            assert line.endswith(' programs.')
            programs_string = line.replace('which has ', '').replace(' programs.', '').replace(' and ', ', ')
            assert len(programs_string) > 0, f'{repr(line)} not correctly parsed.'
            programs = programs_string.split(', ')
            location_dict['location_available_programs'] = programs
            current_tag_into_type = None
        elif current_tag_into_type == 'name':
            location_dict['location_name'] = line
            current_tag_into_type = None
        elif current_tag_into_type == 'address':
            address = location_dict.get('location_address', [])
            address.append(line)
            location_dict['location_address'] = address
        elif current_tag_into_type == 'operating_hours':
            operating_hours_string = location_dict.get('location_operating_hours', [])
            location_dict['location_operating_hours'] = operating_hours_string
            location_dict['location_operating_hours'].append(line)
        elif current_tag_into_type == 'halal_meal_availability':
            assert line == 'meals available at this location.'
            location_dict['location_halal_meal_availability'] = True
            current_tag_into_type = None
        elif current_tag_into_type == 'accessibility':
            location_dict['location_accessibility'] = line
            current_tag_into_type = None
        else:
            raise ValueError(f'Unhandled html string (at {repr(line)}):\n{html_string}')
    ebt_string = ''.join(location_dict.get('location_operating_hours', []))
    if 'accepts EBT' in ebt_string:
        location_dict['location_accepts_ebt'] = True
    elif 'does not accept EBT' in ebt_string:
        location_dict['location_accepts_ebt'] = False
    else:
        assert 'ebt' not in ebt_string.lower(), ebt_string
    return location_dict

async def scrape_location_dicts() -> List[dict]:
    async with new_browser('--start-fullscreen', headless=False, defaultViewport=None) as browser:
        page = only_one(await browser.pages())
        location_dicts: List[str] = []
        await page.goto(GET_FOOD_URL)
        home_button = await page.get_sole_element('div.home')
        await home_button.click() # ensure consistent zoom level
        circles = await page.get_elements('div#map_gc circle')
        circles = circles
        await circles[-1].click() # activate ERSI popup
        window_width, window_height = await page.evaluate('() => [window.innerWidth, window.innerHeight]')
        big_radius = window_width + window_height
        display_div = await page.get_sole_element('.esriPopupWrapper')
        for circle_index, circle in enumerate(circles):
            await page.evaluate(f'(element) => {{element.setAttribute("r", "{big_radius}px")}}', circle) # avoid obfuscated and overlapping circles by expanding the desired circle
            await home_button.click()
            await page.mouse.click(2 if bool(circle_index%2) else window_width - 5, window_height//2) # avoid double clicking while pinging at sub-double-click speed
            display_div_html_string = await page.evaluate('(element) => element.innerHTML', display_div)
            location_dict = process_location_html_string(display_div_html_string)
            sanity_check_raw_scraped_location_dict(location_dict)
            location_dicts.append(location_dict)
            await page.evaluate('(element) => {{element.setAttribute("r", "0px")}}',  circle) # hide processed circle to avoid obfuscation and overlap
        assert len(location_dicts) == len(circles)
    return location_dicts

@lru_cache(maxsize=1)
def get_borough_to_polygons() -> dict:
    with open(BOROUGH_GEOJSON_FILE, 'r') as f_borough:
        borough_geojson = json.loads(f_borough.read())
    borough_to_polygons = {}
    for feature in borough_geojson['features']:
        borough_name = feature['properties']['boro_name'].lower()
        polygon_coordinate_lists = map(lambda coordinate_list: coordinate_list[0], feature['geometry']['coordinates'])
        polygons = eager_map(Polygon, polygon_coordinate_lists)
        borough_to_polygons[borough_name] = polygons
    return borough_to_polygons

def nearest_borough_to_coordinates(latitude: float, longitude: float) -> str:
    point = Point(longitude, latitude)
    nearest_borough = None
    nearest_borough_dist = float('inf')
    borough_to_polygons = get_borough_to_polygons()
    for borough, polygons in borough_to_polygons.items():
        for polygon in polygons:
            if point.within(polygon):
                return borough
            borough_dist = polygon.exterior.distance(point)
            if borough_dist < nearest_borough_dist:
                nearest_borough_dist = borough_dist
                nearest_borough = borough
    assert isinstance(nearest_borough, str)
    nearest_borough = nearest_borough.lower() if nearest_borough_dist < 0.01 else None
    return nearest_borough

def add_borough_data(location_dict: dict) -> None:
    nearest_borough = nearest_borough_to_coordinates(location_dict['location_latitude'], location_dict['location_longitude'])
    if nearest_borough is not None:
        location_dict['location_borough'] = nearest_borough
    else:
        del location_dict['location_latitude']
        del location_dict['location_longitude']
    return

def coordinates_from_url(url: str) -> Tuple[float, float]:
    data_string = url.split('/')[-1]
    assert data_string.startswith('data=!')
    data_segments = data_string.split('!')[1:]
    assert all(data_segment[0].isnumeric() and data_segment[1].isalpha() for data_segment in data_segments)
    coordinate_dict = {data_segment[:2]: float(data_segment[2:]) for data_segment in data_segments if data_segment[:2] in ('3d', '4d')}
    latitute = coordinate_dict['3d']
    longitude = coordinate_dict['4d']
    return latitute, longitude

async def scrape_geospatial_data(location_dict: dict) -> dict:
    result_found = False
    async with new_browser(headless=True) as browser: # @todo make this headless
        page = only_one(await browser.pages())
        await page.goto(LAT_LONG_URL)
        await page.waitForSelector('#searchboxinput')
        await page.type(f'input[id=searchboxinput]', location_dict['location_address'])
        await page.keyboard.press('Enter')
        await page.safelyWaitForNavigation({'timeout': 30_000}), f'Unhandled url {page.url}'
        result_found = await page.safelyWaitForSelector('div.section-hero-header-title-top-container', {'timeout': 30_000})
        if result_found:
            url = page.url
            if not url.split('/')[-1].startswith('data=!'):
                await page.safelyWaitForNavigation({'timeout': 30_000})
                url = page.url
                assert url.split('/')[-1].startswith('data=!'), f'Unhandled url {url}'
            if '!3d' not in url.split('/')[-1]:
                await page.safelyWaitForNavigation({'timeout': 30_000})
                url = page.url
                assert '!3d' in url.split('/')[-1], f'Unhandled url {url}'
            if '!4d' not in url.split('/')[-1]:
                await page.safelyWaitForNavigation({'timeout': 30_000})
                url = page.url
                assert '!4d' in url.split('/')[-1], f'Unhandled url {url}'
    if result_found:
        location_dict['location_latitude'], location_dict['location_longitude'] = coordinates_from_url(url)
        assert 'location_borough' not in location_dict
        add_borough_data(location_dict)
    assert iff('location_borough' in location_dict, 'location_latitude' in location_dict and 'location_longitude' in location_dict)
    return location_dict

async def gather_location_dicts() -> List[dict]:
    if os.path.isfile(RAW_SCRAPED_DATA_JSON_FILE):
        with open(RAW_SCRAPED_DATA_JSON_FILE, 'r') as json_file_handle:
            location_dicts = json.load(json_file_handle)
    else:
        location_dicts = await scrape_location_dicts()
        with open(RAW_SCRAPED_DATA_JSON_FILE, 'w') as json_file_handle:
            json.dump(location_dicts, json_file_handle, indent=4)
    semaphore = asyncio.Semaphore(MAX_NUMBER_OF_CONCURRENT_LAT_LONG_GATHERING_BROWSERS)
    async def semaphore_task(task: Awaitable):
        async with semaphore:
            return await task
    location_dicts = [await coroutine for coroutine in tqdm.tqdm(asyncio.as_completed(eager_map(semaphore_task, map(scrape_geospatial_data, location_dicts))), total=len(location_dicts), bar_format='{l_bar}{bar:50}{r_bar}')]
    return location_dicts

##########
# Driver #
##########

def gather_data() -> None:
    with timer('Data gathering'):
        location_dicts = EVENT_LOOP.run_until_complete(gather_location_dicts())
    with open(OUTPUT_JSON_FILE, 'w') as json_file_handle:
        json.dump(location_dicts, json_file_handle, indent=4)
    return

if __name__ == '__main__':
    gather_data()
