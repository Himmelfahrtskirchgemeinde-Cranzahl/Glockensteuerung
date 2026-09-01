# Rulesets

Schutzregeln für dieses Repository. Sie liegen hier als Datei, damit
nachvollziehbar ist, was gilt — **wirksam werden sie erst durch den Import** in
den Repository-Einstellungen.

## Einspielen

**Einstellungen → Rules → Rulesets → New ruleset → Import a ruleset**, dann die
jeweilige Datei auswählen. Nach dem Import prüfen, ob `Enforcement status` auf
*Active* steht.

## Was die Regeln bewirken

### `main-schuetzen.json`

| Regel | Wirkung |
|---|---|
| Restrict deletions | `main` kann nicht gelöscht werden |
| Block force pushes | kein Überschreiben der Historie auf `main` |
| Require a pull request | kein direkter Push auf `main` — passt zur Arbeitsregel „nie direkt auf main" |

Die Pull-Request-Regel verlangt **keine** Freigabe (`required_approving_review_count: 0`).
Das ist Absicht: In einem Projekt mit einem Betreuer kann niemand den eigenen
Pull Request freigeben — mit einer verlangten Freigabe wäre nichts mehr
mergebar.

### `versions-tags-schuetzen.json`

Schützt Tags der Form `v*` vor Löschen und Überschreiben. Wichtig, weil die
Releases unveränderlich sind: Ein gelöschter Tag ließe sich nicht sauber neu
setzen, das zugehörige Release hinge in der Luft.

## Bewusst nicht enthalten

**Erforderliche Status-Checks.** Naheliegend wäre, den Check `build` zu
verlangen. Das wäre hier aber eine Falle: Der Workflow
`build-extension.yml` läuft nur bei Änderungen unter `extension/**`. Ein Pull
Request, der ausschließlich den Gateway oder die Anleitung anfasst, bekäme
deshalb nie einen `build`-Check — und bliebe mit dieser Regel dauerhaft
blockiert, ohne dass etwas kaputt wäre.

Wer die Regel dennoch möchte, muss zuerst den `paths`-Filter aus dem Workflow
entfernen, damit der Check bei **jedem** Pull Request läuft. Erst dann ist sie
gefahrlos.

## Sich nicht aussperren

Beide Rulesets kommen ohne `bypass_actors`, gelten also für alle. Wer sich die
Möglichkeit offenhalten will, im Notfall daran vorbeizuarbeiten, trägt nach dem
Import unter **Bypass list** die Rolle *Repository admin* ein.
