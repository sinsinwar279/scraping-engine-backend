from fastapi import FastAPI
from fastapi.responses import JSONResponse
import requests
from bs4 import BeautifulSoup
import time
import re
import logging
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Delay, max call limit, and headers used in requests
delay = [0, 1, 2, 4]
maxCallLimit = 3
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    'X-Requested-With': 'XMLHttpRequest',
    'X-APP-NAME': 'Minoan'
}

from pydantic import BaseModel
from typing import List


class UrlData(BaseModel):
    url: str
    id: int


class ScrapRequest(BaseModel):
    urls: List[UrlData]


# Define Pydantic models for request data validation
class TrackingDetailsRequest(BaseModel):
    domain: str
    order_id: str
    zip_code: str


@app.post('/getTrackingDetailsWSI')
def get_tracking_details_wsi_function(request: TrackingDetailsRequest):
    logger.info(request.dict())

    if not request.domain or not request.order_id or not request.zip_code:
        return JSONResponse(status_code=400, content={"error": "Bad Request", "message": "missing parameters"})

    url = f"https://www.{request.domain}.com/customer-service/order-status/v1/order-details/index.json?orderNumber={request.order_id}&postalCode={request.zip_code}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        logger.info(data)
        return JSONResponse(content=data)

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return JSONResponse(status_code=response.status_code,
                            content={"error": "HTTP error occurred", "message": str(http_err)})

    except requests.exceptions.ConnectionError as conn_err:
        return JSONResponse(status_code=503, content={"error": "Connection error occurred", "message": str(conn_err)})

    except requests.exceptions.Timeout as timeout_err:
        return JSONResponse(status_code=504, content={"error": "Timeout error occurred", "message": str(timeout_err)})

    except requests.exceptions.RequestException as req_err:
        return JSONResponse(status_code=500, content={"error": "An error occurred", "message": str(req_err)})


@app.post('/scrap')
def get_response_function(req: ScrapRequest):
    logger.info(f"start {req}")
    url_list = req.urls
    before = time.time()
    results = get_response(url_list[0].url)  # Access the 'url' field from the first item
    after = time.time()

    logger.info("Total time: %s seconds", after - before)

    return [results]


def get_response(url):
    data = {
        'title': '',
        'images': [],
        'description': '',
        'url': url,
        'brand_name': ''
    }

    data["url"] = sanitize_url(data["url"])
    fetch_data(data)

    filter_images(data)
    data['title'] = title_case_product_title(data["title"])

    return {
        'url': data["url"],
        'response': data
    }


def title_case_product_title(sentence):
    # Split the sentence into individual words
    if not sentence:
        return ""
    words = sentence.split()
    # Capitalize each word
    capitalized_words = [capitalize_first_letter(word) for word in words]
    # Join the words back into a sentence
    return ' '.join(capitalized_words)


def capitalize_first_letter(word):
    # Capitalize the first letter and make all other letters lowercase
    return word[0].upper() + word[1:].lower()


def filter_images(data):
    brand_pattern = re.escape(data["brand_name"]) if data["brand_name"] else None
    brand_regex = rf'{brand_pattern}'
    extension_regex = r'\.(jpg|png|jpeg|jfif|pjpeg|pjp|svg|gif|webp)(\b|$|\?|[&#])'
    images_with_brand = []
    images_without_brand = []

    for image_url in data['images']:
        if brand_pattern and re.search(brand_regex, image_url, re.IGNORECASE):
            images_with_brand.append(image_url)
        elif re.search(extension_regex, image_url, re.IGNORECASE):
            images_without_brand.append(image_url)

    data['images'] = images_with_brand + images_without_brand


def sanitize_url(url):
    if not re.match(r'^https?://', url):
        url = 'https://' + url
    sanitized_url = re.sub(r'^(https?://)(?!www\.)', r'\1www.', url)
    return sanitized_url


def fetch_data(data):
    global headers

    data["brand_name"] = get_brand_name(data["url"])
    logger.info("brand_name : %s", data["brand_name"])

    before = time.time()
    is_title_source_url = get_is_title_source_url(data["brand_name"])
    logger.info(f"Time taken in get_is_title_source_url : {time.time() - before}")

    product_title = None
    if not is_title_source_url:
        before1 = time.time()
        product_title = get_title_from_meta_data(data)
        logger.info(f"Time taken in get_title_from_meta_data : {time.time() - before1}")
        data["brand_name"] = get_brand_name(data.get("url"))

    if is_title_source_url or not product_title:
        before = time.time()
        product_title = get_title_from_url(data["url"], data["brand_name"])
        logger.info(f"Time taken in get_title_from_url : {time.time() - before}")

    if not product_title:
        return

    before = time.time()
    data['title'] = sanitize_product_title(product_title, data["brand_name"])
    logger.info(f"Time taken in sanitize_product_title : {time.time() - before}")

    # before = time.time()
    # get_data_from_google_api(data)
    # logger.info(f"Time taken in get_data_from_google_api : {time.time() - before}")


