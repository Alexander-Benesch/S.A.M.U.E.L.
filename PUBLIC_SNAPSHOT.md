# Öffentlicher Quellstand für v2.0.0a40

Die Quellen für diese Alpha stammen vom integrierten Entwicklungscommit `96f1196e013036000fc40f17ade3a742051200c0`. Die öffentliche Projektion besitzt einen eigenen Commit. Das Release-Manifest bindet das Container-Image und die Installationsdateien an diesen öffentlichen Commit.

Die [README](README.md#öffentliche-alpha-auf-einem-docker-host-installieren) enthält den Einstieg für eine frische Docker-Installation. Die freigegebenen Dateien stehen beim [GitHub-Prerelease v2.0.0a40](https://github.com/Alexander-Benesch/S.A.M.U.E.L./releases/tag/v2.0.0a40).

Der interne Installationskandidat hat auf einer frischen Ubuntu-VM die Prüfung der signierten Metadaten, die Aufnahme des ersten Administrators und die Anmeldung eines neu angelegten leseberechtigten Kontos im Dashboard durchlaufen. Der interne Test verwendete eine eigene Registry und Testschlüssel. Die öffentliche Installation verwendet GitHub und die GitHub Container Registry.
