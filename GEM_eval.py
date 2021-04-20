""" GEM evaluation"""

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"


from graphdb_handler import GraphDBHandler
from term_mapper import TermMapper


class TermMapperEvaluator:
    def __init__(self, test_data, do_not_delete=False, exp_prefix=None):
        self.TermMapper = TermMapper()
        self.DBHandler = GraphDBHandler()

        self.do_not_delete = do_not_delete
        self.test_data_path = test_data

        self.exp_prefix = exp_prefix

    def _set_params(self, params):
        self.TermMapper.set_conf_values(params)
        self.DBHandler.set_conf_values(params)

    @staticmethod
    def rreplace(s, old, new, occurrence):
        li = s.rsplit(old, occurrence)
        return new.join(li)

    @staticmethod
    def mesh_index_depth(index):
        depth = len(index.split(".")) - 1
        return depth

    @staticmethod
    def mesh_index_split(index):
        split = index.split(".")
        split.insert(0, split[0][0:1])
        split.insert(0, "ROOT")

        return split

    @staticmethod
    def lcs_index_dist(lcs_index, listing_index):
        if lcs_index == "":
            lcs_index_split = []
        else:
            lcs_index_split = lcs_index.split(".")

        listing_index = listing_index.split(".")
        listing_index.insert(0, listing_index[0][0:1])
        listing_index.insert(0, "ROOT")

        distance = len(listing_index) - len(lcs_index_split)
        return distance

    @staticmethod
    def calc_hops(start, target):
        hops = 0
        start = start[:1] + "." + start[1:]
        target = target[:1] + "." + target[1:]

        still_running = True
        while still_running:
            if target == start:
                break

            elif start in target:
                not_equal = True
                while not_equal:
                    target = target[:target.rfind(".")]
                    hops += 1
                    if target == start:
                        not_equal = False
                still_running = False
            else:
                start = start[:start.rfind(".")]
                hops += 1

        return hops

    def calculate_avg_hops(self, match_tuples):
        total_hops = 0

        for tuple_ in match_tuples:
            target = tuple_[0]
            start = tuple_[1]

            if target is None:
                continue

            hops = self.calc_hops(start, target)
            total_hops += hops

        hops_in_avg = total_hops / len(match_tuples)
        return hops_in_avg

    def get_mesh_record_indices(self, record_id):
        result = self.DBHandler.get_all_index_listings_of_a_mesh_record(record_id)
        extracted_listings = []

        for binding in result["results"]["bindings"]:
            extracted_listings.append(self.DBHandler.remove_uri(binding["index"]["value"]))

        return extracted_listings

    def find_mesh_lcs(self, index_one, index_two):
        index_one_split = self.mesh_index_split(index_one)
        index_two_split = self.mesh_index_split(index_two)

        lcs_index_listing = ""
        index = 0
        for index_one_entry in index_one_split:
            if len(index_two_split) <= index:
                break
            if index_one_entry == index_two_split[index]:
                lcs_index_listing += index_one_entry + "."
            else:
                break
            index += 1

        lcs_index_listing = self.rreplace(lcs_index_listing, ".", "", 1)
        return lcs_index_listing

    def mesh_conceptual_sim(self, match_listing, base_listing):
        lcs = self.find_mesh_lcs(match_listing, base_listing)
        lcs_depth = self.mesh_index_depth(lcs)  # N3
        match_listing_distance = self.lcs_index_dist(lcs, match_listing)  # N1
        base_listing_distance = self.lcs_index_dist(lcs, base_listing)  # N2

        weight = 2
        conceptual_similarity = weight*lcs_depth / (match_listing_distance + base_listing_distance + weight*lcs_depth)

        return conceptual_similarity

    @staticmethod
    def _clean_match_info(match):
        for e in ["base_word", "context_sentence"]:
            try:
                del match[e]
            except KeyError:
                continue

        return match

    def _measure_match_distance(self, match, base_listings_of_record):
        conceptual_sims = {}
        hop_listings = {}
        match_listings = self.get_mesh_record_indices(match["corresponding_id"])
        for match_listing in match_listings:
            conceptual_sims[match_listing] = ("", -99)
            hop_listings[match_listing] = ("", 99999)

            for base_listing in base_listings_of_record:
                similarity = self.mesh_conceptual_sim(match_listing, base_listing)
                hops = self.calc_hops(match_listing, base_listing)

                if conceptual_sims[match_listing][1] < similarity:
                    conceptual_sims[match_listing] = (base_listing, similarity)

                if hop_listings[match_listing][1] > hops:
                    hop_listings[match_listing] = (base_listing, hops)

        match["conceptual_similarities"] = conceptual_sims
        match["hops"] = hop_listings

        self._clean_match_info(match)

    def try_delete_term(self, term):
        result = self.DBHandler.get_id_from_mesh_term(term)
        term_id = None
        for binding in result["results"]["bindings"]:
            val = self.DBHandler.remove_uri(binding["term"]["value"])
            if val.startswith("ger"):
                term_id = val
                break

        if term_id is None:
            print(f"Warning: No term ID found for: {term}")
            raise KeyError("Please re-insert term to graphdb")

        # Delete 'hasTermName' relation before evaluation
        with open("sparql_insert_log.txt", "a") as ifile:
            ifile.write(f"mesh:{term_id} mesh_entity:hasTermName '{term}' .\n")
        self.DBHandler.delete_specific_term_from_mesh(term, term_id)

        return term_id

    def eval_mesh_mapping(self, params=None):  # noqa: C901
        if params is not None:
            self._set_params(params)

        with open(self.test_data_path) as f:
            test_data = [line.split("\t") for line in f.read().split("\n")]

        test_results = []

        for descriptor_id, term, sentence in test_data:
            deleted_term_id = None
            if not self.do_not_delete:
                deleted_term_id = self.try_delete_term(term)

            mesh_direct_match, mesh_similar_matches, mesh_compound_matches, _, _, gem_matches = \
                self.TermMapper.find_matches(term, sentence)

            base_record_listings = self.get_mesh_record_indices(descriptor_id)
            if len(base_record_listings) == 0:
                print("Descriptor ID not found in DB:", descriptor_id)

            for match in mesh_direct_match:
                self._measure_match_distance(match, base_record_listings)

            for match_tuple in mesh_similar_matches:
                match = match_tuple[0]
                self._measure_match_distance(match, base_record_listings)

            for match in mesh_compound_matches:
                self._measure_match_distance(match, base_record_listings)

            for match_tuple in gem_matches:
                match = match_tuple[0]
                self._measure_match_distance(match, base_record_listings)

            current_results = {
                    "base_word": term,
                    "context_sentence": sentence,
                    "record": descriptor_id,
                    "direct_match": mesh_direct_match,
                    "similar_matches": mesh_similar_matches,
                    "compound_matches": mesh_compound_matches,
                    "gem_matches": gem_matches
                }
            test_results.append(current_results)

            if not self.do_not_delete:
                # Re-insert term after evaluation
                self.DBHandler.insert_specific_term_into_mesh(term, deleted_term_id)

        self.analyse_results(test_results)

    @staticmethod
    def _best_concept_sim(vals):
        tmp_vals = [val[1] for val in vals]
        return max(tmp_vals)

    def analyse_results(self, results):
        lexical_match_cs = []
        gem_match_cs = []
        revgem_match_cs = []
        compound_match_cs = []
        all_match_cs = []

        lexical_match_hop = []
        gem_match_hop = []
        revgem_match_hop = []
        compound_match_hop = []
        all_match_hop = []

        correct_lex = 0
        correct_gem = 0
        correct_revgem = 0
        correct_comp = 0

        multi_lex = 0
        multi_gem = 0
        multi_revgem = 0
        multi_comp = 0

        no_match = 0

        for term in results:
            matched = False

            if len(term["direct_match"]) > 1:
                multi_lex += 1

            for exact in term["direct_match"]:
                matched = True
                val = self._best_concept_sim(exact["conceptual_similarities"].values())
                lexical_match_cs.append(val)
                all_match_cs.append(val)

                if val == 1.0:
                    correct_lex += 1

                val_hop = self._best_concept_sim(exact["hops"].values())
                lexical_match_hop.append(val_hop)
                all_match_hop.append(val_hop)

            if len(term["similar_matches"]) > 1:
                multi_gem += 1

            for similar in term["similar_matches"]:
                matched = True
                similar = similar[0]
                val = self._best_concept_sim(similar["conceptual_similarities"].values())
                gem_match_cs.append(val)
                all_match_cs.append(val)

                if val == 1.0:
                    correct_gem += 1

                val_hop = self._best_concept_sim(similar["hops"].values())
                gem_match_hop.append(val_hop)
                all_match_hop.append(val_hop)

            if len(term["gem_matches"]) > 1:
                multi_revgem += 1

            for gem in term["gem_matches"]:
                matched = True
                gem = gem[0]
                val = self._best_concept_sim(gem["conceptual_similarities"].values())
                revgem_match_cs.append(val)
                all_match_cs.append(val)

                if val == 1.0:
                    correct_revgem += 1

                val_hop = self._best_concept_sim(gem["hops"].values())
                revgem_match_hop.append(val_hop)
                all_match_hop.append(val_hop)

            if len(term["compound_matches"]) > 1:
                multi_comp += 1

            for compound in term["compound_matches"]:
                matched = True
                val = self._best_concept_sim(compound["conceptual_similarities"].values())
                compound_match_cs.append(val)
                all_match_cs.append(val)

                if val == 1.0:
                    correct_comp += 1

                val_hop = self._best_concept_sim(compound["hops"].values())
                compound_match_hop.append(val_hop)
                all_match_hop.append(val_hop)

            if not matched:
                no_match += 1

        dataset_len = len(results)

        len_all = len(all_match_cs)
        len_exact = len(lexical_match_cs)
        len_gem = len(gem_match_cs)
        len_revgem = len(revgem_match_cs)
        len_compound = len(compound_match_cs)

        print(f"Dataset length: {dataset_len}")
        print(f"All matches: {len_all} ({round(len_all/dataset_len*100, 3)}%)")
        print(f"Lexical matches: {len_exact} ({round(len_exact/dataset_len*100, 3)}%) ({multi_lex} multiple)")
        print(f"GEM matches: {len_gem} ({round(len_gem/dataset_len*100, 3)}%) ({multi_gem} multiple)")
        print(f"revGEM matches: {len_revgem} ({round(len_revgem/dataset_len*100, 3)}%) ({multi_revgem} multiple)")
        print(f"Compound matches: {len_compound} ({round(len_compound/dataset_len*100, 3)}%) ({multi_comp} multiple)")
        print(f"No matches: {no_match} ({round(no_match/dataset_len*100, 3)}%)")
        print("----------------------------")
        print(f"Lexical correct: {correct_lex}")
        print(f"GEM correct: {correct_gem}")
        print(f"revGEM correct: {correct_revgem}")
        print(f"Compound correct: {correct_comp}")
        print("----------------------------")

        print(f"Avg. All matches: {round(sum(all_match_cs) / len_all, 3)}")
        if len_exact > 0:
            print(f"Avg. Lexical matches: {round(sum(lexical_match_cs) / len_exact, 3)}")
        if len_gem > 0:
            print(f"Avg. GEM matches: {round(sum(gem_match_cs) / len_gem, 3)}")
        if len_revgem > 0:
            print(f"Avg. revGEM matches: {round(sum(revgem_match_cs) / len_revgem, 3)}")
        if len_compound > 0:
            print(f"Avg. Compound matches: {round(sum(compound_match_cs) / len_compound, 3)}")
        print("---------------------------")

        print(f"Avg. Hops All matches: {round(sum(all_match_hop) / len_all, 3)}")
        if len_exact > 0:
            print(f"Avg. Hops Lexical matches: {round(sum(lexical_match_hop) / len_exact, 3)}")
        if len_gem > 0:
            print(f"Avg. Hops GEM matches: {round(sum(gem_match_hop) / len_gem, 3)}")
        if len_revgem > 0:
            print(f"Avg. Hops revGEM matches: {round(sum(revgem_match_hop) / len_revgem, 3)}")
        if len_compound > 0:
            print(f"Avg. Hops Compound matches: {round(sum(compound_match_hop) / len_compound, 3)}")
        print("---------------------------")
