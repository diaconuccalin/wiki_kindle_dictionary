PROFILE ?= pocket
PYTHON ?= python3
FLAGS ?=
VOLUME ?=

ifeq ($(PROFILE),custom)
  PROFILE_FLAG = --profile custom
else
  PROFILE_FLAG = --profile $(PROFILE)
endif

ifdef FAST
  FLAGS += --fast
endif

ifdef VOLUME
  VOLUME_FLAG = --volume $(VOLUME)
endif

.PHONY: all download parse parse-articles parse-langlinks parse-redirects parse-pageviews merge html compile test clean complete

all: download parse merge html compile

download:
	$(PYTHON) 01_download.py $(PROFILE_FLAG) $(FLAGS)

parse: parse-articles parse-langlinks parse-redirects parse-pageviews

parse-articles:
	$(PYTHON) 02a_parse_articles.py $(PROFILE_FLAG) $(FLAGS)

parse-langlinks:
	$(PYTHON) 02b_parse_langlinks.py $(PROFILE_FLAG) $(FLAGS)

parse-redirects: parse-langlinks
	$(PYTHON) 02b2_parse_redirects.py $(PROFILE_FLAG) $(FLAGS)

parse-pageviews:
	$(PYTHON) 02c_parse_pageviews.py $(PROFILE_FLAG) $(FLAGS)

merge:
	$(PYTHON) 03_merge.py $(PROFILE_FLAG) $(FLAGS)

html:
	$(PYTHON) 04_generate_html.py $(PROFILE_FLAG) $(VOLUME_FLAG) $(FLAGS)

compile:
	$(PYTHON) 05_compile.py $(PROFILE_FLAG) $(VOLUME_FLAG) $(FLAGS)

test:
	$(PYTHON) 01_download.py --profile pocket --test $(FLAGS)
	$(PYTHON) 02a_parse_articles.py --profile pocket --test $(FLAGS)
	$(PYTHON) 02b_parse_langlinks.py --profile pocket --test $(FLAGS)
	$(PYTHON) 02b2_parse_redirects.py --profile pocket --test $(FLAGS)
	$(PYTHON) 02c_parse_pageviews.py --profile pocket --test $(FLAGS)
	$(PYTHON) 03_merge.py --profile pocket --test $(FLAGS)
	$(PYTHON) 04_generate_html.py --profile pocket --test $(FLAGS)
	$(PYTHON) 05_compile.py --profile pocket --test --fast $(FLAGS)

complete: download parse
	$(PYTHON) 03_merge.py --profile complete $(FLAGS)
	$(PYTHON) 04_generate_html.py --profile complete $(VOLUME_FLAG) $(FLAGS)
	$(PYTHON) 05_compile.py --profile complete $(VOLUME_FLAG) $(FLAGS)

clean:
	rm -rf data/processed/*.jsonl data/processed/*.tsv data/processed/*.tmp
	rm -rf data/kindle/*
	rm -rf output/*

clean-all: clean
	rm -rf data/raw/*
