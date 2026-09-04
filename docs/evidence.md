---
layout: story
title: Evidence
permalink: /evidence/
page_class: story
description: Dated, source-bound benchmark, profile, coverage, and fuzz reports with their interpretation limits.
---

# Evidence

Every item below is tied to a named source state, corpus, environment, or test
budget. Read its method and limitations before carrying an observation to a
different machine or workload.

{% assign evidence = site.pages | where: "page_class", "evidence" | sort: "title" %}
{% include document-list.html documents=evidence %}
