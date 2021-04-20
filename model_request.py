"""
This is an interface for the model server.
"""

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

import logging
import configparser
import requests
import urllib.parse

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read("config.ini")
conf = config["ONTOLOGY_MAPPER"]

FAST_TEXT_PROTOCOL = conf.get("fasttext_protocol")
FAST_TEXT_HOST = conf.get("fasttext_host")
FAST_TEXT_PORT = conf.get("fasttext_port")
FAST_TEXT_ADDR = None
if FAST_TEXT_PORT is None:
    FAST_TEXT_ADDR = FAST_TEXT_PROTOCOL + FAST_TEXT_HOST + "/"
else:
    FAST_TEXT_ADDR = FAST_TEXT_PROTOCOL + FAST_TEXT_HOST + ":" + str(FAST_TEXT_PORT) + "/"


class ModelRequest:
    def __init__(self):
        self.base_url = FAST_TEXT_ADDR

    def in_vocab(self, word: str = "") -> bool:
        """
        Check if the word exists in the vocabulary of the model.
        On similarity checks, the fasttext model avoids out of vocabulary (OOV) issues by
        comparing n-grams. That doesn't mean that "asldkalksdja2" exists in the vocabulary.
        You can check that here.
        :param word: Word to check if exists in vocab
        :return: True if exists, false otherwise
        """
        word = urllib.parse.quote(word, safe="")
        request_url = self.base_url + "in_vocab/" + word
        response = requests.get(url=request_url)
        try:
            return bool(response.json())
        except Exception:
            return False

    def n_similarity(self, reference: list = None, word: list = None) -> float:
        if not type(reference) is list:
            reference = [reference]

        if not type(word) is list:
            word = [word]

        data = {
            "ws1": reference,
            "ws2": word
        }
        request_url = self.base_url + "n_similarity"

        return self.req(request_url, data=data)

    def most_similar(self, positive: list = None, top_n: int = 1):
        if not type(positive) is list:
            positive = [positive]

        data = {
            "positive": positive,
            "topn": top_n
        }

        request_url = self.base_url + "most_similar"

        return self.req(request_url, data=data)

    def similarity(self, base_word, lookup):
        data = {
            "w1": base_word,
            "w2": lookup
        }

        request_url = self.base_url + "similarity"
        return self.req(request_url, data=data)

    def wv(self, word):
        word = urllib.parse.quote(word, safe="")
        request_url = self.base_url + "wv/" + word
        return self.req(request_url)

    @staticmethod
    def req(request_url, data=None):
        if data is not None:
            response = requests.post(url=request_url, json=data)
        else:
            response = requests.get(url=request_url)
        try:
            return response.json()
        except Exception as e:
            print(e)
            return False
