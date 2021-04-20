# GEM-Paper
Welcome to the code repository for the paper 
"A Generatively Enhanced Embedding Model For Knowledge Graph Enrichment"
submitted to ISWC2021.

## Requirements
These requirements are not mandatory, but should give an orientation for what is needed.
Experiments were run under these settings and software/hardware specifications, respectively.

### Hardware
- Intel i7-9750H
- 32GB RAM
- 30GB SSD  

A basic laptop will do. You may outsource GraphDB and the fastText (GEM) server.

### Software
- Ubuntu 20.04 LTS
- Python 3.7
- [Ontotext GraphDB Free](https://www.ontotext.com/products/graphdb/graphdb-free/) 9.6
- [SECOS: Compound Splitter](https://github.com/riedlma/SECOS)

### Python Packages
- nltk==3.6.1
- numpy==1.20.2
- requests==2.25.1
- spacy==3.0.5
- SPARQLWrapper==1.8.5

### Additional
The base [fastText](https://fasttext.cc/) model for the German language was downloaded
here: [Word vectors for 157 languages](https://fasttext.cc/docs/en/crawl-vectors.html#models).  
We retrieved the German _MeSH_ in version 2019 in XML format [here](https://www.dimdi.de/dynamic/de/klassifikationen/weitere-klassifikationen-und-standards/mesh/).  


## Test Data
The test data can be found in `test_data`. Both files are tab-separated-values (TSV).  
`reinsert_data.tsv` contains the 113 terms for the _re-insert_ experiment,  
`enrich_data.tsv` contains 45 terms for the _enrich_ experiment.  

The text files for term extraction that led to the _enrich_ data were compiled from
[JSynCC](https://github.com/JULIELab/jsyncc).


## Setup

Create virtual environment  
```
python -m venv .env
```
Activate virtual environment
```
source .env/bin/activate
``` 

Install Python requirements
```
pip install -r requirements.txt
``` 

Install (German) Spacy model
```
python -m spacy download de_core_news_lg
```

### Optional
Start fastText server  
```
gunicorn -t 600 --bind 0.0.0.0:5000 fasttext_service:app
```

Start SECOS server  
```
python decompound_server.py ./resources/data/denews70M_trigram__candidates.gz ./resources/data/denews70M_trigram__WordCount.gz 50 3 3 5 3 upper 0.01 2020
```

Start GraphDB server  
```
cd graphdb-free-9.6.0
./bin/graphdb
```

## Config
All parameters and additional settings can be found in `config.py`.  
For running the code, the server settings are most important (host & port) for:
- fastText
- SECOS
- GraphDB 

All _similarity thresholds_ influence the results.

## Run
To run the evaluation, use following command:
```
python run.py reinsert
python run.py enrich
```

## Complexity
```
# TODO
n := nodes in KG
m := candidate terms

runtime
O(n+m) 

memory
O(1)
```