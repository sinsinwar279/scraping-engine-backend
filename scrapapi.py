import random

from flask import Flask, jsonify, abort, request
import multiprocessing
import requests
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor
from flask_cors import CORS, cross_origin
import re
import logging

app = Flask(__name__)
CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type, authorization, access-control-allow-origin, Origin, X-Auth-Token,'
app.config["DEBUG"] = True

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


@app.route('/getTrackingDetailsWSI', methods=['POST'])
def get_tracking_details_wsi_function():
    req = request.get_json()

    app.logger.info(req)

    if not req.get("domain") or not req.get("order_id") or not req.get("zip_code"):
        return jsonify({"error": "Bad Request", "message": "missing parameters"}), 400

    url = f"https://www.{req.get('domain')}.com/customer-service/order-status/v1/order-details/index.json?orderNumber={req.get('order_id')}&postalCode={req.get('zip_code')}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        app.logger.info(data)
        return jsonify(data)

    except requests.exceptions.HTTPError as http_err:
        app.logger.error(response.status_code)
        app.logger.error(http_err)
        if response.status_code == 400:
            return jsonify({"error": "Bad Request", "message": response.text}), 400
        elif response.status_code == 401:
            return jsonify({"error": "Unauthorized", "message": response.text}), 401
        elif response.status_code == 403:
            return jsonify({"error": "Forbidden", "message": response.text}), 403
        elif response.status_code == 404:
            return jsonify({"error": "Not Found", "message": response.text}), 404
        elif response.status_code == 500:
            return jsonify({"error": "Internal Server Error", "message": response.text}), 500
        else:
            return jsonify({"error": "HTTP error occurred", "message": str(http_err)}), response.status_code

    except requests.exceptions.ConnectionError as conn_err:
        return jsonify({"error": "Connection error occurred", "message": str(conn_err)}), 503

    except requests.exceptions.Timeout as timeout_err:
        return jsonify({"error": "Timeout error occurred", "message": str(timeout_err)}), 504

    except requests.exceptions.RequestException as req_err:
        return jsonify({"error": "An error occurred", "message": str(req_err)}), 500


# Define another route that accepts parameters
@app.route('/scrap', methods=['POST'])
def get_responce():
    data = request.get_json()
    urlList = data.get('urls')

    before = time.time()

    results = get_response(urlList[0])

    after = time.time()

    app.logger.info("total time")
    app.logger.info(after - before)

    return [results]


def filter_images(data):
    brand_pattern = re.escape(data["brand_name"]) if data["brand_name"] else None
    # Regex to match any of the specified brand names or image file extensions
    brand_regex = rf'{brand_pattern}'
    extension_regex = r'\.(jpg|png|jpeg|jfif|pjpeg|pjp|svg|gif|webp)(\b|$|\?|[&#])'
    images_with_brand = []
    images_without_brand = []

    for image_url in data['images']:
        if brand_pattern and re.search(brand_regex, image_url, re.IGNORECASE):
            images_with_brand.append(image_url)
        elif re.search(extension_regex, image_url, re.IGNORECASE):
            images_without_brand.append(image_url)

    # Prioritize images with the brand name in their URL by appending them first
    data['images'] = images_with_brand + images_without_brand


def sanitize_url(url):
    # Ensure the URL has a scheme
    if not re.match(r'^https?://', url):
        url = 'https://' + url

    # Ensure the URL has 'www.' in the netloc
    # Match the scheme and netloc
    sanitized_url = re.sub(r'^(https?://)(?!www\.)', r'\1www.', url)

    return sanitized_url


def get_response(obj):
    data = {
        'title': '',
        'images': [],
        'description': '',
        'url': obj['url'],
        'brand_name': ''
    }

    data["url"] = sanitize_url(data["url"])

    before = time.time()
    fetch_data(data)
    app.logger.info(f"Time taken in fetch_data : {time.time() - before}")

    before = time.time()
    filter_images(data)
    app.logger.info(f"Time taken in filter_images : {time.time() - before}")

    before = time.time()
    data['title'] = title_case_product_title(data["title"])
    app.logger.info(f"Time taken in title_case_product_title : {time.time() - before}")

    return {
        'url': data["url"],
        'response': data
    }


def capitalize_first_letter(word):
    # Capitalize the first letter and make all other letters lowercase
    return word[0].upper() + word[1:].lower()


