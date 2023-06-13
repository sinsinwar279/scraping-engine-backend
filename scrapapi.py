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
maxCallLimit = 4

headers = {

    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:98.0) Gecko/20100101 Firefox/98.0",
    #   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
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
}


# Define another route that accepts parameters
@app.route('/scrap', methods=['POST'])
def get_responce():
    data = request.get_json()
    urlList = data.get('urls')

    num_cores = multiprocessing.cpu_count()
    max_workers = num_cores + 1

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit API requests asynchronously
        futures = [executor.submit(getResponse, obj) for obj in urlList]

        # Wait for all the API requests to complete
        results = [future.result() for future in futures]

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

    return {
        'url': url,
        'id': id,
        'response': data
    }


def fetchData(url, data, callCount=0):
    global maxCallLimit, headers

    response = requests.get(url, headers=headers)

    if (response.status_code == 200):
        getOgPrefixMetaTags(response, data)

        if (data.get('title') == ''):
            if (callCount > maxCallLimit):
                # abort(400, "No response from Clint's server")
                return {"error": "No response from Clint's server"}

            time.sleep(delay[callCount])
            return fetchData(url, data, callCount + 1)

        getDataFromGoogleApi(data.get('title'), data)

        return data

    elif (response.status_code == 500):
        if (callCount > maxCallLimit):
            # abort(400, "No response from Clint's server")
            return {"error": "No response from Clint's server"}

        time.sleep(delay[callCount])
        return fetchData(url, data, callCount + 1)

    # abort(400, "No response from Clint's server")
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

    if (callCount >= maxCallLimit):
        # abort(400, "No response from CSE")
        return []

    api_key = "AIzaSyBU3CCsLdjPTPG0FLqjh7SdhIogmAP9Mls"
    cse_id = "1123473d2f0334801"

    # api_key = "AIzaSyD4GOZSGBQlg0xzBl9qQkpNdBVkHfohLDA"
    # cse_id = "2070d058d8eee4de0"

    url = f"https://www.googleapis.com/customsearch/v1?cx={cse_id}&key={api_key}&q={productTitle}&searchType=image&num=10"

    response = requests.get(url)

    if response.status_code == 200:
        return extractDataFromCSEResponse(response.json(), data)
    else:
        time.sleep(delay[callCount])
        return getDataFromGoogleApi(url, data, callCount + 1)


def extractDataFromCSEResponse(response, data):
    images = []

    for item in response.get('items'):
        link = item.get('link')
        if link:
            images.append(link)

    print(len(images))

    data['images'].extend(images)

    return


# Run the Flask application
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, threaded=True, port=5000)
