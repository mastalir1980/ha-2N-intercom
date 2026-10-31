# Dokumentace integrace 2N Intercom

Vývojářská / technická dokumentace. Uživatelské návody zůstávají v kořeni repa
([`README.md`](../README.md), [`INSTALLATION.md`](../INSTALLATION.md),
[`HOMEKIT_INTEGRATION.md`](../HOMEKIT_INTEGRATION.md)).

| Dokument | Obsah |
|---|---|
| [`OVERVIEW.md`](OVERVIEW.md) | **Začni tady.** Přehled projektu: stroje a agenti, pipeline od groomingu po merge, životní cyklus úkolu, kontroly, bezpečnost, běžné úkony. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Přehled komponent, datový model, tok dat, životní cyklus, kamera transport, dynamické entity. |
| [`API_REFERENCE.md`](API_REFERENCE.md) | 2N HTTP/RTSP endpointy, které integrace volá, mapování událostí, zvláštnosti firmwaru. |
| [`IMPROVEMENTS.md`](IMPROVEMENTS.md) | Návrh vylepšení – bezpečnost (TLS/HTTP/Basic) a možné chyby, seřazené dle závažnosti. |
| [`product/`](product/README.md) | Product analysis: 2N capabilities, Home Assistant changes, gaps (GAP). Sources with dates. |

### Diagramy (Excalidraw)

Otevři na [excalidraw.com](https://excalidraw.com) (drag & drop souboru) nebo ve
VS Code rozšíření *Excalidraw*.

| Soubor | Co zobrazuje |
|---|---|
| [`architecture.excalidraw`](architecture.excalidraw) | Komponenty integrace a jejich vazby (HA core → coordinator → API → device, platformy). |
| [`event-flow.excalidraw`](event-flow.excalidraw) | Tok událostí `local_push`: subscribe → pull → patch cache → update entit. |

> Diagramy se generují z [`_gen_excalidraw.py`](_gen_excalidraw.py)
> (`python3 docs/_gen_excalidraw.py`). Lze je upravovat i ručně v Excalidraw a
> uložit zpět.
