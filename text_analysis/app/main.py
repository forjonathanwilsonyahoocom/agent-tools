#!/usr/bin/env python3
"""
Text Analysis Tool
===================

This script analyses a set of text files in a given working directory.
It can focus on a single file or on all files matching a given extension.
The analysis includes:

* High inverse document frequency (IDF) words
* Most frequent non‑stop‑word words
* Overall sentiment (VADER) and lists of positive/negative documents
* summary of each file
* A lightweight high‑level summary of the corpus

The script is intended to be the entry point of a Docker container.
It prints a summary report to stdout and then exits.
"""

import argparse
import json
import sys
import os
from pathlib import Path
from collections import Counter

import spacy

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from sklearn.feature_extraction.text import TfidfVectorizer

from sumy.nlp.tokenizers import Tokenizer
from sumy.parsers.plaintext import PlaintextParser
from sumy.summarizers.lex_rank import LexRankSummarizer




def summarize_text(text: str, sentence_count: int = 5) -> str:
    if not text.strip():
        return ""

    parser = PlaintextParser.from_string(text, Tokenizer("english"))
    summarizer = LexRankSummarizer()
    sentences = summarizer(parser.document, sentence_count)
    return " ".join(str(sentence) for sentence in sentences)
    
def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Recursive text analysis tool")
    parser.add_argument(
        "--workdir",
        type=str,
        default=".",
        help="Working directory relative to the container root (default: current directory)",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Optional single file to focus on (relative to workdir)",
    )
    parser.add_argument(
        "--ext",
        type=str,
        default="*.txt",
        help="Optional file extension filter (glob pattern, default: *.txt)",
    )
    return parser.parse_args(argv)


def get_file_paths(workdir: Path, file: str | None, ext: str) -> list[Path]:
    """Return a list of file paths to analyze.

    If ``file`` is provided, it is resolved relative to ``workdir`` and
    returned as a single‑item list.  Otherwise all files matching ``ext``
    under ``workdir`` (recursively) are returned.
    """
    if file:
        target = workdir / file
        if not target.is_file():
            raise FileNotFoundError(f"Specified file not found: {target}")
        return [target]
    # No specific file – find all matching files
    return sorted(workdir.rglob(ext))


def load_texts(workdir: Path, paths: list[Path]) -> list[dict]:
    texts = []
    for p in paths:
        try:
            document = {"text" : p.read_text(encoding="utf-8"),
                        "file" :  str(p.relative_to(workdir))}
            texts.append(document)
        except Exception as e:  # pragma: no cover
            print(f"Warning: could not read {p}: {e}")
    return texts

 
def compute_idf(texts: list[dict], top_n: int = 50) -> list[tuple[str, float]]:
    documents = [row["text"] for row in texts]
    if not documents:
        print("no documents")
        return []
    vectorizer = TfidfVectorizer(stop_words="english")
    try:
        vectorizer.fit(documents)
    except Exception as e:  # e.g. empty vocabulary
        print(f"compute_idf vectorizer failed: {e}")
        return []

    pairs = sorted(
        zip(vectorizer.get_feature_names_out(), vectorizer.idf_),
        key=lambda item: item[1],
        reverse=True,
    )
    return [
        (token, score)
        for token, score in pairs
        if not any(ch.isdigit() for ch in token)
    ][:top_n]


def compute_most_frequent_words(texts: list[dict], nlp, top_n: int = 10) -> list[tuple[str, int]]:
    """Return the most frequent non‑stop‑word tokens.

    Tokens are lower‑cased and filtered to exclude spaCy stop‑words.
    """
    counter = Counter()
    text_from_files = []
    for text in texts:
        text_from_files.append(text["text"])
        
    for doc in nlp.pipe(text_from_files, disable=["parser", "ner"]):
        for token in doc:
            if token.is_alpha and not token.is_stop:
                counter[token.lemma_.lower()] += 1
    return counter.most_common(top_n)


def compute_sentiment(texts: list[dict]) -> tuple[list[dict], float]:
    """Return overall sentiment and augmented with positive/negative documents.

    Sentiment is computed using VADER.  Documents with compound score > 0.05
    are considered positive, < -0.05 negative.
    """
    analyzer = SentimentIntensityAnalyzer()
    compound_scores = []
    for row in texts:
        score = analyzer.polarity_scores(row["text"])["compound"]
        compound_scores.append(score)
        row["sentiment_score"] = score
        if score > 0.05:
            row["sentiment"] = "positive"
        elif score < -0.05:
            row["sentiment"] = "negative"
        else:
            row["sentiment"] = "neutral"
    overall = sum(compound_scores) / len(compound_scores) if compound_scores else 0.0
    return (texts, overall)


def compute_summary(texts: list[dict]) -> tuple[list[dict], str]:
    corpus = []
    for row in texts:
        minimized = row.pop("text", "")[:3000]
        try:
            summary = summarize_text(minimized)
            corpus.append(summary)
            row["summary"] = summary
        except Exception as e:
            row["summary"] = "text summarize failed"
            print(f"text summarize failed: {e}")

    try:
        overall_summary = summarize_text("\n\n".join(corpus))
    except Exception as e:
        overall_summary = ""
        print(f"corpus summarize failed: {e}")

    return texts, overall_summary


def main(argv=None):
    args = parse_args(argv)
    workdir = Path(args.workdir).resolve()
    if not workdir.is_dir():
        print(f"Error: workdir not found: {workdir}")
        sys.exit(1)

    try:
        file_paths = get_file_paths(workdir, args.file, args.ext)
    except FileNotFoundError as e: 
        print(str(e))
        sys.exit(1)

    if not file_paths:
        print("No files found to analyze.")
        sys.exit(0)

    texts = load_texts(workdir, file_paths)

    # Load spaCy model once
    try:
        nlp = spacy.load("en_core_web_sm")
    except Exception as e:
        print(f"Could not load en_core_web_sm: {e}")
        sys.exit(1)
            
    idf_top = compute_idf(texts)
    frequent_words = compute_most_frequent_words(texts, nlp)
    texts, overall_sentiment = compute_sentiment(texts)
    texts, corpus_summary = compute_summary(texts)

    report = {
        "idf_top": idf_top,
        "frequent_words": frequent_words,
        "summary": texts,
        "overall_gist" : corpus_summary,
        "overall_sentiment" : overall_sentiment,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":  # pragma: no cover
    main()