def title_case_product_title(sentence):
    # Split the sentence into individual words
    if not sentence:
        return ""
    words = sentence.split()
    # Capitalize each word
    capitalized_words = [capitalize_first_letter(word) for word in words]
    # Join the words back into a sentence
    return ' '.join(capitalized_words)


def is_wsi_brand(brand_name):
    if ('westelm' == brand_name or 'potterybarn' == brand_name or 'rejuvenation' == brand_name or
            'williams-sonoma' == brand_name or 'pbteen' == brand_name or 'potterybarnkids' == brand_name):
        return True
    return False


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
    if is_wsi_brand(brand_name) or brand_name == 'etsy' or brand_name == 'wayfair' or brand_name == 'crateandbarrel'\
            or brand_name == 'anthropologie':
        return True
    return False


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
    # app.logger.info(match)

    if match:
        # Replace hyphens with spaces for readability
        title = match.group(1).replace('-', ' ')

        # app.logger.info(title)

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

    return None


success_response_status_code_list = [200, 201]


def get_html_response(url):
    try:
        response = requests.get(url, headers=headers, timeout=4, allow_redirects=True, verify=False)

        app.logger.info(response.status_code)

        if response.status_code in success_response_status_code_list:
            return response
        else:
            app.logger.info(f"Received status code {response.status_code}, retrying...")

    except Exception as req_err:
        app.logger.info(f"Request error: {req_err}")

    return None


def get_title_update_images_from_meta_tags(html_response, data):
    html_content = html_response.text

    soup = BeautifulSoup(html_content, 'html.parser')
    meta_tags = soup.find_all('meta')
    for meta_tag in meta_tags:
        for attr_value in meta_tag.attrs.values():
            if isinstance(attr_value, str) and 'og:' in attr_value:
                # app.logger.info(attr_value)
                if 'title' in attr_value:
                    # app.logger.info(meta_tag.get('content'))
                    data['title'] = meta_tag.get('content')
                elif 'image' in attr_value:
                    data['images'].append(meta_tag.get('content'))
                elif 'description' in attr_value:
                    data['description'] = meta_tag.get('content')
            else:
                if 'title' in attr_value and not data['title']:
                    # app.logger.info(meta_tag.get('content'))
                    data['title'] = meta_tag.get('content')
                elif 'image' in attr_value and not data['images']:
                    data['images'].append(meta_tag.get('content'))
                elif 'description' in attr_value and not data['description']:
                    data['description'] = meta_tag.get('content')

    if data['title'] == '':
        data['title'] = soup.title.string if soup.title else ''

    return data['title']


def get_title_from_meta_data(data):
    before = time.time()
    html_response = get_html_response(data["url"])
    after = time.time()
    app.logger.info(f"Time taken in get_html_response {after - before}")
    if not html_response:
        return None

    data["url"] = html_response.url

    return get_title_update_images_from_meta_tags(html_response, data)


def sanitize_title(title, brand):
    # Normalize the brand by converting to lowercase and stripping whitespace
    if not brand:
        return title

    brand =  brand.lower().strip()

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


def sanitize_product_title_amazon(product_title):
    return product_title.split(",")[0]


def sanitize_product_title(product_title, brand_name):
    product_title = sanitize_title(product_title, brand_name)

    if brand_name == 'amazon':
        product_title = sanitize_product_title_amazon(product_title)

    return product_title


def fetch_data(data):
    global headers

    data["brand_name"] = get_brand_name(data["url"])

    is_title_source_url = get_is_title_source_url(data["brand_name"])
    product_title = None
    if not is_title_source_url:
        product_title = get_title_from_meta_data(data)
        data["brand_name"] = get_brand_name(data.get("url"))

    if is_title_source_url or not product_title:
        before = time.time()
        product_title = get_title_from_url(data["url"], data["brand_name"])
        app.logger.info(f"Time taken in get_title_from_url : {time.time() - before}")

    if not product_title:
        return

    before = time.time()
    data['title'] = sanitize_product_title(product_title, data["brand_name"])
    app.logger.info(f"Time taken in sanitize_product_title : {time.time() - before}")

    before = time.time()
    get_data_from_google_api(data)
    app.logger.info(f"Time taken in get_data_from_google_api : {time.time() - before}")


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


# Run the Flask application
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, threaded=True, port=5000)
