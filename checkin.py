# -*- coding: UTF-8 -*-
import argparse
import json
import logging
import os
import re
import sys
import threading
import time
import warnings
import typing
from urllib.parse import urlparse

import requests
from lxml import etree

warnings.filterwarnings('ignore')

parser = argparse.ArgumentParser()

'''
run example

checkin.py tsdm.cookies.json -t tsdm -f 0a0000a0 -hook http://127.0.0.1

checkin.py tsdm.cookies.json -t tsdm -f 0a0000a0
checkin.py zod.cookies.json -t zod -f 0a0000a0 -p socks5h://127.0.0.1:1080
checkin.py zod.cookies.json -t zod -f 0a0000a0 -l 20 -i 5 -p socks5h://127.0.0.1:1080
# ↑ 5ms run once, total 20s.

'''

parser.add_argument('cookies', nargs=1, help='input cookies json file')
parser.add_argument('-f', '-formhash', '--formhash', help='formhash value', metavar="formhash")
parser.add_argument('-p', '-proxy', '--proxy', help='use proxy', metavar="proxy url")
parser.add_argument('-l', '-loop', '--loop', type=int, help='loop time secound, default 10ms run once',
                    metavar="LOOP_TIME")
parser.add_argument('-i', '-interval', '--interval', type=int, default=10, help='loop interval, ms, default 10',
                    metavar="LOOP_INTERVAL")
parser.add_argument('-t', '-type', '--type', choices=['tsdm', 'zod', 'plus'],
                    help='choices checkin site, tsdm、zod、plus',
                    metavar="CHECKIN_SITE", required=False)
parser.add_argument('-hook', '--hook', help='call web hook url, post json data {"msg": "msg content"} in body',
                    metavar="call web hook url")
parser.add_argument('-FlareSolverr', '--FlareSolverr', help='FlareSolverr url, use FlareSolverr to bypass Cloudflare protection ',
                    metavar="FlareSolverr url")
# https://github.com/Anorov/cloudflare-scrape/issues/406
parser.add_argument("-cf", "--cf", help="pass Cloudflare's anti-bot page", action="store_true")
args = parser.parse_args()

form_hash = args.formhash
proxy = args.proxy
site_type = args.type
loopTime = args.loop
interval = args.interval
IS_CF = args.cf
FLARE_SOLVERR_URL = args.FlareSolverr
COOKIES_FILE = os.path.realpath(os.path.join(os.getcwd(), args.cookies[0]))

HOOK_URL = args.hook

PROGRAM_DIR_PATH = os.path.dirname(os.path.abspath(sys.argv[0]))
# CACHE_FILE_PATH = os.path.join(PROGRAM_DIR_PATH, 'CACHE.json')

DYNAMODB_TABLE_NAME = 'CheckinCache'

taskTimer: typing.Optional[threading.Timer] = None

logging.basicConfig(level=logging.INFO, format='{} - %(asctime)s \n\t %(levelname)s - %(message)s'.format(COOKIES_FILE))
logger = logging.getLogger(__name__)

URL_LINK = {
    "plus": {
        "formhash": "https://www.south-plus.net/",
        "checkin": "https://www.south-plus.net/plugin.php",
        "checkin-status": None,
        "get_job": {
            "H_name": "tasks",
            "action": "ajax",
            "actions": "job",
            "cid": "15",
            "nowtime": "",
            "verify": "",
        },
        "done_job": {
            "H_name": "tasks",
            "action": "ajax",
            "actions": "job2",
            "cid": "15",
            "nowtime": "",
            "verify": "",
        },
        "template": {}
    },
    "tsdm": {
        "formhash": "https://www.tsdm39.com/forum.php",
        "checkin": "https://www.tsdm39.com/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1&sign_as=1"
                   "&inajax=1",
        "checkin-status": {
            "sign": "https://www.tsdm39.com/plugin.php?id=dsu_paulsign:sign",
            "checkinInfoXpath": '//*[@class="mn"]/p',
            "hasCheckinXpath": 'string(//*[@class="mt"][1])'
        },
        "template": {
            "formhash": "",
            "qdxq": "wl",
            "todaysay": "HHHHH",
            "qdmode": "3",
            "fastreply": "0"
        }
    },
    "zod": {
        "formhash": "https://zodgame.xyz/forum.php",
        "checkin": "https://zodgame.xyz/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1&inajax=1",
        "checkin-status": {
            "sign": "https://zodgame.xyz/plugin.php?id=dsu_paulsign:sign",
            "checkinInfoXpath": '//*[@class="mn"]/p',
            "hasCheckinXpath": 'string(//*[@class="mt"][1])'
        },
        "template": {
            "formhash": "",
            "qdxq": "wl"
        }
    }
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'
}

