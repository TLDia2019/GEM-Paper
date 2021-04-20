"""
Generate list of word embedding vectors for all entries of the given Knowledge Graph
"""
__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

import os
import pickle
import numpy as np
from model_request import ModelRequest
from graphdb_handler import GraphDBHandler


class GEMsim:
    """ ;) """

    def __init__(self, min_sim=-1.0, model_request=None, graphdb=None):
        self._model_request = model_request
        self._graphdb = graphdb
        self.min_sim = min_sim

        if self._model_request is None:
            self._model_request = ModelRequest()  # FastText request service

        if self._graphdb is None:
            self._graphdb = GraphDBHandler()  # GraphDB handler

        self.wv = None
        self.idx2term = None
        self.term2idx = None
        self.term2record = None
        self._load_data()

    @staticmethod
    def _dummy_res(records, term):
        bindings = []
        for record in records:
            tmp = {"record": {
                "type": "uri",
                "value": "https://www.minds-medical.de/ontologies/tldia#" + str(record)
                }, "termName": {
                "type": "string",
                "value": term
            }}
            bindings.append(tmp)

        query_result = {
            "head": {"vars": []},
            "results": {"bindings": bindings}
        }
        return query_result

    def _load_data(self):
        data = pickle.load(open(os.path.join("resources", "kg_vec_data.pkl"), "rb"))
        self.wv = data["wv"]
        self.idx2term = data["idx2term"]
        self.term2idx = data["term2idx"]
        self.term2record = data["term2record"]

    def cosine_sim(self, word, topn=None):
        word_vector = self._model_request.wv(word)
        word_vector = np.array(word_vector)
        all_keys = []

        if word in self.term2idx:
            all_keys = [self.term2idx[word]]

        product = np.dot(self.wv, word_vector)

        if topn is None:
            topn = product.size - 1

        x = np.asarray(product)
        x = -x  # "reverse"
        most_extreme = np.argpartition(x, topn)[:topn]
        best = most_extreme.take(np.argsort(x.take(most_extreme)))  # resort topn into order

        result = [
            (self.idx2term[sim], float(product[sim]))
            for sim in best if sim not in all_keys and float(product[sim]) > self.min_sim
        ]

        return result

    def find_record(self, term, best=False, min_sim=None):
        if min_sim is not None:
            self.min_sim = float(min_sim)

        similarities = self.cosine_sim(term)
        res = []
        for term, sim in similarities:
            rec = self.term2record[term]
            rec = self._dummy_res(rec, term)
            tmp_res = (term, sim, rec)

            if best:
                return tmp_res

            res.append(tmp_res)

        return res


if __name__ == "__main__":
    gem = GEMsim(min_sim=0.75)

    test_words = ["Calcimycin", "Aspirin", "Hüftknochen"]
    for tw in test_words:
        recs = gem.find_record(tw)
        print(recs)
