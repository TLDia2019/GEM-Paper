""" Term Mapper """

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

from typing import List, Any, Tuple
import configparser
import os

from nltk.corpus import stopwords
import requests
import spacy

from graphdb_handler import GraphDBHandler
from kg_vec_calc import GEMsim
from model_request import ModelRequest
from sentence_encoder import find_best_n_similarity_match


class TermMapper:
    """
    Attempting to map a given term the best way possible into a given knowledge graph.
    """

    def __init__(self):
        self._conf = dict()
        self._set_conf_from_config()

        self._base_word = None
        self._context_sentence = None

        lemma_data_path = os.path.join(self._conf.get("resources_dir"), self._conf.get("lemma_data"))
        self.lemma_data = self._load_lemma_data(lemma_data_path)
        self.stop_words = stopwords.words('german')
        self.model_request = ModelRequest()  # FastText request service
        self.graphdb = GraphDBHandler()  # GraphDB handler
        self.GEMsim = GEMsim()
        # python -m spacy download de_core_news_lg
        # if missing...
        self.nlp = spacy.load("de_core_news_lg")

        self.direct_found_terms = []
        self.ft_found_terms = []
        self.compound_found_terms = []
        self.sorted_ft_findings = []
        self.translated_found_terms = []
        self.artificial_found_terms = []
        # self.all_found_terms = []
        self.sorted_gem_findings = []
        self.gem_found_terms = []

        self.finding_list = []
        self.all_findings_list = []
        self.already_tested = dict()

    def _set_conf_from_config(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        conf = config["ONTOLOGY_MAPPER"]
        self._conf = dict(conf.items())

    def set_conf_values(self, values: dict):
        self._conf.update(values)
        self.graphdb.set_conf_values(values)

    @property
    def context_sentence(self) -> str:
        return self._context_sentence

    @context_sentence.setter
    def context_sentence(self, sentence: str) -> None:
        if type(sentence) is not str or len(sentence) == 0:
            raise ValueError
        self._context_sentence = sentence

    @property
    def base_word(self) -> str:
        return self._base_word

    @base_word.setter
    def base_word(self, base_word: str) -> None:
        if type(base_word) is not str or len(base_word) == 0:
            raise ValueError
        self._base_word = base_word

    @staticmethod
    def _load_lemma_data(path_to_lemma_file):
        """
        Load the lemma data from a file
        :return: None
        """
        with open(path_to_lemma_file, 'r', encoding="utf-8") as lemma_file:
            tmp_lemma_data = []
            for line in lemma_file:
                line = line.strip("\n")
                tmp_lemma_data.append(line)
                if "ß" in line:
                    line = line.replace(u'ß', 'ss')
                    tmp_lemma_data.append(line)
        return set(tmp_lemma_data)

    @staticmethod
    def match_found(result_data):
        """ Returns true if a match was found """
        return True if len(result_data["results"]["bindings"]) > 0 else False

    @staticmethod
    def get_record_value(record_entry, key):
        """ Extracts value from record and removes leading prefix/URI"""
        value = record_entry[key]["value"]
        return value[value.rfind("#") + 1:]

    def decompound(self, term: str) -> List[str]:
        """
        Decompound given term

        Args:
            term: str to decompound

        Returns:
            List of stems or empty list if term equals only stem
        """
        res = requests.get(self._conf.get("secos_server_url") + term)
        decoded = res.content.decode().strip()
        if decoded == term:
            return []

        stems = decoded.replace("'", "").strip().split(" ")
        return stems

    def split_word_in_all_comps(self, term: str) -> List[str]:
        """
        Split given term in all possible stems

        Args:
            term: str to decompound in all possible stems

        Returns:
            List of all possible stems of given term
        """
        all_stems = []

        words = term.split()
        for word in words:
            stems = self.decompound(word)
            all_stems.extend(stems)

            for stem in stems:
                more_stems = self.split_word_in_all_comps(stem)
                all_stems.extend(more_stems)

        return all_stems

    def modify_and_test_word(self, cur_finding_list, term, finding_type):
        modifications = self.generate_transitional_modifications(word=term)

        for mod_as_token in modifications:
            mod = str(mod_as_token)

            result = self.graphdb.get_record_using_exact_matching(mod)

            if self.match_found(result):
                threshold_reached, result, cor_walk = self.check_match_results(result, self.base_word)
                if threshold_reached:
                    self.save_finding(cur_finding_list, term, result, cor_walk, finding_type)
                    return True

        return False

    def sort_ft_similar_word_findings(self, ft_found_terms):
        """ Legacy Code

        For multiple matches in FT, sort based on similarity to base word

        """
        similarity_scores = []
        for entry in ft_found_terms:
            corresponding_term = entry["corresponding_term"]

            similarity = self.model_request.similarity(self.base_word, corresponding_term)
            similarity_scores.append((entry, similarity))

        similarity_scores.sort(reverse=True, key=lambda tup: tup[1])

        return similarity_scores

    def save_finding(self, cur_finding_list: List = None,
                     term: str = None,
                     query_result: dict = None,
                     cor_walk: Any = None,
                     finding_type: str = None) -> None:
        """
        Save the (currently) best finding in two lists.

        Args:
            cur_finding_list: The list, the current match should be saved in (e.g. list of direct matches)
            term: The term that was used for lookup
            query_result: Return value of the search in GraphDB
            cor_walk: The corresponding best walk (path) for the term
            finding_type: Type the led to that finding

        Returns:
            None
        """

        current_finding_ids = [finding["corresponding_id"] for finding in cur_finding_list]

        for record_entry in query_result["results"]["bindings"]:
            mesh_record_id = self.get_record_value(record_entry, "record")

            if mesh_record_id in current_finding_ids:
                print("record id already in list")
            else:
                entry = {
                    "base_word": self.base_word,
                    "queried_term": term,
                    "corresponding_id": mesh_record_id,
                    "corresponding_term": self.get_record_value(record_entry, "termName"),
                    "cor_walk": cor_walk,
                    "finding_type": finding_type,
                    "context_sentence": self.context_sentence
                }

                best_abstraction_path, all_similarities = self.calculate_best_mesh_abstraction_path(mesh_record_id)
                entry["best_abstraction_path"] = best_abstraction_path
                entry["all_abstraction_path_similarities"] = all_similarities

                cur_finding_list.append(entry)
                self.all_findings_list.append(entry)

    def split_word_using_simple_dict_search(self, base_word: str):
        """ Find Partial Lemma in Base Word

        A similarity threshold must be reached to be an accepted sub-lemma

        Args:
            base_word: str that should be checked for containing lemmas

        Returns:
            List of lemmas found in base word
        """
        lemmas_in_base_word = []
        for lemma in self.lemma_data:

            if lemma.lower() in base_word.lower():
                if self.model_request.similarity(base_word, lemma) > 0.5:
                    lemmas_in_base_word.append({
                        "word": lemma,
                        "start_index": base_word.lower().find(lemma.lower()),
                        "end_index": base_word.lower().find(lemma.lower()) + len(lemma)
                    })

        return lemmas_in_base_word

    def check_match_results(self, result, base_word=None):
        walks = {}

        if base_word is None:
            base_word = self.base_word

        if type(result) == dict and "results" in result:
            records = [self.graphdb.remove_uri(binding["record"]["value"])
                       for binding
                       in result["results"]["bindings"]]
        else:
            records = result

        for record in records:
            if record not in self.already_tested:
                best_position = self.graphdb.find_best_place_for_word(record, base_word)
                walks[record] = best_position
                self.already_tested[record] = best_position
            else:
                walks[record] = self.already_tested[record]

        return self.calculate_best_fitting_word_group(result, walks)

    def calculate_best_fitting_word_group(self, result, walks):  # noqa: C901
        min_random_walk_sim_threshold = float(self._conf.get("min_random_walk_sim_threshold"))
        min_average_ft_sim_of_walk = float(self._conf.get("min_average_ft_sim_of_walk"))

        best_synset, highest_sim, all_similarities = find_best_n_similarity_match(self.context_sentence, walks,
                                                                                  self.model_request)
        if best_synset is not None:
            walk_split = walks[best_synset].split(", ")
            average_sim = 0
            iteration_count = 0

            for split in walk_split:
                if split == "":
                    break
                average_sim += self.model_request.similarity(self.base_word, split)
                iteration_count += 1
                if iteration_count == 3:
                    break

            if iteration_count == 0:
                average_sim = 99
            else:
                average_sim = average_sim / iteration_count

        else:
            average_sim = 99

        if highest_sim > min_random_walk_sim_threshold and average_sim > min_average_ft_sim_of_walk:
            best_binding = []
            if result is not None:
                for binding in result["results"]["bindings"]:
                    if best_synset in binding["record"]["value"]:
                        best_binding.append(binding)
                        break
                result["results"]["bindings"] = best_binding
            else:
                result = all_similarities

            return True, result, walks[best_synset]

        return False, None, None

    def calculate_best_mesh_abstraction_path(self, record_id: str) -> Tuple:
        """
        If multiple abstractions paths are available for a record, try to find the best matching one.

        Args:
            record_id: str MeSH Record ID

        Returns:
            Tuple of best abstraction path and all similarity measures
        """
        base_indexes = {}
        # get all abstractions paths from recordID
        result = self.graphdb.get_all_index_listings_of_a_mesh_record(record_id)
        for binding in result["results"]["bindings"]:
            base_indexes[binding["index"]["value"]] = []

        for base_index in base_indexes:
            root_index_found = False
            current_parent_index = base_index
            while not root_index_found:
                dot_idx = current_parent_index.rfind(".")
                if dot_idx == -1:
                    current_parent_index = current_parent_index[0:1]
                else:
                    current_parent_index = current_parent_index[:dot_idx]
                base_indexes[base_index].append(current_parent_index)
                if "." not in current_parent_index:
                    root_index_found = True

        parent_record_paths = {}
        for base_index in base_indexes:
            parent_record_paths[base_index] = []
            for parent_index in base_indexes[base_index]:
                if len(parent_index) == 1:
                    # get group name instead:
                    parent_record_paths[base_index].append(parent_index)
                    continue
                else:
                    result = self.graphdb.get_record_id_from_mesh_listing_index(parent_index)

                for binding in result["results"]["bindings"]:
                    parent_record_paths[base_index].append(self.graphdb.remove_uri(binding["record"]["value"]))

        walks = {}
        for parent_path in parent_record_paths:
            walks[parent_path] = self.graphdb.generate_path_comparison_walk_mesh_record_id_list(
                parent_record_paths[parent_path])

        threshold_reached, all_similarities, cor_walk = self.calculate_best_fitting_word_group(None, walks)
        walk_key_list = list(walks.keys())
        walk_val_list = list(walks.values())
        if cor_walk in walk_val_list:
            best_abstraction_path = walk_key_list[walk_val_list.index(cor_walk)]

            return best_abstraction_path, all_similarities

        else:
            return None, None

    def find_direct_match(self, fuzzy: bool = False):

        if fuzzy:
            finding_type = self._conf.get("FUZZY_MATCH")
            finding_list = self.direct_found_terms
            result = \
                self.graphdb.get_record_using_fuzzy_matching(self.base_word,
                                                             method=self._conf.get("fuzzy_method_norm_levensthein"))
        else:
            finding_type = self._conf.get("DIRECT")
            finding_list = self.direct_found_terms
            result = self.graphdb.get_record_using_exact_matching(self.base_word)

        if not self.match_found(result):
            return False

        threshold_reached, result, cor_walk = self.check_match_results(result)
        if threshold_reached:
            self.save_finding(finding_list, self.base_word, result, cor_walk, finding_type)

        return True

    def find_artificial_relation_match(self) -> bool:
        # 1.1
        artificial_results = self.graphdb.get_records_with_artificial_relation(self.base_word)

        if len(artificial_results["results"]["bindings"]) > 0:
            cor_walk = None
            self.save_finding(self.artificial_found_terms, self.base_word, artificial_results, cor_walk,
                              self._conf.get("ARTIFICIAL_MATCH"))
            return True

        return False

    def similar_matching(self):
        min_sim_thresh = float(self._conf.get("min_gem_sim_threshold"))
        most_similar_words = self.GEMsim.find_record(self.base_word, min_sim=min_sim_thresh)

        # iterate through the most similar word list
        match_found = False
        for similar_word, sim, record in most_similar_words:
            if not match_found:
                threshold_reached, result, cor_walk = self.check_match_results(record)
                if threshold_reached:
                    match_found = True
                    self.save_finding(self.gem_found_terms, similar_word, result,
                                      cor_walk, self._conf.get("FT_DIRECT"))

                else:
                    # 4.2 - Convert word into lemma and find exact match in ontology.
                    match_found = self.modify_and_test_word(self.gem_found_terms, similar_word,
                                                            self._conf.get("MOD_FT"))

                artificial_results = self.graphdb.get_records_with_artificial_relation(similar_word)
                if len(artificial_results["results"]["bindings"]) > 0:
                    self.save_finding(self.artificial_found_terms, similar_word, artificial_results,
                                      None, self._conf.get("ARTIFICIAL_MATCH"))

        self.sorted_gem_findings = self.sort_ft_similar_word_findings(self.gem_found_terms)

    def most_similar_matching(self):
        """
        find match using a list of the most similar words of the base word.
        for example: Nierenzellenkarzinom -> Nierenkarzinom

        Returns:
        """
        min_sim_thresh = float(self._conf.get("min_similarity_threshold"))
        most_similar_words = self.model_request.most_similar(positive=[self.base_word],
                                                             top_n=self._conf.get("max_similar_terms_threshold"))

        # iterate through the most similar word list
        match_found = False
        for similar_word, sim in most_similar_words:
            if sim > min_sim_thresh and not match_found:

                # 4.1 - find exact match in ontology.
                result = self.graphdb.get_record_using_exact_matching(similar_word)

                if self.match_found(result):
                    threshold_reached, result, cor_walk = self.check_match_results(result)
                    if threshold_reached:
                        match_found = True
                        self.save_finding(self.ft_found_terms, similar_word, result,
                                          cor_walk, self._conf.get("FT_DIRECT"))

                else:
                    # 4.2 - Convert word into lemma and find exact match in ontology.
                    match_found = self.modify_and_test_word(self.ft_found_terms, similar_word, self._conf.get("MOD_FT"))

                artificial_results = self.graphdb.get_records_with_artificial_relation(similar_word)
                if len(artificial_results["results"]["bindings"]) > 0:
                    self.save_finding(self.artificial_found_terms, similar_word, artificial_results,
                                      None, self._conf.get("ARTIFICIAL_MATCH"))

        self.sorted_ft_findings = self.sort_ft_similar_word_findings(self.ft_found_terms)

    def find_compound_match(self):
        """ 4. """
        compounds = self.split_word_in_all_comps(self.base_word)
        lowered_compounds = [compound.lower() for compound in compounds]

        dict_split_results = self.split_word_using_simple_dict_search(self.base_word)

        for dict_split in dict_split_results:
            dict_word = dict_split["word"]
            if dict_word.lower() not in lowered_compounds:
                compounds.append(dict_word)

        for compound in compounds:
            # 5.1  - look for a direct match
            result = self.graphdb.get_record_using_exact_matching(compound)
            if self.match_found(result):
                threshold_reached, result, cor_walk = self.check_match_results(result, compound)
                if threshold_reached:
                    self.save_finding(self.compound_found_terms, compound, result,
                                      cor_walk, self._conf.get("COMPOUND"))
            else:
                method = self._conf.get("fuzzy_method_norm_levensthein_punished")
                result = self.graphdb.get_record_using_fuzzy_matching(compound, method)
                if self.match_found(result):
                    threshold_reached, result, cor_walk = self.check_match_results(result, compound)
                    if threshold_reached:
                        self.save_finding(self.compound_found_terms, compound,
                                          result, cor_walk, self._conf.get("COMPOUND_FUZZY"))

                else:
                    # 5.2 - Convert word into lemma and find exact match in ontology.
                    self.modify_and_test_word(self.compound_found_terms, compound, self._conf.get("MOD_COMPOUND"))

    def _clear_result_lists(self) -> None:
        self.direct_found_terms = []
        self.sorted_ft_findings = []
        self.compound_found_terms = []
        self.artificial_found_terms = []
        self.translated_found_terms = []
        self.all_findings_list = []
        self.ft_found_terms = []
        self.already_tested = {}
        self.all_found_terms = []
        self.finding_list = []
        self.sorted_gem_findings = []
        self.gem_found_terms = []

    def find_matches(self, base_word: str, context_sentence: str):  # noqa: C901
        self.base_word = base_word
        self.context_sentence = context_sentence
        self._clear_result_lists()

        # 2 - find match using Levenshtein distance measure. Tries to ignore typos
        self.find_direct_match(fuzzy=True)

        # 3 Most Similar Matching
        self.most_similar_matching()

        # 3.1 Similar Matching
        self.similar_matching()

        # 5 - Split the base word into all compounds in order to test them
        self.find_compound_match()

        return self.direct_found_terms, self.sorted_ft_findings, self.compound_found_terms,\
            self.artificial_found_terms, self.translated_found_terms, self.sorted_gem_findings

    def generate_transitional_modifications(self, word: str = "") -> list:  # noqa: C901
        """
        Create list of possible word modifications
        :param word: The word to be modified
        :return: List of modified words
        """
        possible_modifications = []

        # Create a list of possible initial words
        word_list = [word]

        # Replace Umlaute to handle things like "H_ä_userschlucht"
        # If the first letter is an Umlaut, it is not going to be changed
        if 'ä' in word and not word[0].lower() == 'ä':
            tmp_word = word.replace(u'ä', 'a')
            word_list.append(tmp_word)

        if 'ö' in word and not word[0].lower() == 'ö':
            tmp_word = word.replace(u'ö', 'o')
            word_list.append(tmp_word)

        if 'ü' in word and not word[0].lower() == 'ü':
            tmp_word = word.replace(u'ü', 'u')
            word_list.append(tmp_word)

        for word in word_list:
            # Consider the unmodified word lowered and capitalized as possible modifications
            possible_modifications.append(word.lower())
            possible_modifications.append(word.capitalize())

            """
            M O D I F Y   W O R D S
            Noun Rules
            """
            # If not last letter is 's'
            # Remove s
            # Remove s, add e
            if word[-1:] == "s":  #
                # action = ["-s"]
                # action2 = ["-s", "+e"]
                possible_modifications.append(word[:-1].lower())
                possible_modifications.append(word[:-1].lower() + "e")

                possible_modifications.append(word[:-1].capitalize())
                possible_modifications.append(word[:-1].capitalize() + "e")

            # If not last letter is 'e'
            # Add e
            if not word[-1:] == "e":  # Kirch|turm (Kirch) -> (Kirche)
                # action = ["+e"]
                possible_modifications.append(word.lower() + "e")
                possible_modifications.append(word.capitalize() + "e")

            # If not last letter is 'n'
            # Add n
            if word[-1:] == "n":  # Hasen|braten (Hasen) -> (Hase)
                # action = ["-n"]
                possible_modifications.append(word[:-1].lower())
                possible_modifications.append(word[:-1].capitalize())

            # If last letter IS 'e'
            # Remove e
            if word[-1:] == "e":  # Hunde|hütte (Hunde) -> (Hund)
                # action = ["-e"]
                possible_modifications.append(word[:-1].lower())
                possible_modifications.append(word[:-1].capitalize())

            # If word ends on "en"
            # Remove "en"
            if word[-2:] == "en":  # Taten|drang (Taten) -> (Tag)
                # action = ["-en"]
                possible_modifications.append(word[:-2].lower())
                possible_modifications.append(word[:-2].capitalize())

            # If word ends on "er"
            # Remove "er"
            if word[-2:] == "er":  # Bücher|Regal (Bücher/Bucher) -> (Büch/Buch)
                # action = ["-er"]
                possible_modifications.append(word[:-2].lower())
                possible_modifications.append(word[:-2].capitalize())

            # If word ends on "ns"
            # Remove "ns"
            if word[-2:] == "ns":  # Glaubens|frage (Glaubens) -> (Glaube)
                # action = ["-ns"]
                possible_modifications.append(word[:-2].lower())
                possible_modifications.append(word[:-2].capitalize())

            # If word ends on "ens"
            # Remove "ens"
            if word[-3:] == "ens":  # Herzens|güte (Herzens) -> (Herz)
                # action = ["-ens"]
                possible_modifications.append(word[:-3].lower())
                possible_modifications.append(word[:-3].capitalize())

            # If ends on "es"
            # Remove "es"
            if word[-2:] == "es":  # Kindes|wohl (Kindes) -> (Kind)
                # action = ["-es"]
                possible_modifications.append(word[:-2].lower())
                possible_modifications.append(word[:-2].capitalize())

            """
            Verb Rules
            """
            # If word does not end on "en" and not on "e"
            # Add -en
            if not word[-2:] == "en" and not word[-1:] == "e":
                # action = ["+en"]
                possible_modifications.append(word.lower() + "en")
                possible_modifications.append(word.capitalize() + "en")

            # If word ends on "en" PR word ends on "em"
            # Add -en, remove -e- in context of n, m)
            # This is totally different to the NOUN rule above
            if word[-2:] == "en" or word[-2:] == "em":
                # action = ["+n", "+en"]
                possible_modifications.append(word[:-2].lower() + word[-1:] + "en")
                possible_modifications.append(word[:-2].capitalize() + word[-1:] + "en")

            # If word does not end on "n"
            # Add -n
            if not word[-1:] == "n":
                # action = ["+n"]
                possible_modifications.append(word.lower() + "n")
                possible_modifications.append(word.capitalize() + "n")

        # modification is valid if:
        # - not in stopwords
        # - len > 2
        # - not in forbidden modifier list
        # - in lemma list

        possible_modifications = [w for w in possible_modifications if w.lower() not in self.stop_words
                                  and len(w) > 2
                                  and str(w) in self.lemma_data]

        return possible_modifications
