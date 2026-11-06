# Autonomous Region of the Azores (Região Autónoma dos Açores): law in git

Part of [lexifina/global-law](https://github.com/lexifina/global-law), one git history for every country's law: this is the law of Autonomous Region of the Azores, Portugal, which global-law reads at `portugal/azores/acts/`.

The law of the Autonomous Region of the Azores (Portugal) in git: one file per article, one commit per amending act on the day its change took effect, from the consolidated texts of the Diário da República. `git blame`, `git log` and `tools/on.py` work as in the other repositories of the shared design.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law), which places it at `pt-20/`. The national law is in [lexifina/portugal-law](https://github.com/lexifina/portugal-law).

The text is in Portuguese.

## What this repository holds

- `estatuto/`: the Estatuto Político-Administrativo of the region (Lei n.º 39/80, revised by Leis n.º 9/87, 61/98 and 2/2009), its text in force from 31 March 1987 (the first day the DR dates), as the oldest version available, then each revision on its own day.
- `dlr-<year>-<number>/`: every Decreto Legislativo Regional of the Assembleia Legislativa da Região Autónoma dos Açores (numbered `N/YYYY/A`) that the Diário da República marks in force and keeps a finished consolidated text of, with every version the DR dates. Regional decrees the DR does not consolidate are not included: their text in force cannot be read from it.

## Source

Diário da República (INCM), Legislação Consolidada, <https://diariodarepublica.pt/dr/legislacao-consolidada>, read through the JSON calls of the DR's own web application: for each act, its amendment timeline (every amending act, the provisions it added, changed or repealed, and the day each change took effect) and its whole consolidated text on each of those days. The acts were found with the DR's own search.

## Dates

- Each commit is dated at noon, Atlantic/Azores, on the day the change took effect, as the DR gives it for that version.
- The DR leaves the original text of most older acts undated. The first day is then the day the act's own entry-into-force sentence names, counted from its publication in the DR (the sentence is quoted in the commit); failing that, for acts published from 1 December 1998, the general rule of Lei n.º 74/98, artigo 2.º, as the DR gives its wording: in the Autonomous Regions the 15th day after publication until 30 June 2006, the 5th day from 1 July 2006. An older act with neither starts at the first day the DR dates any change to it, labelled as the oldest version available.
- Each change is credited to the amending act the DR names for that provision version. A change the DR ties to no single act is committed by the publisher and labelled unexplained.

## Files

`artigo-007.md` is Artigo 7.º (`artigo-007-a.md` Artigo 7.º-A); `preambulo.md` the act's title and preamble; `assinatura.md` the approval and signature lines; annexes are folders of their own (`anexo-...`). The headings of the parts that begin before an article are `##` lines at the top of its file; the article's own heading is `###`.

## How it is checked

- Every version of every act is read back from git on the day it took effect and on the day before (`tools/check_repo.py`); both must match the corpus.
- For every act, the letters and digits of its files on 30 October 2026 equal those of the DR's consolidated text for that day, read a second time from the DR's response by a separate reader.

## Limits

This is not an official publication, and the DR's consolidated texts have no legal value. Only the Diário da República (and, for acts published there, the Jornal Oficial of the region) as published is authoritative.
