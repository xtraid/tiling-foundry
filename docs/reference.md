---
layout: story
title: Reference
permalink: /reference/
page_class: story
description: Maintained contracts, methods, implementation references, bibliography, and visibly separate historical context.
---

# Reference

These documents define maintained interfaces, methods, identities, and
correctness boundaries. They are not generated from a captured run.

{% assign references = site.pages | where: "page_class", "reference" | sort: "title" %}
{% include document-list.html documents=references %}

## Historical context

Historical material explains earlier decisions but does not define current
behavior.

{% assign history = site.pages | where: "page_class", "history" | sort: "title" %}
{% include document-list.html documents=history %}
