# Posts d'annonce — regreek

## LinkedIn (français)

---

Pendant ma thèse, je me suis heurté à un problème absurde : impossible de copier une seule ligne de grec depuis les PDF de mes éditions critiques.

Vous copiez « διὰ Ἡσαΐου κηρυχθὲν ἐν πνεύματι ἁγίῳ » — vous obtenez « dia; JHsai?ou khrucqe;n ejn pneuvmati aJgivw/ ».

La cause : des milliers d'éditions savantes composées entre 1985 et 2005 utilisent des polices grecques antérieures à Unicode (Graeca, SPIonic, GreekKeys…), qui stockent le grec sous forme de frappes clavier latines. Tous les extracteurs de texte reproduisent fidèlement ce charabia. Et à l'heure où chacun veut interroger ses sources avec des outils d'IA, ces éditions — souvent les seules éditions critiques existantes de textes majeurs — restent illisibles pour la machine.

J'ai construit regreek pour y répondre, et je le publie en open source (MIT) :

→ Décodage déterministe de 9 encodages hérités, tables dérivées empiriquement par alignement sur corpus et validées sur textes tenus à l'écart : 98-100 % d'attestation mesurée, chiffres et lacunes documentés dans chaque fichier de table.

→ Séparation des couches de la page : texte constitué, apparat critique, traduction en regard, titres courants — pour qu'une variante d'apparat ne soit jamais citée comme le texte lui-même. Validation : zéro fuite de l'apparat vers la couche texte.

→ Un contrat central : zéro fabrication. Pas de modèle de langue, pas d'OCR, pas d'inférence. Un caractère inconnu est préservé et signalé, jamais deviné. L'outil refuse même de « décoder » de la prose latine ordinaire en pseudo-grec.

pip install regreek — et c'est tout.

Si vous travaillez sur des textes anciens et possédez des documents dans des polices non couvertes (SGreek, WinGreek, Ismini…), quelques centaines de mots suffisent pour dériver et valider honnêtement une table : les contributions sont ouvertes.

https://github.com/romain-girardi-eng/regreek
DOI (citable) : https://doi.org/10.5281/zenodo.21778443

#DigitalHumanities #Classics #OpenSource #AncientGreek #Patristics #Philologie

---

## X (anglais)

---

Copy Greek from a scholarly PDF typeset before ~2005 and you get this:

dia; JHsai?ou khrucqe;n

instead of this:

διὰ Ἡσαΐου κηρυχθὲν

Pre-Unicode Greek fonts (Graeca, SPIonic, GreekKeys…) store Greek as Latin keystrokes — and every extractor faithfully reproduces the mojibake.

I built regreek to fix it. Open source, MIT:

• decodes 9 legacy encodings — tables derived by corpus alignment, 98–100 % attestation on held-out texts
• separates critical-edition layers: text / apparatus / translation — zero apparatus leakage into the text, measured
• zero fabrication: no LLM, no OCR, deterministic table lookup; unknown input is flagged, never guessed

pip install regreek

Have documents in an uncovered font (SGreek, WinGreek, Ismini…)? A few hundred words are enough to derive and honestly validate a table — contributions welcome.

Citable: https://doi.org/10.5281/zenodo.21778443
https://github.com/romain-girardi-eng/regreek

---

## Notes de publication

- Joindre `docs/demo.gif` aux deux posts (la démo animée : page → mojibake → détection des zones → sortie structurée).
- X : si le texte dépasse la limite du compte, couper après « pip install regreek » et mettre le lien + le point contributions en réponse au premier tweet.
- LinkedIn : publier le GIF en média natif (pas en lien), l'aperçu GitHub prendra le relais dans les commentaires si besoin.
