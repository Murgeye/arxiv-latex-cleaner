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

import unittest

from arxiv_latex_cleaner import bib_cleaner

SAMPLE_BIB = r"""
@article{smith2020,
  author = {Smith, J.},
  title = {A Cited Paper},
  journal = {Journal of Examples},
  year = {2020},
  abstract = {A long abstract nobody needs on arXiv.},
  url = {https://example.com/smith2020},
  doi = {10.1000/example},
  keywords = {foo, bar}
}

@inproceedings{child2021,
  author = {Child, A.},
  title = {A Paper In Proceedings},
  crossref = {proc2021},
  year = {2021}
}

@proceedings{proc2021,
  editor = {Editor, E.},
  title = {Proceedings of Examples},
  year = {2021}
}

@article{unused2099,
  author = {Nobody},
  title = {Never Cited},
  journal = {Journal},
  year = {2099},
  abstract = {Should be dropped entirely.}
}

@online{web2022,
  author = {Web, W.},
  title = {A Cited Web Page},
  year = {2022},
  url = {https://example.com/web2022}
}

@thesis{phd2015,
  author = {Grad, S.},
  title = {A Cited Thesis},
  year = {2015}
}

@IEEEtranBSTCTL{IEEEexample:BSTcontrol,
  CTLdash_repeated_names = "no"
}
"""


class StripCommentBlocksTest(unittest.TestCase):

  def test_removes_simple_comment(self):
    bib = '@comment{Phase III, step 1}\n\n@article{a, title={t}}'
    stripped = bib_cleaner.strip_comment_blocks(bib)
    self.assertNotIn('@comment', stripped.lower())
    self.assertIn('@article{a', stripped)

  def test_removes_comment_with_nested_braces(self):
    # A whole commented-out entry, disabled by wrapping it in @comment{...}.
    bib = (
        '@comment{\n'
        '@article{disabled2020, author = {X}, title = {Y}}\n'
        '}\n\n'
        '@article{live2021, title = {Z}}'
    )
    stripped = bib_cleaner.strip_comment_blocks(bib)
    self.assertNotIn('disabled2020', stripped)
    self.assertIn('live2021', stripped)

  def test_removes_multiple_comments_case_insensitively(self):
    bib = '@Comment{one}\n@COMMENT{two}\n@article{a, title={t}}'
    stripped = bib_cleaner.strip_comment_blocks(bib)
    self.assertNotIn('one', stripped)
    self.assertNotIn('two', stripped)
    self.assertIn('@article{a', stripped)

  def test_leaves_non_comment_content_untouched(self):
    bib = '@article{a, title={t}}'
    self.assertEqual(bib_cleaner.strip_comment_blocks(bib), bib)


class FindCitedKeysTest(unittest.TestCase):

  def test_finds_various_citation_commands(self):
    tex_content = r"""
    \cite{key_a}
    \citep[see][p.~2]{key_b, key_c}
    \citet*{key_d}
    \parencite{key_e}
    \Autocite{key_f}
    \textcite{key_g}
    \citeauthor{key_h}
    \footcite{key_i}
    """
    self.assertEqual(
        bib_cleaner.find_cited_keys(tex_content),
        {
            'key_a',
            'key_b',
            'key_c',
            'key_d',
            'key_e',
            'key_f',
            'key_g',
            'key_h',
            'key_i',
        },
    )

  def test_ignores_non_citation_commands(self):
    tex_content = r'\cref{fig:one} \label{sec:intro} \ref{eq:1}'
    self.assertEqual(bib_cleaner.find_cited_keys(tex_content), set())

  def test_nocite_star_means_keep_all(self):
    tex_content = r'\cite{key_a} \nocite{*}'
    self.assertEqual(bib_cleaner.find_cited_keys(tex_content), {'*'})

  def test_nocite_specific_key(self):
    tex_content = r'\nocite{key_a}'
    self.assertEqual(bib_cleaner.find_cited_keys(tex_content), {'key_a'})

  def test_no_citations(self):
    self.assertEqual(bib_cleaner.find_cited_keys('No citations here.'), set())


