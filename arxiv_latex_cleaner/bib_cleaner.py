# coding=utf-8
# Copyright 2018 The Google Research Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Cleans .bib files: drops uncited entries and strips unnecessary fields."""
import logging

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
import regex

# Matches natbib/biblatex citation commands, e.g. \cite, \citep, \citet*,
# \parencite, \Autocite, \citeauthor, and \nocite, capturing the
# comma-separated key list inside the mandatory {...} argument. Optional
# `[...]` pre/post-note arguments (as used by \citep[see][]{key}) are
# skipped.
CITE_COMMAND_PATTERN = regex.compile(
    r'\\(?:[A-Za-z]*[Cc]ite[A-Za-z]*|[Nn]ocite)\*?'
    r'(?:\[[^\]]*\])*\{([^}]*)\}'
)

# Matches '@comment{...}' blocks, treating everything between the outer
# matching braces as opaque comment text (per BibTeX semantics), including
# arbitrarily nested braces such as a whole commented-out entry. Uses the
# same balanced-brace recursion trick as `_remove_command` in
# arxiv_latex_cleaner.py.
COMMENT_BLOCK_PATTERN = regex.compile(
    r'@comment\s*\{((?:[^{}]+|\{(?1)\})*)\}', regex.IGNORECASE
)

# Fields that are reference-manager bookkeeping (Zotero/Mendeley/JabRef/
# BibDesk) or otherwise documented as unused by standard bibliography
# styles, so stripping them by default never changes how the compiled
# bibliography looks. Fields that *can* be rendered depending on the
# bibliography style in use (e.g. 'doi', 'url', 'note', 'month', 'eprint':
# many .bst/biblatex styles do print these) are deliberately NOT included
# here; pass them via `bib_fields_to_delete` if you've confirmed your own
# style doesn't use them.
DEFAULT_BIB_FIELDS_TO_DELETE = [
    'abstract',
    'abstractnote',
    'annotation',
    'annote',
    'bdsk-file-1',
    'bdsk-file-2',
    'bdsk-url-1',
    'bdsk-url-2',
    'copyright',
    'file',
    'groups',
    'isbn',
    'issn',
    'keywords',
    'language',
    'mendeley-tags',
    'owner',
    'pmid',
    'shorttitle',
    'timestamp',
]

# Entry types that are never "cited" via \cite/\citep/etc. but that still
# must be kept as-is: they configure how the bibliography style renders
# every other entry, rather than describing a work. E.g. IEEEtran's
# '@IEEEtranBSTCTL' lets authors override .bst formatting defaults
# (dash style, name format, URL/DOI display, ...); dropping it silently
# changes how the whole bibliography looks.
ALWAYS_KEEP_ENTRY_TYPES = {'ieeetranbstctl'}


def find_cited_keys(tex_content):
  """Finds all BibTeX keys cited anywhere in 'tex_content'.

  Recognizes natbib- and biblatex-style citation commands (\\cite, \\citep,
  \\citet, \\parencite, \\autocite, \\citeauthor, their starred and
  capitalized variants, etc.) as well as \\nocite.

  If a `\\nocite{*}` is found (which tells BibTeX/biblatex to include every
  entry of the bibliography, cited or not), returns {'*'} to signal that all
  entries should be kept.
  """
  keys = set()
  for match in CITE_COMMAND_PATTERN.finditer(tex_content):
    for key in match.group(1).split(','):
      key = key.strip()
      if key == '*':
        return {'*'}
      if key:
        keys.add(key)
  return keys


def strip_comment_blocks(bib_content):
  """Removes '@comment{...}' blocks from 'bib_content'.

  Everything between the outer matching braces is treated as comment text
  and dropped, including nested braces (e.g. a whole commented-out entry).
  This is done as a pre-processing step, before bibtexparser ever sees the
  content: bibtexparser's own comment handling doesn't balance nested
  braces, so content commented out this way (a common way to disable an
  entry without deleting it) could otherwise leak through and get parsed as
  a live entry.
  """
  return COMMENT_BLOCK_PATTERN.sub('', bib_content)


def _add_crossref_keys(entries_by_id, cited_keys):
  """Pulls in keys referenced via 'crossref'/'xdata' fields of cited entries.

  BibTeX/biblatex entries can inherit fields from another entry via
  'crossref' (BibTeX/biblatex) or 'xdata' (biblatex), so those targets must
  be kept even if they are never cited directly.
  """
  to_process = list(cited_keys)
  while to_process:
    key = to_process.pop()
    entry = entries_by_id.get(key)
    if entry is None:
      continue
    for field in ('crossref', 'xdata'):
      for target in entry.get(field, '').split(','):
        target = target.strip()
        if target and target not in cited_keys:
          cited_keys.add(target)
          to_process.append(target)


def clean_bib_content(
    bib_content, cited_keys, fields_to_delete, fields_to_keep=()
):
  """Removes uncited entries, unnecessary fields, and comments.

  Also strips all '@comment{...}' blocks (see `strip_comment_blocks`).

  Args:
    bib_content: The contents of a .bib file, as a string.
    cited_keys: Set of BibTeX keys that are cited in the paper. If it
      contains '*', every entry is kept.
    fields_to_delete: Iterable of field names (case-insensitive) to strip
      from every kept entry.
    fields_to_keep: Iterable of field names (case-insensitive) that override
      'fields_to_delete', i.e. that must never be stripped.

  Returns:
    The cleaned .bib content, as a string.
  """
  bib_content = strip_comment_blocks(bib_content)
  # By default, bibtexparser silently drops entries whose type isn't one of
  # the handful of standard BibTeX types, discarding e.g. biblatex's
  # '@online', '@report', '@thesis', '@collection', or IEEEtran's
  # '@ieeetranbstctl' control entries. Keep every entry type as-is.
  parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False)
  bib_database = bibtexparser.loads(bib_content, parser=parser)
  entries_by_id = {entry['ID']: entry for entry in bib_database.entries}

  # Leftover stray braces from a malformed '@comment{...}' in the source (or
  # any other free text sitting between entries) are themselves picked up by
  # bibtexparser as comments; drop those too so no comment text survives.
  bib_database.comments = []

  keep_all = '*' in cited_keys
  if not keep_all:
    cited_keys = set(cited_keys)
    _add_crossref_keys(entries_by_id, cited_keys)

  fields_to_delete = {f.lower() for f in fields_to_delete} - {
      f.lower() for f in fields_to_keep
  }

  kept_entries = []
  for entry in bib_database.entries:
    is_special = entry['ENTRYTYPE'].lower() in ALWAYS_KEEP_ENTRY_TYPES
    if not keep_all and not is_special and entry['ID'] not in cited_keys:
      logging.info('Removing uncited bib entry %s.', entry['ID'])
      continue
    if not is_special:
      for field in list(entry.keys()):
        if field.lower() in ('id', 'entrytype'):
          continue
        if field.lower() in fields_to_delete:
          del entry[field]
    kept_entries.append(entry)

  bib_database.entries = kept_entries

  writer = BibTexWriter()
  writer.indent = '  '
  writer.order_entries_by = None
  return bibtexparser.dumps(bib_database, writer)


def clean_bib_file(
    input_path, output_path, cited_keys, fields_to_delete, fields_to_keep=()
):
  """Reads a .bib file from 'input_path', cleans it, writes it to 'output_path'."""
  with open(input_path, 'r', encoding='utf-8') as f:
    bib_content = f.read()

  cleaned_content = clean_bib_content(
      bib_content, cited_keys, fields_to_delete, fields_to_keep
  )

  with open(output_path, 'w', encoding='utf-8') as f:
    f.write(cleaned_content)
