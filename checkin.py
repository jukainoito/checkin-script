# -*- coding: UTF-8 -*-
import requests
import traceback
import json
import os
import re
import sys
import time
from urllib.parse import urlparse

from lxml import etree

import cfscrape

import argparse

import threading

import warnings
warnings.filterwarnings('ignore')


import logging



parser = argparse.ArgumentParser()

'''
run explame

checkin.py tsdm.cookies.json -t tsdm -f 0a0000a0 -hook http://127.0.0.1

checkin.py tsdm.cookies.json -t tsdm -f 0a0000a0
checkin.py zod.cookies.json -t zod -f 0a0000a0 -p socks5h://127.0.0.1:1080
checkin.py zod.cookies.json -t zod -f 0a0000a0 -l 20 -i 5 -p socks5h://127.0.0.1:1080
# ↑ 5ms run once, total 20s.

'''

parser.add_argument('cookies', nargs=1,  help='input cookies json file')
parser.add_argument('-f', '-formhash', '--formhash', help='formhash value', metavar="formhash")
parser.add_argument('-p', '-proxy', '--proxy', help='use proxy', metavar="proxy url")
parser.add_argument('-l', '-loop', '--loop', type=int, help='loop time secound, default 10ms run once', metavar="LOOP_TIME")
parser.add_argument('-i', '-interval', '--interval', type=int, default=10, help='loop interval, ms, default 10', metavar="LOOP_INTERVAL")
parser.add_argument('-t', '-type', '--type', choices=['tsdm', 'zod'], help='choices checkin site, tsdm、zod', metavar="CHECKIN_SITE", required=False)
parser.add_argument('-hook', '--hook', help='call web hook url, post json data {"msg": "msg content"} in body', metavar="call web hook url")
parser.add_argument("-cf", "--cf", help="pass Cloudflare's anti-bot page", action="store_true")
args = parser.parse_args()



formhash = args.formhash
proxy = args.proxy
site_type = args.type
loopTime = args.loop
interval = args.interval
IS_CF = args.cf
COOKIES_FILE = os.path.realpath(os.path.join(os.getcwd(), args.cookies[0]))

HOOK_URL = args.hook

PROGRAM_DIR_PATH = os.path.dirname(os.path.abspath(sys.argv[0]))
CACHE_FILE_PATH = os.path.join(PROGRAM_DIR_PATH, 'CACHE.json')

taskTimer = None

logging.basicConfig(level = logging.INFO, format = '{} - %(asctime)s \n\t %(levelname)s - %(message)s'.format(COOKIES_FILE))
logger = logging.getLogger(__name__)

