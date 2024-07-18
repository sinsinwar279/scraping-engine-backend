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

    if not req.get("domain") or not req.get("order_id") or not req.get("zip_code"):
        return jsonify({"error": "Bad Request", "message": "missing parameters"}), 400

    url = f"https://www.{req.get('domain')}.com/customer-service/order-status/v1/order-details/index.json?orderNumber={req.get('order_id')}&postalCode={req.get('zip_code')}"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()
        return jsonify(data)

    except requests.exceptions.HTTPError as http_err:
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

    num_cores = multiprocessing.cpu_count()
    max_workers = num_cores + 1

    before = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit API requests asynchronously
        futures = [executor.submit(getResponse, obj) for obj in urlList]

        # Wait for all the API requests to complete
        results = [future.result() for future in futures]

    after = time.time()

    app.logger.info("total time")
    app.logger.info(after - before)

    return jsonify(results)


def filterImages(data):
    pattern = r'\.(jpg|png|jpeg|jfif|pjpeg|pjp|svg|gif|webp)'
    modified_images = []

    for image_url in data['images']:
        if re.search(pattern, image_url, re.IGNORECASE):
            modified_images.append(image_url)

    data['images'] = modified_images


def getResponse(obj):
    url = obj['url']
    id = obj['id']

    data = {
        'title': '',
        'images': [],
        'description': ''
    }

    fetchData(url, data)

    filterImages(data)

    data['title'] = titleCaseProductTitle(data.get("title", ""))

    return {
        'url': url,
        'id': id,
        'response': data
    }


def capitalize_first_letter(word):
    # Capitalize the first letter and make all other letters lowercase
    return word[0].upper() + word[1:].lower()


def titleCaseProductTitle(sentence):
    # Split the sentence into individual words
    if not sentence:
        return ""
    words = sentence.split()
    # Capitalize each word
    capitalized_words = [capitalize_first_letter(word) for word in words]
    # Join the words back into a sentence
    return ' '.join(capitalized_words)


def fetchData(url, data, callCount=0):
    global maxCallLimit, headers
    if callCount >= maxCallLimit:
        return None

    if 'westelm' in url or 'potterybarn' in url or 'rejuvenation' in url or 'williams-sonoma' in url or 'pbteen' in url or 'potterybarnkids' in url:
        arr = url.split('/')
        for i in range(0, len(arr)):
            str = "products"
            if arr[i] == str and i + 1 < len(arr):
                data['title'] = arr[i + 1].replace("-", " ")
                getDataFromGoogleApi(data.get('title'), data)
                return data
    else:
        res = 403
        try:
            response = requests.get(url, headers=headers, timeout=5)
            res = response.status_code
        except requests.exceptions.HTTPError as http_err:
            app.logger.info(response.status_code)
            return fetchData(url, data, callCount + 1)

        app.logger.info("*************")
        app.logger.info(url)
        app.logger.info("response status")
        # app.logger.info(response.status_code)

        if res == 200:
            getOgPrefixMetaTags(response, data)
            app.logger.info("*************")
            app.logger.info("data")
            app.logger.info(data)

            getDataFromGoogleApi(data.get('title'), data)

            return data

    return {"error": f"No response from Clint's server {response}"}


def getOgPrefixMetaTags(response, data):
    html_content = response.text

    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    # app.logger.info(soup)
    # json = soup.find('script', type='application/ld+json')
    # Extract meta tags from the parsed HTML
    meta_tags = soup.find_all('meta')
    # app.logger.info("Called")
    for meta_tag in meta_tags:
        for attr_value in meta_tag.attrs.values():
            if isinstance(attr_value, str) and 'og:' in attr_value:
                # app.logger.info(attr_value)
                if ('title' in attr_value):
                    # app.logger.info(meta_tag.get('content'))
                    data['title'] = meta_tag.get('content')
                elif ('image' in attr_value):
                    data['images'].append(meta_tag.get('content'))
                elif ('description' in attr_value):
                    data['description'] = meta_tag.get('content')

    if (data.get('title') == ''):
        data['title'] = soup.title.string if soup.title else ''

    return


def getDataFromGoogleApi(productTitle, data, callCount=0):
    global maxCallLimit
    if callCount >= maxCallLimit:
        return None

    api_key = "AIzaSyBU3CCsLdjPTPG0FLqjh7SdhIogmAP9Mls"
    cse_id = "1123473d2f0334801"

    url = f"https://www.googleapis.com/customsearch/v1?cx={cse_id}&key={api_key}&q={productTitle}&searchType=image&num=7"

    before = time.time()
    response = requests.get(url)
    after = time.time()

    app.logger.info("***********************************")
    app.logger.info("google api time")
    app.logger.info(after - before)

    if response.status_code == 200:
        return extractDataFromCSEResponse(response.json(), data)
    else:
        return getDataFromGoogleApi(productTitle, data, callCount + 1)


def extractDataFromCSEResponse(response, data):
    images = []

    if not 'items' in response:
        return

    for item in response.get('items'):
        link = item.get('link')
        if link:
            images.append(link)

    # print(len(images))

    data['images'].extend(images)

    return


# Run the Flask application
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, threaded=True, port=5001)
