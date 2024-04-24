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
    'X-APP-NAME': 'Minoan'
}


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


#     results = []
#     for obj in urlList:
#         results.append(getResponse(obj))

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

    before = time.time()
    fetchData(url, data)
    after = time.time()
    app.logger.info("fetchData response time")
    app.logger.info(after - before)

    before = time.time()
    filterImages(data)
    after = time.time()
    app.logger.info("filterImages response time")
    app.logger.info(after - before)

    before = time.time()
    data['title'] = titleCaseProductTitle(data.get("title"))
    after = time.time()
    app.logger.info("titleCaseProductTitle response time")
    app.logger.info(after - before)

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

#     res = 200
#     while res == 200:
#         response = requests.get(url, headers=headers)
#         print(response.status_code, "response status")
#         res = response.status_code

#     print(response, "response")


    response = requests.get(url, headers=headers)
    # app.logger.info('%s response', response.text)
    # app.logger.info('%s response', response.status_code)
    app.logger.info(url)
    app.logger.info("res")
    app.logger.info(response.status_code)

    if (response.status_code == 200 or response.status_code == 201):
        getOgPrefixMetaTags(response, data)
#         print(data, "data")
        app.logger.info("data")
        app.logger.info(data)

        if (data.get('title') == '' or data.get('title') == 'West Elm: 403 - Restricted Access'):
            if 'westelm' in url or 'potterybarn' in url or 'rejuvenation' in url or 'williams-sonoma' in url or 'pbteen' in url or 'potterybarnkids' in url:
                arr = url.split('/')
                for i in range(0, len(arr)):
                    str = "products"
#                     if 'potterybarnkids' in url:
#                         str = "shop"
                    if arr[i] == str and i + 1 < len(arr):
                        data['title'] = arr[i + 1].replace("-", " ")
                        # print(arr[i + 1].replace("-", " ").rsplit(' ', 1), "title")
                        getDataFromGoogleApi(data.get('title'), data)
                        return data

            return {"error": "No response from Clint's server"}
        else:
            getDataFromGoogleApi(data.get('title'), data)

        return data

    else:
        if 'westelm' in url or 'potterybarn' in url or 'rejuvenation' in url or 'williams-sonoma' in url or 'pbteen' in url or 'potterybarnkids' in url:
            arr = url.split('/')
            before = time.time()
            for i in range(0, len(arr)):
                bi = time.time()
                str = "products"
                if arr[i] == str and i + 1 < len(arr):
                    data['title'] = arr[i + 1].replace("-", " ")
                    # print(arr[i + 1].replace("-", " ").rsplit(' ', 1), "title")
                    getDataFromGoogleApi(data.get('title'), data)
                    return data
                ei = time.time()
                app.logger.info("for i response time : ")
                app.logger.info(i)
                app.logger.info(ei - bi)
            after = time.time()
            app.logger.info("for loop response time")
            app.logger.info(after - before)

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

    api_key = "AIzaSyBU3CCsLdjPTPG0FLqjh7SdhIogmAP9Mls"
    cse_id = "1123473d2f0334801"

    # api_key = "AIzaSyD4GOZSGBQlg0xzBl9qQkpNdBVkHfohLDA"
    # cse_id = "2070d058d8eee4de0"

    url = f"https://www.googleapis.com/customsearch/v1?cx={cse_id}&key={api_key}&q={productTitle}&searchType=image&num=10"

    before = time.time()
    response = requests.get(url)
    after = time.time()

    app.logger.info(after - before)
    app.logger.info("google api time")

    if response.status_code == 200:
        return extractDataFromCSEResponse(response.json(), data)


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
    app.run(host='0.0.0.0', debug=True, threaded=True, port=5000)