URL_LINK = {
	"tsdm": {
		"formhash": "https://www.tsdm39.net/forum.php",
		"checkin": "https://www.tsdm39.net/plugin.php?id=dsu_paulsign:sign&operation=qiandao&infloat=1&sign_as=1&inajax=1",
		"checkin-status": {
			"sign": "https://www.tsdm39.net/plugin.php?id=dsu_paulsign:sign",
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
	'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36'
}

COOKIES = {}

PROXIES = None
if proxy is not None:
	PROXIES = {
	    'http': proxy,
	    'https': proxy
	}


def checkIn(url, data):
	r = requests.post(url, data=data,headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
	content = r.text
	if content.find('登录') != -1:
		logger.info('cookies expire')
		sys.exit(0)
	if content.find('未定义操作') != -1:
		return {'error': 'formhash'}
	result = re.search('(.*?)</div>', content).group(1)
	return result

def getFormhash(url):
	r = requests.get(url, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
	htmlEtree = etree.HTML(r.text)
	formhash = htmlEtree.xpath("//*[@name='formhash']/@value")
	formhash = ''.join(formhash)
	if len(formhash) == 0:
		formhash = re.match('.*;formhash=(\w*).*', r.text, re.S).group(1)
	return formhash

def readCookiesFile():
	cookies = {}
	try:
		temp, ext = os.path.splitext(COOKIES_FILE)
		if ext.lower() == '.json':
			with open(COOKIES_FILE, mode='r', encoding='utf-8') as f:
				data = json.load(f)
				if isinstance(data, list):
					cookies = {obj['name']:obj['value'] for obj in data}
				else:
					cookies = data
		else:
			cookies = {}
			f = open(COOKIES_FILE, 'r')
			for line in f.readlines():
				line = line.strip()
				key = line[0:line.index('=')]
				val = line[line.index('=')+len('='):]
				if val.rfind(';') == len(val) -1 :
					val = val[0: len(val)-1]
				cookies[key] = val
	finally:
		if f:
			f.close()
	return cookies

def doCheckIn(file, url, data):
	result = checkIn(url, data)
	if isinstance(result, dict) and 'error' in result.keys():
		if result['error'] == 'formhash':
			logger.info("formhash: {}  错误，重新获取 formhash".format(data['formhash']))
			data['formhash'] = getFormhash(FORMHASH_URL)
			logger.info("当前 formhash: {}".format(data['formhash']))
			result = checkIn(url, data)
	logger.info("{}".format(result))

def loopDoCheckIn(file, url, data, startTime, loopTime):
	nowTime = time.time()
	if nowTime-startTime < loopTime:
		global taskTimer
		taskTimer = threading.Timer(interval/1000, loopDoCheckIn, (file, url, data, startTime, loopTime,))
		taskTimer.start()
	doCheckIn(file, url, data)	

def getCheckinInfo(checkStatusObj):
	url = checkStatusObj['sign']
	hasCheckinXpath = checkStatusObj['hasCheckinXpath']
	checkinInfoXpath = checkStatusObj['checkinInfoXpath']
	r = requests.get(url, headers=HEADERS, cookies=COOKIES, proxies=PROXIES, verify=False, timeout=60)
	htmlEtree = etree.HTML(r.text)
	hasCheckin = htmlEtree.xpath(hasCheckinXpath)
	logger.info(hasCheckin)
	if hasCheckin.find('已经签到') == -1:
		return

	# toDay = time.strftime("%Y%m%d")
	# if toDay == CACHE[site_type]:
	# 	return

	checkinInfoCount = htmlEtree.xpath('count(' + checkinInfoXpath + ')')
	checkinInfoList = []
	for i in range(int(checkinInfoCount)):
		p = htmlEtree.xpath('string(' + checkinInfoXpath + '[' + str(i) + '])')
		if p is not None:
			checkinInfoList.append(p)
	checkinInfo = '\n'.join(checkinInfoList)
	logger.info('{}'.format(checkinInfo))
	# if command is not None:
	# 	command_line = Template(command).substitute(info=checkinInfo)
	# 	print(command_line)
	# 	command_args = shlex.split(command_line)
	# 	try:
	# 		subprocess.check_call(command_args)
	# 	except subprocess.CalledProcessError:
	# 		traceback.print_exc()
	# CACHE[site_type] = toDay
	checkinDate = re.findall('(\d{4}-\d{2}-\d{2})',checkinInfo)
	if len(checkinDate) > 0:
		checkinDate = checkinDate[0]
		data = {}
		if os.path.exists(CACHE_FILE_PATH):
			with open(CACHE_FILE_PATH, mode='r', encoding='utf-8') as f:
				try:
					data = json.load(f)
				except Exception:
					pass
				finally:
					f.close()
		if COOKIES_FILE in data.keys() and data[COOKIES_FILE] == checkinDate:
			return

		if HOOK_URL is not None:
			payload = {'msg': checkinInfo}
			logger.info('Send msg: {} to {}'.format(payload, HOOK_URL))
			requests.post(HOOK_URL, json=payload)

		data[COOKIES_FILE] = checkinDate		
		with open(CACHE_FILE_PATH, mode='w', encoding='utf-8') as f:
			json.dump(data, f)
			f.close()

def useCf(siteObj):
	urlInfo=urlparse(siteObj['checkin'])
	domainUrl = urlInfo.scheme + '://' + urlInfo.netloc
	cookie_value, user_agent = cfscrape.get_tokens(domainUrl, proxies=PROXIES)
	HEADERS['user-agent'] = user_agent
	COOKIES.update(cookie_value)

def main():
	logger.info("Start")
	global COOKIES
	COOKIES = readCookiesFile()


	siteObj = URL_LINK[args.type]

	if IS_CF:
		useCf(siteObj)

	global formhash
	if formhash is None:
		formhash = getFormhash(siteObj['formhash'])
	logger.info('Use formhash: {}'.format(formhash))
	data = siteObj['template']
	data['formhash'] = formhash

	if loopTime is None:
		doCheckIn(COOKIES_FILE, siteObj['checkin'], data)
	else:
		startTime = time.time()
		loopDoCheckIn(COOKIES_FILE, siteObj['checkin'], data, startTime, loopTime)
	global taskTimer
	while taskTimer is not None and not taskTimer.is_alive():
		time.sleep(5)
	if HOOK_URL is not None:
		getCheckinInfo(siteObj['checkin-status'])


if __name__ == '__main__':
	main()

