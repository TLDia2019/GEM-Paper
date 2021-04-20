""" GraphDB Handler """

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

import random
import configparser
import json
import time
import urllib.error as urlerror

from SPARQLWrapper import SPARQLWrapper, JSON, POST


def string_variants(string):
    res = [
        string,
        string.lower(),
        string.upper(),
        string.capitalize(),
        string.casefold(),
        string.title(),
        string.swapcase()
    ]

    return set(res)


def escape(term):
    return json.dumps(term)


def mesh_str_values(variants):
    search_str = "^^mesh:string ".join(escape(v) for v in variants) + "^^mesh:string"
    search_str += " ".join(escape(v) for v in variants)
    return search_str


class GraphDBHandler:

    def __init__(self):
        self._conf = dict()
        self._set_conf_from_config()
        self._sparql = None

        self._prefix = """
                        PREFIX mesh: <https://www.minds-medical.de/ontologies/tldia#>
                        PREFIX germanet: <https://www.minds-medical.de/ontologies/tldia_gn#>
                        PREFIX owl: <http://www.w3.org/2002/07/owl#>
                        PREFIX jsfn:<http://www.ontotext.com/js#>
                        PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                        PREFIX mesh_entity: <https://www.minds-medical.de/ontologies/tldia>
                        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                       """

        self._connection_retries = 0
        self._connection_retry_sleep = 1
        self._connection_max_retries = 10
        self._connection_timeout = 60  # in seconds

        self.init_sparql()

    def _set_conf_from_config(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        conf = config["ONTOLOGY_MAPPER"]
        self._conf = dict(conf.items())

    def set_conf_values(self, values: dict):
        self._conf.update(values)

    def init_sparql(self):
        self._sparql = SPARQLWrapper(f"{self._conf.get('graphdb_repo_url')}{self._conf.get('graphdb_repo_name')}")
        self._sparql.setCredentials(self._conf.get("graphdb_user"), self._conf.get("graphdb_passwd"))
        self._sparql.setTimeout(self._connection_timeout)

        self._sparql.setReturnFormat(JSON)  # select the return format (e.g. XML, JSON etc...)

    def query_ontology(self, query):
        res = None
        while res is None:
            try:
                self._sparql.setQuery(query)
                res = self._sparql.query().convert()
            except Exception as e:
                if self._connection_retries < self._connection_max_retries:
                    self._connection_retries += 1
                    print(f"SPARQLConnection Error. Retry {self._connection_retries} of {self._connection_max_retries}")
                    if urlerror.URLError == type(e):
                        time.sleep(60)
                    else:
                        time.sleep(self._connection_retry_sleep)
                    continue
                else:
                    raise

        self._connection_retries = 0
        return res

    def insert_into_ontology(self, query):
        sparql = SPARQLWrapper(self._conf.get("graphdb_repo_url") +
                               self._conf.get("graphdb_repo_name") +
                               "/statements")

        sparql.setCredentials(self._conf.get("graphdb_user"), self._conf.get("graphdb_passwd"))
        if self._conf.get("graphdb_auth_token") is not None:
            sparql.addCustomHttpHeader('Authorization', f'Bearer {self._conf.get("graphdb_auth_token")}')

        # select the return format (e.g. XML, JSON etc...)
        sparql.setQuery(query)
        sparql.setMethod(POST)
        results = sparql.query()

        return results

    def get_record_using_exact_matching(self, term):
        term_variants = string_variants(term)
        term_variants = mesh_str_values(term_variants)

        query = self._prefix + \
            """
            SELECT ?record ?termName{
                ?record rdf:type mesh:Record .
                ?record mesh_entity:hasConcept ?concept .
                ?concept mesh_entity:hasTerm ?term .
                ?term mesh_entity:hasTermName ?termName .
                VALUES ?termName {""" + term_variants + """}
            }
            """

        return self.query_ontology(query)

    # def get_record_using_exact_matching_for_mesh_translated_terms(self, term):
    #     term_variants = string_variants(term)
    #     term_variants = mesh_str_values(term_variants)
    #
    #     query = self._prefix + \
    #         """
    #         SELECT ?record ?termName WHERE
    #         {
    #             {
    #                 SELECT * {
    #                     ?record rdf:type mesh:Record .
    #                     ?record mesh:has_artificial_translated_preffered_terms ?translated_terms .
    #                     ?translated_terms mesh:translated_preffered_term ?termName .
    #                     VALUES ?termName {""" + term_variants + """}
    #                 }
    #             }
    #             UNION
    #             {
    #                 SELECT * {
    #                     ?record rdf:type mesh:Record .
    #                     ?record mesh:has_artificial_translated_narrower_terms ?translated_terms .
    #                     ?translated_terms mesh:translated_narrower_term ?termName .
    #                     VALUES ?termName {""" + term_variants + """}
    #                 }
    #             }
    #         }
    #         """
    #     return self.query_ontology(query)

    def get_id_from_mesh_term(self, term):
        term_variants = string_variants(term)
        term_variants = mesh_str_values(term_variants)

        query = self._prefix + \
            f"""
            SELECT ?term {{
                ?concept mesh_entity:hasTerm ?term .
                ?term mesh_entity:hasTermName ?termName .
                VALUES ?termName {{{term_variants}}}
            }}
            """

        return self.query_ontology(query)

    def insert_specific_term_into_mesh(self, term, term_id):
        query = self._prefix + \
            f"""
            INSERT DATA{{
                mesh:{term_id} mesh_entity:hasTermName "{term}" .
            }}
            """
        return self.insert_into_ontology(query)

    def delete_specific_term_from_mesh(self, term, term_id):
        query = self._prefix + \
            f"""
            DELETE {{
              mesh:{term_id} mesh_entity:hasTermName ?termName .
            }}
            WHERE {{
                {{
                SELECT ?termName {{
                    mesh:{term_id} mesh_entity:hasTermName ?termName .
                    FILTER (lcase(str(?termName)) = lcase("{term}"))
                }}
              }}
            }}
            """
        return self.insert_into_ontology(query)

    def get_all_index_listings_of_a_mesh_record(self, record_id):
        query = self._prefix + \
            f"""
            select ?index where {{
                mesh:{record_id} mesh_entity:hasPreviousIndexing ?index .
            }}
            """
        return self.query_ontology(query)

    def get_term_from_mesh_group(self, group_name):
        query = self._prefix + \
            f"""
            select ?gerName where {{
                ?record mesh_entity:hasType ?index ;
                        mesh_entity:hasNameGer ?gerName .
                FILTER (?index = "{group_name}"^^mesh:string)
            }}
            """
        return self.query_ontology(query)

    def get_record_id_from_mesh_listing_index(self, listing_index):
        query = self._prefix + \
            f"""
            select * where {{
                ?record mesh_entity:hasPreviousIndexing ?index .
                FILTER (?index = "{listing_index}"^^mesh:string)
            }}
            """
        return self.query_ontology(query)

    def get_record_using_fuzzy_matching(self, term, method):
        threshold = 0
        comparison_sign = ">"

        if method == self._conf.get("fuzzy_method_jaro_winkler"):
            threshold = self._conf.get("min_jaro_winkler_ratio")
            comparison_sign = ">"
        elif method == self._conf.get("fuzzy_method_norm_levensthein_punished"):
            threshold = self._conf.get("min_norm_levensthein_ratio")
            comparison_sign = ">"
        elif method == self._conf.get("fuzzy_method_norm_levensthein"):
            threshold = self._conf.get("min_norm_levensthein_ratio")
            comparison_sign = ">"
        elif method == self._conf.get("fuzzy_method_levensthein"):
            comparison_sign = "<="
            if len(term) >= 16:
                threshold = 3
            elif len(term) >= 11:
                threshold = 2
            else:
                threshold = 1

        query = self._prefix + \
            """
            SELECT ?record ?termName {
                ?record rdf:type mesh:Record ;
                        mesh_entity:hasConcept ?concept .
                ?concept mesh_entity:hasTerm ?term .
                ?term mesh_entity:hasTermName ?termName ;
                      mesh_entity:hasThesaurusId ?thId . 
                FILTER (jsfn:"""+method+"""(lcase(str(?termName)), lcase('""" + term + """')) """ + \
            comparison_sign + """ """ + str(threshold) + """) .
                FILTER (?thId = "German Thesaurus"^^mesh:string)
            }
            """

        return self.query_ontology(query)

    def get_records_with_artificial_relation(self, term):
        relation_iri = "mesh"
        relation_name = "hasNameGer"
        term = escape(term)

        query = self._prefix + \
            """
            SELECT ?record ?relation ?termName WHERE
            {
                {
                    SELECT ?record ?relation ?termName WHERE {
                        ?record """ + relation_iri + """:""" + relation_name + """ ?termName .
                        ?record """ + relation_iri + """:artificial_similar_term  ?searchTerm .
                        ?record ?relation ?termName .
                        FILTER (lcase(str(?searchTerm)) = lcase(""" + term + """))
                    }
                }
                UNION
                {
                    SELECT ?record ?relation ?termName WHERE {
                        ?record """ + relation_iri + """:""" + relation_name + """ ?termName .
                        ?record """ + relation_iri + """:artificial_compound_from  ?searchTerm .
                        ?record ?relation ?termName .
                        FILTER (lcase(str(?searchTerm)) = lcase(""" + term + """))
                    }
                }
            }
            """
        return self.query_ontology(query)

    # # AT(P|N|B)T stands for artificial translated (preffered | narrower | broader) terms
    # def insert_artificial_translated_mesh_term(self, target_id, translations, translation_type):
    #     list_valid_types = ["preffered", "narrower", "broader"]
    #     if translation_type in list_valid_types and len(translations) > 0:
    #         translation_sparql = ""
    #         for translation in translations:
    #             if '"' in translation:
    #                 continue
    #             translation_sparql += \
    #                 f"""
    #                 mesh:{target_id}_AT{translation_type[0:1].upper()}T
    #                 mesh:translated_{translation_type}_term \"{translation}\" .\n
    #                 """
    #
    #         query = self._prefix + \
    #             f"""
    #             INSERT DATA{{
    #                 mesh:{target_id} rdf:type mesh:Record .
    #                 mesh:{target_id} mesh:has_artificial_translated_{translation_type}_terms
    #                 mesh:{target_id}_AT{translation_type[0:1].upper()}T .
    #                 {translation_sparql}
    #             }}
    #             """
    #
    #         return self.insert_into_ontology(query)
    #     else:
    #         return None

    def get_mesh_terms_for_record(self, record_id):
        query = self._prefix + \
            f"""
            SELECT ?record ?term ?termName
            FROM <http://www.ontotext.com/explicit>
            {{
                ?record rdf:type mesh:{record_id} .
                ?record mesh_entity:hasConcept ?concept .
                ?concept mesh_entity:hasTerm ?term .
                ?term mesh_entity:hasTermName ?termName .
            }}
            """
        return self.query_ontology(query)

    def get_parent_record_id_from_mesh_record(self, child_record_id):
        query = self._prefix + \
            f"""
            SELECT ?childRecord ?parentRecord
            FROM <http://www.ontotext.com/explicit>
            {{
                ?childRecord rdf:type mesh:{child_record_id} .
                ?childRecord rdfs:subClassOf ?parentRecord .
            }}
            """
        return self.query_ontology(query)

    def remove_uri(self, value):
        return value.replace(self._conf.get("mesh_uri"), "")

    def find_best_place_for_word_mesh(self, start_record_id, word):
        iterations = 0
        record_ids = [start_record_id]
        walk_finished = False
        walk = ""
        while not walk_finished:
            iterations += 1

            if iterations == 6:
                walk_finished = True

            max_range = 2
            german_mesh_terms = []

            for record_id in record_ids:
                term_results = self.get_mesh_terms_for_record(record_id)
                term_results = self.filter_mesh_onto_query_for_german_terms(term_results)
                for binding in term_results["results"]["bindings"]:
                    german_mesh_terms.append(binding["termName"]["value"])

            if word in german_mesh_terms:
                german_mesh_terms.remove(word)

            not_used_words = [pos_word
                              for pos_word in german_mesh_terms
                              if word.lower() in pos_word.lower()]

            german_mesh_terms = [pos_allowed_word
                                 for pos_allowed_word in german_mesh_terms
                                 if pos_allowed_word not in not_used_words]
            random.shuffle(german_mesh_terms)
            german_mesh_terms += not_used_words

            if len(german_mesh_terms) < max_range:
                max_range = len(german_mesh_terms)

            for i in range(0, max_range):
                walk += german_mesh_terms[i] + ", "

            # parent_results = get_parent_record_id_from_mesh_record(record_id)
            # record_id = remove_mesh_uri(parent_results["results"]["bindings"][0]["parentRecord"]["value"])

            new_record_ids = []
            for record_id in record_ids:
                parent_results = self.get_parent_record_id_from_mesh_record(record_id)
                new_record_ids = new_record_ids + [self.remove_uri(binding["parentRecord"]["value"])
                                                   for binding in parent_results["results"]["bindings"]]
            record_ids = new_record_ids

            if len(walk.split(", ")) > 5:
                walk_finished = True
                walk = walk[0: walk.rfind(",")]

        return walk

    def find_best_place_for_word(self, start_record_id, word):
        return self.find_best_place_for_word_mesh(start_record_id, word)

    def generate_path_comparison_walk_mesh_record_id_list(self, record_id_list):
        walk = []
        i = 0
        while True:
            if i > len(record_id_list) - 1:
                break

            else:
                max_range = 2
                german_mesh_terms = []

                record_id = record_id_list[i]
                if len(record_id) == 1:
                    term_results = self.get_term_from_mesh_group(record_id)
                    for binding in term_results["results"]["bindings"]:
                        german_mesh_terms.append(binding["gerName"]["value"])

                else:
                    term_results = self.get_mesh_terms_for_record(record_id)
                    term_results = self.filter_mesh_onto_query_for_german_terms(term_results)

                    for binding in term_results["results"]["bindings"]:
                        german_mesh_terms.append(binding["termName"]["value"])

                random.shuffle(german_mesh_terms)
                max_range = min(len(german_mesh_terms), max_range)
                walk += german_mesh_terms[:max_range]
                i += 1

                if len(walk) > 7:
                    break

        walk = ", ".join(walk)
        return walk

    def filter_mesh_onto_query_for_german_terms(self, query_result):
        query_result["results"]["bindings"] = [binding
                                               for binding in query_result["results"]["bindings"]
                                               if "ger" in self.remove_uri(binding["term"]["value"])]
        return query_result
