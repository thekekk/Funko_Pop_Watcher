#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import os
import json
import time
import hashlib
import logging
import requests
import threading
import validators
import urllib.request

from threading import Thread
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, date
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - '
                    '%(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TIMEOUT = {}
THREAD_ALIVE = False
SEM = threading.Semaphore()

# Define user specific attributed
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHATID']

# Create the EventHandler and pass it your bot's token.
UPDATER = Updater(TELEGRAM_TOKEN)

HTML_OBJ = {
    "hottopic": {"type": "div", "filter": {"class": "presale-pdp viewpage-pdp"}},
    "boxlunch": {"type": "div", "filter": {"class": "availability-msg"}},
    "walmart": {"type": "div", "filter": {"class": "prod-CallToActionSection hf-BotRow"}},
    "barnesandnoble": {"type": "section", "filter": {"id": "skuSelection"}},
    "gamestop": {"type": "div", "filter": {"class": "button qq"}},
    "blizzard": {"type": "div", "filter": {"class": "columns small-12 hide-for-small-only"}},
    "geminicollectibles": {"type": "div", "filter": {"style": "display: none"}},
    "target": {"type": "div", "filter": {"class": "Col-lvtw7q-0 ehJzUH"}}
}

class StoreStock(object):
    def check_funko(self, site, url):
        global TIMEOUT
        status = False

        logger.warning('Checking {0}'.format("Checking: " + site + " " + url))
    
        if site in ['blizzard']:
            status = self.out_of_stock(site, url)  
        elif site in ['hottopic', 'boxlunch']:
            status = self.in_stock(site, url)
        elif site in ['walmart', 'barnesandnoble', 'gamestop', 'blizzard', 'geminicollectibles', 'target']:
            status = self.add_to_cart(site, url)
    
        if status:
            msg = site + " - In Stock: " + ":\n" + url
            UPDATER.bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                                          text=msg)
            url_md5 = hashlib.md5(url.encode('utf-8')).hexdigest()
            TIMEOUT[url_md5] = datetime.today().date()
            logger.warning('Timeout Set: {0}'.format(url_md5))

    def pop_search(self, sleep_interval=60):
        global SEM, TIMEOUT, THREAD_ALIVE

        while True:  
            # Load in items from pops.json
            if THREAD_ALIVE:
                SEM.acquire()
                with open('pops.json') as data_file:
                    funkopop_links = json.load(data_file)
                SEM.release()
        
                for funko in funkopop_links:
                    url_md5 = hashlib.md5(funko['url'].encode('utf-8')).hexdigest()
                    try:
                        if not url_md5 in TIMEOUT:
                            self.check_funko(funko['store'], funko['url'])
                        elif url_md5 in TIMEOUT and TIMEOUT[url_md5] < datetime.today().date():
                            if datetime.now().hour > 7:
                                self.check_funko(funko['store'], funko['url'])
                    except Exception as excp:
                        logger.error('Exception {0}'.format(excp))
        
            time.sleep(sleep_interval)

    def url_to_html(self, url):
        product_page = urllib.request.Request(url, headers={'User-Agent' : "Magic Browser"})   
        r = urllib.request.urlopen(product_page)
        return BeautifulSoup(r.read(),"html5lib")

    def in_stock(self, site, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all(HTML_OBJ[site]["type"],
                                    HTML_OBJ[site]["filter"])
        return re.search(r'\bIn Stock\b', str(html_source))

    def add_to_cart(self, site, url):
        response = False
        soup = self.url_to_html(url)
        html_source = soup.find_all(HTML_OBJ[site]["type"],
                                    HTML_OBJ[site]["filter"])
        if re.search(r'\bAdd to Cart\b', str(html_source)):
            response = True
        elif re.search(r'\bAdd To Cart\b', str(html_source)):
            response = True
        
        if site == "geminicollectibles":
            return not response
        
        return response

    def out_of_stock(self, site, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all(HTML_OBJ[site]["type"],
                                    HTML_OBJ[site]["filter"])
        if re.search(r'\bOut of stock\b', str(html_source)):
            return False

        return True

def start(bot, update):
    """Send a message when the command /start is issued."""
    global THREAD_ALIVE
    THREAD_ALIVE = True
    update.message.reply_text('Starting bot search.')
    
def stop(bot, update):
    """Send a message when the command /stop is issued."""
    global THREAD_ALIVE
    THREAD_ALIVE = False
    update.message.reply_text('Stopping bot search.')

def add(bot, update):
    """Send a message when the command /add is issued."""  
    if not len(update.message.text.split()) == 2:
        logger.error('Wrong number of parameters passed.')
        update.message.reply_text('Wrong number of parameters passed.')

    if not validators.url(update.message.text.split()[1]):
        logger.error('URL exception {0}'.format(update.message.text.split()[1]))
        update.message.reply_text('URL exception {0}'.format(update.message.text.split()[1]))

    parsed = urlparse(update.message.text.split()[1])
    store = parsed.netloc.split('.')[-2]
    
    SEM.acquire()
    with open('pops.json') as data_file:
        funkopop_links = json.load(data_file)
    SEM.release()
    
    funkopop_links.append({"store": store,
                           "url": update.message.text.split()[1]})

    SEM.acquire()
    with open('pops.json', 'w') as outfile:
        json.dump(funkopop_links, outfile, sort_keys=True, indent=4, separators=(',', ': '))
    SEM.release()
    
    update.message.reply_text('Added entry into bot search.')

def delete(bot, update):
    """Send a message when the command /delete is issued."""    
    SEM.acquire()
    with open('pops.json') as data_file:
        funkopop_links = json.load(data_file)
    SEM.release()

    new_list = []
    for idx, elem in enumerate(funkopop_links):
        if not elem["url"] == update.message.text.split()[1]:
            new_list.append(elem)

    SEM.acquire()
    with open('pops.json', 'w') as outfile:
        json.dump(new_list, outfile, sort_keys=True, indent=4, separators=(',', ': '))
    SEM.release()

    update.message.reply_text('Deleted entry in bot search.')

def list(bot, update):
    """Send a message when the command /list is issued."""    
    SEM.acquire()
    with open('pops.json') as data_file:
        funkopop_links = json.load(data_file)
    SEM.release()

    if not funkopop_links:
        update.message.reply_text('No entries in search.')
    
    for elem in funkopop_links:
        update.message.reply_text(elem["url"])

def help(bot, update):
    """Send a message when the command /help is issued."""
    update.message.reply_text("Don't ask for help")


def error(bot, update, error):
    """Log Errors caused by Updates."""
    logger.error('Update "%s" caused error "%s"', update, error)

def startfunc():
    stkobj = StoreStock()
    stkobj.pop_search()

def main():
    """Start the bot."""
    t = Thread(target=startfunc)
    t.start()

    # Get the dispatcher to register handlers
    dp = UPDATER.dispatcher

    # on different commands - answer in Telegram
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler('add', add))
    dp.add_handler(CommandHandler('list', list))
    dp.add_handler(CommandHandler('delete', delete))
    dp.add_handler(CommandHandler('stop', stop))
    dp.add_handler(CommandHandler("help", help))

    # log all errors
    dp.add_error_handler(error)

    # Start the Bot
    UPDATER.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    UPDATER.idle()

if __name__ == '__main__':
    main()