COOKIES = {}

PROXIES = None
if proxy is not None:
    PROXIES = {
        'http': proxy,
        'https': proxy
    }


def plus_checkin(formhash, cid):
    url = URL_LINK[site_type]['checkin']
    params = URL_LINK[site_type]['get_job']
    params['cid'] = cid
    params['verify'] = formhash
    params['nowtime'] = str(int(time.time()*1000))
    r = requests.get(url, params=params, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
    content = r.text
    logger.info(content)

    params = URL_LINK[site_type]['done_job']
    params['cid'] = cid
    params['verify'] = formhash
    params['nowtime'] = str(int(time.time()*1000))
    r = requests.get(url, params=params, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
    content = r.text
    logger.info(content)


def checkin(url, data):
    if site_type == 'plus':
        plus_checkin(data['formhash'], '15')
        plus_checkin(data['formhash'], '14')
        return dict()
    else:
        r = requests.post(url, data=data, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
        content = r.text
        if content.find('登录') != -1:
            logger.info('cookies expire')
            sys.exit(0)
        if content.find('未定义操作') != -1:
            return {'error': 'formhash'}
        result = re.search('(.*?)</div>', content).group(1)
    return result


def get_form_hash(url):
    r = requests.get(url, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
    html_etree = etree.HTML(r.text)
    if site_type == 'plus':
        temp = html_etree.xpath("/html/head/script[4]/text()")
        temp = ''.join(temp)
        form_hash_value = re.search('verifyhash[^\']*\'(\\w+)\'', temp).group(1)
    else:
        form_hash_value = html_etree.xpath("//*[@name='formhash']/@value")
        form_hash_value = ''.join(form_hash_value)
        if len(form_hash_value) == 0:
            form_hash_value = re.match('.*;formhash=(\\w*).*', r.text, re.S).group(1)
    return form_hash_value


def read_cookies_file():
    f = None
    try:
        temp, ext = os.path.splitext(COOKIES_FILE)
        global RAW_COOKIES
        if ext.lower() == '.json':
            with open(COOKIES_FILE, mode='r', encoding='utf-8') as f:
                data = json.load(f)
                RAW_COOKIES = data
                if isinstance(data, list):
                    cookies = {obj['name']: obj['value'] for obj in data}
                else:
                    cookies = data
        else:
            cookies = {}
            f = open(COOKIES_FILE, 'r')
            for line in f.readlines():
                line = line.strip()
                key = line[0:line.index('=')]
                val = line[line.index('=') + len('='):]
                if val.rfind(';') == len(val) - 1:
                    val = val[0: len(val) - 1]
                cookies[key] = val
    finally:
        if f:
            f.close()
    return cookies


def do_checkin(url, data):
    result = checkin(url, data)
    if isinstance(result, dict) and 'error' in result.keys():
        if result['error'] == 'formhash':
            logger.info("formhash: {}  错误，重新获取 formhash".format(data['formhash']))
            data['formhash'] = get_form_hash(URL_LINK[site_type]['formhash'], site_type)
            logger.info("当前 formhash: {}".format(data['formhash']))
            result = checkin(url, data)
    logger.info("{}".format(result))


def loop_do_checkin(file, url, data, start_time, loop_time):
    now_time = time.time()
    if now_time - start_time < loop_time:
        global taskTimer
        taskTimer = threading.Timer(interval / 1000, loop_do_checkin, (file, url, data, start_time, loop_time,))
        taskTimer.start()
    do_checkin(url, data)


def get_checkin_info(check_status_obj):
    if check_status_obj is None:
        return
    url = check_status_obj['sign']
    has_checkin_xpath = check_status_obj['hasCheckinXpath']
    checkin_info_xpath = check_status_obj['checkinInfoXpath']
    r = requests.get(url, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
    html_etree = etree.HTML(r.text)
    has_checkin = html_etree.xpath(has_checkin_xpath)
    logger.info(has_checkin)
    if has_checkin.find('已经签到') == -1:
        return

    checkin_info_count = html_etree.xpath('count(' + checkin_info_xpath + ')')
    checkin_info_list = []
    for i in range(int(checkin_info_count)):
        p = html_etree.xpath('string(' + checkin_info_xpath + '[' + str(i) + '])')
        if p is not None:
            checkin_info_list.append(p)
    checkin_info = '\n'.join(checkin_info_list)
    checkin_date = re.findall('(\\d{4}-\\d{2}-\\d{2})', checkin_info)
    if len(checkin_date) > 0:
        if HOOK_URL is not None:
            payload = {'msg': checkin_info}
            logger.info('Send msg: {} to {}'.format(payload, HOOK_URL))
            requests.post(HOOK_URL, json=payload)


def flare_solverr(site_obj):
    try:
        url_info = urlparse(site_obj['checkin'])
        domain_url = url_info.scheme + '://' + url_info.netloc
        r = requests.post(FLARE_SOLVERR_URL,  json={
            "cmd": "request.get",
            "url": domain_url,
            "cookies": RAW_COOKIES,
            "proxy": {"url": PROXIES['http']} if PROXIES else None,
            "maxTimeout": 50000,
        }, verify=False,
                         timeout=60000)
        ret = r.json()
        status = ret['status']
        if status != 'ok':
            logger.error('FlareSolverr fail')
            logger.error(ret['message'])
            return
        ret = ret['solution']
        HEADERS['user-agent'] = ret['userAgent']
        temp_cookies = ret['cookies']
        for t in temp_cookies:
            COOKIES[t['name']] = t['value']
    finally:
        ...

def use_cf(site_obj):
    try:
        import cfscrape
        url_info = urlparse(site_obj['checkin'])
        domain_url = url_info.scheme + '://' + url_info.netloc
        cookie_value, user_agent = cfscrape.get_tokens(domain_url, proxies=PROXIES)
        HEADERS['user-agent'] = user_agent
        COOKIES.update(cookie_value)
    finally:
        ...


def main():
    logger.info("Start")
    global COOKIES
    COOKIES = read_cookies_file()

    site_obj = URL_LINK[args.type]
    if FLARE_SOLVERR_URL is not None:
        flare_solverr(site_obj)
    elif IS_CF:
        use_cf(site_obj)

    global form_hash
    if form_hash is None:
        form_hash = get_form_hash(site_obj['formhash'])
    # logger.info('Use formhash: {}'.format(formhash))
    data = site_obj['template']
    data['formhash'] = form_hash

    if loopTime is None:
        do_checkin(site_obj['checkin'], data)
    else:
        start_time = time.time()
        loop_do_checkin(COOKIES_FILE, site_obj['checkin'], data, start_time, loopTime)
    global taskTimer
    while taskTimer is not None and not taskTimer.is_alive():
        time.sleep(5)
    if HOOK_URL is not None:
        get_checkin_info(site_obj['checkin-status'])


if __name__ == '__main__':
    main()
