""" Run """

__author__ = "Jannik Geyer, Daniel Bruneß, Matthias Bay"
__copyright__ = "Copyright 2021, MINDS medical GmbH"
# __license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Daniel Bruneß"
__email__ = "daniel.bruness@kite.thm.de"
__status__ = "Development"

import sys
from os import path
from GEM_eval import TermMapperEvaluator

if "__main__" == __name__:
    default_mode = "reinsert"
    data_path = "test_data"
    reinsert_data_file = "reinsert_data.tsv"
    enrich_data_file = "enrich_data.tsv"

    try:
        mode = sys.argv[1]
        if mode not in ["reinsert", "enrich"]:
            mode = default_mode
    except IndexError:
        mode = default_mode

    if mode == "reinsert":
        test_data = path.join(data_path, reinsert_data_file)
        do_not_delete = False
        prefix = "re_insert"

    else:
        test_data = path.join(data_path, enrich_data_file)
        do_not_delete = True
        prefix = "enrich"

    print("Mode:", mode)
    print("Test Data:", test_data)
    print("Do-not-delete:", do_not_delete)
    print("Experiment Prefix:", prefix)

    tme = TermMapperEvaluator(test_data=test_data, do_not_delete=do_not_delete, exp_prefix=prefix)
    tme.eval_mesh_mapping()