def sanitize_product_title_amazon(product_title):
    return product_title.split(",")[0]


def sanitize_title(title, brand):
    # Normalize the brand by converting to lowercase and stripping whitespace
    if not brand:
        return title

    brand = brand.lower().strip()

    # Create patterns for the brand name and domain variations at the start or end of the title
    tld_list = "com|org|net|info|biz|edu|gov|mil|co|xyz|in|us|uk|ca|au|de|fr|cn|jp|br|ru|za|aero|asia|coop|museum|jobs|travel|tech|app|online|shop|blog|art|health|news|space|ad|ae|af|ag|ai|al|am|ao|aq|ar|as|at|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bl|bm|bn|bo|bq|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cu|cv|cw|cx|cy|cz|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|fi|fj|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|kj|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mf|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tr|tt|tv|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|za|zm|zw"
    brand_pattern = r"\s*".join(brand)
    brand_pattern = rf"^[^\w]*{brand_pattern}[^\w]*|[^\w]*{brand_pattern}[^\w]*$"
    domain_pattern = rf"(^|\s+){re.escape(brand)}\.({tld_list})[^\w\s]*"

    # Remove the brand name and domain variations from the title
    sanitized_title = re.sub(domain_pattern, "", title, flags=re.IGNORECASE)
    sanitized_title = re.sub(brand_pattern, "", sanitized_title, flags=re.IGNORECASE)

    # Remove any leading or trailing whitespace after processing
    sanitized_title = sanitized_title.strip()

    # Clean up any residual extra spaces created by the removal process
    sanitized_title = re.sub(r'\s{2,}', ' ', sanitized_title)

    # Remove any special characters from the start or end of the title
    sanitized_title = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', sanitized_title)

    return sanitized_title


def sanitize_product_title(product_title, brand_name):
    product_title = sanitize_title(product_title, brand_name)

    if brand_name == 'amazon':
        product_title = sanitize_product_title_amazon(product_title)

    return product_title


def get_brand_name(url):
    pattern = r'www\.([^.]+)\.'
    try:
        match = re.search(pattern, url)
    except Exception as e:
        print("error in get_brand_name : ", e)
        return None

    if match:
        return match.group(1)
    else:
        return None


def get_is_title_source_url(brand_name):
    if is_wsi_brand(brand_name) or brand_name == 'etsy' or brand_name == 'wayfair' or brand_name == 'crateandbarrel' \
            or brand_name == 'anthropologie' or brand_name == 'lumens':
        return True
    return False


def is_wsi_brand(brand_name):
    if ('westelm' == brand_name or 'potterybarn' == brand_name or 'rejuvenation' == brand_name or
            'williams-sonoma' == brand_name or 'pbteen' == brand_name or 'potterybarnkids' == brand_name):
        return True
    return False


def get_title_from_meta_data(data):
    before = time.time()
    html_response = get_html_response(data["url"])
    after = time.time()
    logger.info(f"Time taken in get_html_response {after - before}")
    if not html_response:
        return None

    data["url"] = html_response.url

    return get_title_update_images_from_meta_tags(html_response, data)


success_response_status_code_list = [200, 201]


def get_html_response(url):
    try:
        response = requests.get(url, headers=headers, timeout=4, allow_redirects=True, verify=False)

        logger.info(response.status_code)

        if response.status_code in success_response_status_code_list:
            return response
        else:
            logger.info(f"Received status code {response.status_code}, retrying...")

    except Exception as req_err:
        logger.info(f"Request error: {req_err}")

    return None