class CleanBibContentTest(unittest.TestCase):

  def test_removes_uncited_entries(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'smith2020'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertIn('smith2020', cleaned)
    self.assertNotIn('unused2099', cleaned)

  def test_strips_default_noisy_fields(self):
    # Only fields that are pure reference-manager bookkeeping (never
    # rendered by any bibliography style) are stripped by default.
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'smith2020'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertNotIn('abstract', cleaned)
    self.assertNotIn('keywords', cleaned)
    self.assertIn('author', cleaned)
    self.assertIn('title', cleaned)
    self.assertIn('journal', cleaned)
    self.assertIn('year', cleaned)

  def test_keeps_style_dependent_fields_by_default(self):
    # 'url'/'doi' can be rendered depending on the bibliography style (e.g.
    # IEEEtran.bst), so they must survive unless explicitly opted into
    # bib_fields_to_delete.
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'smith2020'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertIn('url', cleaned)
    self.assertIn('doi', cleaned)

  def test_strips_style_dependent_fields_when_explicitly_requested(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB,
        {'smith2020'},
        bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE + ['url', 'doi'],
    )
    self.assertNotIn('url', cleaned)
    self.assertNotIn('doi', cleaned)

  def test_keeps_all_entries_on_star(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'*'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertIn('smith2020', cleaned)
    self.assertIn('unused2099', cleaned)

  def test_keeps_crossref_target_of_cited_entry(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'child2021'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertIn('child2021', cleaned)
    self.assertIn('proc2021', cleaned)
    self.assertNotIn('smith2020', cleaned)
    self.assertNotIn('unused2099', cleaned)

  def test_fields_to_keep_overrides_fields_to_delete(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB,
        {'smith2020'},
        fields_to_delete=['url', 'doi'],
        fields_to_keep=['doi'],
    )
    self.assertNotIn('url', cleaned)
    self.assertIn('doi', cleaned)

  def test_keeps_nonstandard_entry_types_when_cited(self):
    # bibtexparser's default parser silently discards entry types outside a
    # small standard set (e.g. '@online', '@thesis'); make sure we override
    # that so cited non-standard entries survive.
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB,
        {'web2022', 'phd2015'},
        bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE,
    )
    self.assertIn('web2022', cleaned)
    self.assertIn('phd2015', cleaned)

  def test_always_keeps_ieeetranbstctl_even_if_uncited(self):
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'smith2020'}, bib_cleaner.DEFAULT_BIB_FIELDS_TO_DELETE
    )
    self.assertIn('IEEEexample:BSTcontrol', cleaned)
    # BibTeX field/type names are case-insensitive; bibtexparser lowercases
    # them on parse, so check case-insensitively.
    self.assertIn('ctldash_repeated_names', cleaned.lower())
    self.assertNotIn('web2022', cleaned)
    self.assertNotIn('phd2015', cleaned)

  def test_never_deletes_id_or_entrytype(self):
    # A user accidentally listing 'ID'/'ENTRYTYPE' should not corrupt output.
    cleaned = bib_cleaner.clean_bib_content(
        SAMPLE_BIB, {'smith2020'}, fields_to_delete=['id', 'entrytype']
    )
    self.assertIn('@article{smith2020', cleaned)

  def test_removes_disabled_entry_hidden_inside_comment(self):
    # Wrapping an entry in @comment{...} is a common way to disable it
    # without deleting it. Without pre-stripping comments, bibtexparser's
    # own (non-brace-balanced) comment handling can leak such an entry
    # through as if it were live, even though its key is never cited.
    bib = SAMPLE_BIB + (
        '\n@comment{\n'
        '@article{disabled2020, author = {X}, title = {Y}, year = {2020}}\n'
        '}\n'
    )
    cleaned = bib_cleaner.clean_bib_content(
        bib, {'smith2020', 'disabled2020'}, []
    )
    self.assertNotIn('disabled2020', cleaned)

  def test_drops_malformed_comment_remnants(self):
    # Real-world bib files sometimes contain comments with mismatched
    # braces (e.g. '@comment{,\n}}'); any leftover fragments must not
    # resurface as a stray '@comment{...}' in the cleaned output.
    bib = (
        '@comment{,\n}}\n\n'
        '@article{smith2020, author = {Smith, J.}, title = {T}, year = {2020}}\n'
    )
    cleaned = bib_cleaner.clean_bib_content(bib, {'smith2020'}, [])
    self.assertNotIn('@comment', cleaned.lower())
    self.assertIn('smith2020', cleaned)


if __name__ == '__main__':
  unittest.main()
