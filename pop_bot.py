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

# Create the EventHandler and pass it your bot's token.
UPDATER = Updater(os.environ['TELEGRAM_TOKEN'])

class StoreStock(object):
    def check_funko(self, site, url):
        global TIMEOUT

        logger.warning('Checking {0}'.format("Checking: " + site + " " + url))
    
        if site == 'hottopic':
            status = self.hottopic_stock(url)
        elif site == 'boxlunch':
            status = self.boxlunch_stock(url)
        elif site == 'walmart':
            status = self.walmart_stock(url)
        elif site == 'barnesandnoble':
            status = self.barnesandnoble_stock(url)
        elif site == 'gamestop':
            status = self.gamestop_stock(url)
        elif site == 'blizzard':
            status = self.blizzard_stock(url)
        else:
            status = False
    
        if status:
            msg = site + " - In Stock: " + ":\n" + url
            UPDATER.bot.send_message(chat_id=os.environ['TELEGRAM_CHATID'],
                                          text=msg)
            url_md5 = hashlib.md5(url.encode('utf-8')).hexdigest()
            TIMEOUT[url_md5] = datetime.today().date()
            logger.warning('Timeout Set: {0}'.format(url_md5))


    def pop_search(self, sleep_interval=5):
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
                    if not url_md5 in TIMEOUT:
                        self.check_funko(funko['store'], funko['url'])
                    elif url_md5 in TIMEOUT and TIMEOUT[url_md5] < datetime.today().date():
                        if datetime.now().hour > 7:
                            self.check_funko(funko['store'], funko['url'])
        
            time.sleep(sleep_interval)

    def url_to_html(self, url):
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; '
                   'Intel Mac OS X 10_10_1)'
                   ' AppleWebKit/537.36 (KHTML, like Gecko)'
                   ' Chrome/39.0.2171.95 Safari/537.36'}

        r = requests.get(url, headers=headers)
        return BeautifulSoup(r.text, 'html.parser')

    def hottopic_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all("div",
                                    {"class": "presale-pdp viewpage-pdp"})
        return re.search(r'\bIn Stock\b', str(html_source))

    def boxlunch_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all("div",
                                    {"class": "availability-msg"})
        return re.search(r'\bIn Stock\b', str(html_source))

    def walmart_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all(
            "div", {"class": "prod-CallToActionSection hf-BotRow"})
        return re.search(r'\bAdd to Cart\b', str(html_source))

    def barnesandnoble_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all("section", {"id": "skuSelection"})
        return re.search(r'\bAdd to Cart\b', str(html_source))

    def gamestop_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all("div", {"class": "button qq"})
        return re.search(r'\bAdd to Cart\b', str(html_source))

    def blizzard_stock(self, url):
        soup = self.url_to_html(url)
        html_source = soup.find_all("div",
                                    {"class": "columns small-12 hide-for-small-only"})
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
        logger.warning('Wrong number of parameters passed.')
        update.message.reply_text('Wrong number of parameters passed.')

    if not validators.url(update.message.text.split()[1]):
        logger.warning('URL exception %s.'.format(update.message.text.split()[1]))
        update.message.reply_text('URL exception %s.'.format(update.message.text.split()[1]))

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
    logger.warning('Update "%s" caused error "%s"', update, error)


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
