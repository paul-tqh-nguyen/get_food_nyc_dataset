# Get Food NYC Dataset

This is a quick-and-dirty web scraper that gathers the data behind [Get Food NYC](https://dsny.maps.arcgis.com/apps/webappviewer/index.html?id=35901167a9d84fb0a2e0672d344f176f).

This data has additionally been integrated with latitudinal and longitudinal geographic coordinate data scraped from [Google Maps](https://www.google.com/maps) as well as borough location data gathered from [NYC OpenData's Borough Boundaries dataset](https://data.cityofnewyork.us/City-Government/Borough-Boundaries/tqmj-j8zm).

The data can be downloaded [here](https://raw.githubusercontent.com/paul-tqh-nguyen/get_food_nyc_dataset/master/scraped_data_with_geo_spatial.json).

Feel free to  [reach out](https://paul-tqh-nguyen.github.io/about/#contact)  to report problems or make suggestions for improvement.

### Data Sources

Data was gathered from the following sources:
- [Get Food NYC](https://dsny.maps.arcgis.com/apps/webappviewer/index.html?id=35901167a9d84fb0a2e0672d344f176f)
- [Google Maps](https://www.google.com/maps)
- [NYC OpenData Borough Boundaries](https://data.cityofnewyork.us/City-Government/Borough-Boundaries/tqmj-j8zm)

### Tools Used

The following tools were utilized to gather this data:

- [Pyppeteer](https://pyppeteer.github.io/pyppeteer/)
- [asyncio](https://docs.python.org/3/library/asyncio.html)
- [Shapely](https://shapely.readthedocs.io/en/latest/manual.html)
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)

[JavaScript](https://www.javascript.com/) was also significantly utilized as a direct result of using [Pyppeteer](https://pyppeteer.github.io/pyppeteer/).

Other Python libraries used include [tqdm](https://github.com/tqdm/tqdm), [typing_extensions](https://github.com/python/typing/blob/master/typing_extensions/README.rst), [typing](https://github.com/python/typing), [contextlib](https://docs.python.org/3/library/contextlib.html), [json](https://docs.python.org/3/library/json.html), [functools](https://docs.python.org/3/library/functools.html), and [os](https://docs.python.org/3/library/os.html).