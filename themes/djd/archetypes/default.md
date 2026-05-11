---
title: "{{ replace .Name "-" " " | title }}"
date: {{ .Date }}
draft: true
---

{{/*
This is the default archetype for data journal entries.
Hugo will use front matter from the YAML source.
*/}}
