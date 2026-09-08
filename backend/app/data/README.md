# Vendored data

## `genres-tree.yaml`

The genre hierarchy from [beets](https://github.com/beetbox/beets), taken from
`beetsplug/lastgenre/genres-tree.yaml`. MIT licensed, © 2010-2016 Adrian Sampson.

Retrieved 2026-09-08 from
<https://raw.githubusercontent.com/beetbox/beets/master/beetsplug/lastgenre/genres-tree.yaml>

It maps roughly 800 genre terms into 21 top-level families. We use it to group
the free-form genre strings Spotify returns, so related genres can be counted
and coloured together instead of by arbitrary rank. It is a static reference:
refresh it deliberately, not on a schedule, and re-run the backend tests, which
assert the families this application depends on still exist.