def get_title_update_images_from_meta_tags(html_response, data):
    html_content = html_response.text

    before = time.time()
    soup = BeautifulSoup(html_content, 'html.parser')
    logger.info(f"Time taken in BeautifulSoup {time.time() - before}")
    meta_tags = soup.find_all('meta')
    cnt = 0

    before = time.time()
    for meta_tag in meta_tags:
        cnt += 1
        for attr_value in meta_tag.attrs.values():
            if isinstance(attr_value, str) and 'og:' in attr_value:
                # logger.info(attr_value)
                if 'title' in attr_value:
                    # logger.info(meta_tag.get('content'))
                    data['title'] = meta_tag.get('content')
                elif 'image' in attr_value:
                    data['images'].append(meta_tag.get('content'))
                elif 'description' in attr_value:
                    data['description'] = meta_tag.get('content')
            else:
                if 'title' in attr_value and not data['title']:
                    # logger.info(meta_tag.get('content'))
                    data['title'] = meta_tag.get('content')
                elif 'image' in attr_value and not data['images']:
                    data['images'].append(meta_tag.get('content'))
                elif 'description' in attr_value and not data['description']:
                    data['description'] = meta_tag.get('content')

    if data['title'] == '':
        data['title'] = soup.title.string if soup.title else ''

    logger.info(f"Time taken in meta tags {time.time() - before}, \n Meta tags count : {cnt}")

    return data['title']


def get_title_from_url(url, brand_name):
    if is_wsi_brand(brand_name):
        return get_wsi_product_title_from_url(url)
    elif brand_name == 'etsy':
        return get_etsy_product_title_from_url(url)
    elif brand_name == 'wayfair':
        return get_wayfair_product_title_from_url(url)
    elif brand_name == 'crateandbarrel':
        return get_crateandbarrel_product_from_url(url)
    elif brand_name == 'anthropologie':
        return get_anthropologie_product_from_url(url)
    elif brand_name == 'lumens':
        logger.info("lumens")
        return get_lumens_product_title_from_url(url)

    return None


def get_lumens_product_title_from_url(url):
    # Regex pattern to match the title after 'lumens.com/'
    pattern = r'lumens\.com/([^/]+)-by-'

    # Search for the pattern in the URL
    match = re.search(pattern, url)

    if match:
        # Extract the title part
        title_with_hyphens = match.group(1)

        # Remove hyphens from the title
        title = title_with_hyphens.replace('-', ' ')

        return title
    else:
        return None

def get_wsi_product_title_from_url(url):
    arr = url.split('/')
    for i in range(0, len(arr)):
        temp_str = "products"
        if arr[i] == temp_str and i + 1 < len(arr):
            return arr[i + 1].replace("-", " ")
    return None


def get_etsy_product_title_from_url(url):
    pattern = r'/listing/\d+/([^/?]+)'
    match = re.search(pattern, url)

    if match:
        return match.group(1).replace("-", " ")
    return None


def get_wayfair_product_title_from_url(url):
    match = re.search(r'wayfair\.com/[^/]+/[^/]+/([^/?]+)(?:\?.*)?', url)
    # logger.info(match)

    if match:
        # Replace hyphens with spaces for readability
        title = match.group(1).replace('-', ' ')

        # logger.info(title)

        # Split the title into words and remove the last word if it's a SKU or identifier
        title_parts = title.split()
        cleaned_title = ' '.join(title_parts[:-1])  # Remove the last part (SKU or identifier)

        return cleaned_title
    else:
        return None


def get_crateandbarrel_product_from_url(url):
    match = re.search(r'\.com\/([^\/]+)', url)
    if match:
        product_title = match.group(1).replace('-', ' ')
        return product_title
    else:
        return None


def get_anthropologie_product_from_url(url):
    match = re.search(r'/shop/([^\/]+)', url)
    if match:
        match = re.search(r'/shop/([^\/?]+)', url)
        if match:
            # Replace hyphens with spaces in the extracted product title
            product_title = match.group(1).replace('-', ' ')
            return product_title
    else:
        return None


def get_data_from_google_api(data):
    if not data['title']:
        return

    global success_response_status_code_list

    api_key = "AIzaSyBU3CCsLdjPTPG0FLqjh7SdhIogmAP9Mls"
    cse_id = "1123473d2f0334801"

    search_string = data['title']
    if data['brand_name']:
        search_string = search_string + " from " + data['brand_name']

    url = (f"https://www.googleapis.com/customsearch/v1?cx={cse_id}&key={api_key}&q={search_string}"
           f"&searchType=image&num=7")

    response = requests.get(url, timeout=5)

    if response.status_code in success_response_status_code_list:
        response_data = response.json()
        extract_data_from_cse_response(response_data, data)
        return


def extract_data_from_cse_response(response, data):
    images = []

    if 'items' not in response:
        return

    for item in response.get('items'):
        link = item.get('link')
        if link:
            images.append(link)

    data['images'].extend(images)

    return


# Run the application using Uvicorn
if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=5000)
