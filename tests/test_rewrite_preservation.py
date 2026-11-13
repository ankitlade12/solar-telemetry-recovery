"""An author rewrite may change every sentence, but not the facts the verified manuscript states."""
from research.rewrite_preservation import compare

VERIFIED = (r'We use 10,000 draws over seven fault scenarios~\cite{bracher2021,dhingra2026}. '
            r'NWIS rises by 1.81\% (Table~\ref{tab:main}).'
            '\n\\begin{equation}\\label{eq:global}\n w_i\\propto\\exp\\{-(o-o_i)/336\\}.\n\\end{equation}\n'
            r'Differences range from $-0.119\%$ to $+0.131\%$ over 0--6 h.')


def test_a_reworded_text_with_the_same_facts_passes():
    rewrite = (r'Across 7 fault scenarios we drew 10000 bootstrap samples~\cite{dhingra2026, bracher2021}. '
               r'Table~\ref{tab:main} shows NWIS going up by 1.81\%.'
               '\n\\begin{equation}\\label{eq:global}\n w_i\\propto\\exp\\{-(o-o_i)/336\\}.\n\\end{equation}\n'
               r'Over 0--6 h the change is between $-0.119\%$ and $+0.131\%$.')
    assert compare(VERIFIED, rewrite) == {}


def test_a_dropped_or_altered_number_is_reported():
    rewrite = VERIFIED.replace('1.81', '1.8').replace('$-0.119\\%$', '$0.119\\%$')
    assert compare(VERIFIED, rewrite)['numbers'] == {'missing': ['-0.119', '1.81'], 'added': ['0.119', '1.8']}


def test_a_lost_citation_reference_or_changed_equation_is_reported():
    rewrite = VERIFIED.replace('bracher2021,', '').replace('tab:main', 'tab:primary').replace('336', '360')
    report = compare(VERIFIED, rewrite)
    assert report['citations'] == {'missing': ['bracher2021'], 'added': []}
    assert report['references'] == {'missing': ['tab:main'], 'added': ['tab:primary']}
    assert report['equations']['missing'] and report['equations']['added']


def test_text_mode_minus_keeps_the_sign():
    assert compare(r'by $-0.119\%$ to $+0.131\%$', r'by \textminus0.119\% to +0.131\%') == {}
    assert compare(r'by $-0.119\%$', r'by 0.119\%')['numbers'] == {'missing': ['-0.119'], 'added': ['0.119']}


def test_digits_inside_keys_and_labels_are_not_numbers():
    assert compare(r'See~\cite{dhingra2026}.', r'See~\cite{dhingra2026} again.') == {}
