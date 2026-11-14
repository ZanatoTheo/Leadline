# Plugins

A plugin is one folder that defines a task for Venus. No plugin ships yet; `tests/fixtures/toy_plugin/` is a working
example.

```
plugins/<name>/
  plugin.json          manifest (schema: venus/schemas/plugin.schema.json)
  input.schema.json    what one input looks like
  output.schema.json   what one output (and a training case's `expected`) looks like
  checker.py           check(input, output, expected) -> {total, parts, reasons}, total in [0, 1]
  tools.py             optional: make_tools(input) -> list
```

`plugin.json`:
```json
{
  "name": "my-task",
  "version": "1.0.0",
  "brief": "What the agent must do, in one or two sentences.",
  "input_schema": "input.schema.json",
  "output_schema": "output.schema.json",
  "checker": "checker:check",
  "seed_tendencies": [{"id": "t1", "text": "A first instruction worth testing."}]
}
```

Optional manifest fields:
- `"tools": "tools:make_tools"`: `make_tools(input)` returns a list of `venus.Tool(name, description, parameters,
  fn)` (or dicts with those keys). `fn(arguments: dict)` returns JSON-serialisable data; if it raises, the agent sees
  the error and goes on.
- `"web": false`: turn off the built-in web tools (`web_search`, `web_scrape`, `web_news`). They are on by default,
  and when on, the agent must search before its first answer.
- Seed tendencies may carry `"sources": ["https://..."]`.

Check it loads: `python -c "import venus; print(venus.load_plugin('plugins/my-task').name)"`.
