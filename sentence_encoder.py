""" Sentence Encoder """

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

from typing import List
import configparser
import os

import nltk
import numpy as np


config = configparser.ConfigParser()
config.read("config.ini")
conf = config["ONTOLOGY_MAPPER"]

stop_word_file = open(os.path.join(conf.get("resources_dir"), conf.get("stopwords_data")), "r")
stop_words = stop_word_file.read().split("\n")


def compute_cosine_similarity(encoded_message_one, encoded_message_two):
    dot_product = np.dot(encoded_message_one, encoded_message_two)
    mag_i = np.sqrt(np.dot(encoded_message_one, encoded_message_one))
    mag_j = np.sqrt(np.dot(encoded_message_two, encoded_message_two))

    cos_theta = dot_product / (mag_i * mag_j)

    return cos_theta


def find_best_match(encoded_sentence, encoded_possible_trees):
    highest_index = None
    highest_sim = -1
    index = 0
    for possible_tree_entry in encoded_possible_trees:
        cos_sim = compute_cosine_similarity(encoded_sentence[0], possible_tree_entry)
        if cos_sim > highest_sim:
            highest_sim = cos_sim
            highest_index = index
        index += 1

    return highest_index, highest_sim


def tokenize_sentence(sentence: str) -> List[str]:
    """
    Tokenize sentence with NLTK tokenizer and remove stopwords
    Args:
        sentence: str to be tokenized

    Returns:
        list of str, the tokenized sentence without stopwords
    """
    tokenized_sentence = nltk.tokenize.word_tokenize(sentence, language='german')
    tokenized_sentence = [w for w in tokenized_sentence if not w.lower() in stop_words]

    return tokenized_sentence


def find_best_n_similarity_match(sentence: str, possible_tree: dict, model_request):
    tokenized_sentence = tokenize_sentence(sentence)
    tokenized_sentence_no_punct = list(filter(lambda t: "," not in t and "." not in t, tokenized_sentence))

    all_similarities = []
    best_record = None
    highest_sim = -1

    for possible_entry in possible_tree:
        tree_terms = possible_tree[possible_entry].split(", ")
        n_sim = model_request.n_similarity(tree_terms, tokenized_sentence_no_punct)

        all_similarities.append((str(n_sim), possible_entry, possible_tree[possible_entry]))

        if n_sim > highest_sim:
            highest_sim = n_sim
            best_record = possible_entry

    return best_record, highest_sim, all_similarities
